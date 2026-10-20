"""
Responsable d'atelier : dashboard, OR, réceptions, techniciens.
"""
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.choices import StatutVehicule, StatutVehiculeAtelier
from apps.accounts.decorators_atelier import resp_atelier_required
from apps.accounts.models import User
from apps.atelier.models import Atelier, CompteRendu, OrdreReparation, ReouvertureOR, StatutOR, StatutTache, Tache, _format_minutes
from apps.atelier.roles import ROLE_TECH
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.models import BonSortie
from apps.reception.models import Reception

from ._utils import (
    STATUTS_OR_ACTIFS, _entree_from_or, a_signe, atelier_requis,
    enrich_taches_duree, format_duree, techniciens_assignables,
)


def _moyenne(valeurs):
    return round(sum(valeurs) / len(valeurs), 1) if valeurs else 0


def _ecart_label(reel, estime):
    """'+1h30', '-20 min' ou '—' si rien de prévu."""
    if not estime:
        return '—'
    ecart = reel - estime
    if not ecart:
        return '0'
    return ('+' if ecart > 0 else '-') + _format_minutes(abs(ecart))



# ═══════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════
@resp_atelier_required
@atelier_requis
def dashboard_atelier(request):
    atelier = request.atelier
    today = timezone.localdate()

    ors_qs = OrdreReparation.objects.filter(ateliers=atelier, statut__in=STATUTS_OR_ACTIFS)
    # CORRIGÉ : avant, TOUS les OR actifs étaient chargés en mémoire pour en afficher 6
    compteurs_or = ors_qs.aggregate(
        or_ouverts=Count('id', filter=Q(statut=StatutOR.OUVERT), distinct=True),
        or_en_cours=Count('id', filter=Q(statut=StatutOR.EN_COURS), distinct=True),
    )
    compteurs_taches = Tache.objects.filter(atelier=atelier).aggregate(
        a_valider=Count('id', filter=Q(statut=StatutTache.TERMINEE)),
        termine_today=Count('id', filter=Q(
            statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE], date_fin__date=today)),
    )

    return render(request, 'atelier/resp/dashboard.html', {
        'atelier': atelier,
        'ors_actifs': (ors_qs.select_related('vehicule', 'vehicule__client', 'reception')
                       .prefetch_related('taches', 'ateliers').order_by('-date_creation')[:6]),
        'taches_a_valider': (
            Tache.objects.filter(atelier=atelier, statut=StatutTache.TERMINEE)
            .select_related('ordre_reparation__vehicule', 'valide_par')
            .prefetch_related('techniciens', 'comptes_rendus')
            .order_by('date_fin')[:6]
        ),
        'stats': {**compteurs_or, **compteurs_taches},
        'Vehicule_controle': (Reception.objects.filter(statut=StatutVehicule.RAPPORT_FAIT)
                              .select_related('vehicule', 'vehicule__client').order_by('-created_at')[:5]),
        'Vehicule_mecanique': (Reception.objects.filter(statut=StatutVehicule.FICHE_CONTROLE)
                               .select_related('vehicule', 'vehicule__client').order_by('-created_at')[:5]),
        'or_clotures_recents': (OrdreReparation.objects.filter(ateliers=atelier, statut=StatutOR.CLOTURE)
                                .select_related('vehicule').order_by('-date_cloture')[:6]),
        'today': today,
    })


# ═══════════════════════════════════════════════════════════
#  ORDRES DE RÉPARATION
# ═══════════════════════════════════════════════════════════
@resp_atelier_required
@atelier_requis
def liste_or_atelier(request):
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()

    qs = (OrdreReparation.objects.filter(ateliers=request.atelier)
          .select_related('vehicule', 'vehicule__client').prefetch_related('taches'))
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(numero__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )

    return render(request, 'atelier/resp/liste_or.html', {
        'atelier': request.atelier,
        'ors': qs.order_by('statut', '-urgence', 'date_creation'),
        'statut': statut,
        'q': q,
    })


# ═══════════════════════════════════════════════════════════
#  ORDRES DE RÉPARATION
# ═══════════════════════════════════════════════════════════
@resp_atelier_required
@atelier_requis
def detail_or_atelier(request, or_id):
    atelier = request.atelier
    or_obj = get_object_or_404(
        OrdreReparation.objects.select_related('vehicule', 'vehicule__client', 'reception')
        .prefetch_related('ateliers'),
        id=or_id, ateliers=atelier,
    )

    taches = list(
    or_obj.taches
    .filter(atelier=atelier)
    .select_related('atelier', 'valide_par', 'created_by', 'ordre_reparation')
    .prefetch_related('techniciens', 'comptes_rendus__technicien')
    .order_by('created_at')
)
    enrich_taches_duree(taches)

    entree = _entree_from_or(or_obj)
    return render(request, 'atelier/resp/detail_or.html', {
        'or': or_obj,
        'atelier': atelier,
        'entree': entree,
        'fiche_controle': getattr(entree, 'fiche_controle', None),
        'fiche_technique': getattr(entree, 'fiche_technique', None),
        'taches': taches,
        'nb_a_valider': sum(t.statut == StatutTache.TERMINEE for t in taches),
        'nb_validees': sum(t.statut == StatutTache.VALIDEE for t in taches),
        'stats': or_obj.stats_pour_atelier,
        'reouvertures': (or_obj.reouvertures.select_related('reouvert_par', 'reception')
                         .prefetch_related('taches')),
        'reception_actuelle': or_obj.reception_actuelle,
        # Verrou : dans le template, masquer créer / modifier / supprimer /
        # valider / refuser / clôture directe quand or_verrouille est vrai.
        'or_verrouille': or_obj.est_cloture,
        'techniciens': techniciens_assignables(atelier, request.user),
    })
 

@resp_atelier_required
@atelier_requis
def cloture_or_atelier(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id, ateliers=request.atelier)
    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=or_id)

    if or_obj.statut == StatutOR.CLOTURE:
        messages.info(request, f"L'OR {or_obj.numero} est déjà clôturé.")
        return redirect('detail_or_atelier', or_id=or_id)

    compte = or_obj.taches.aggregate(
        total=Count('id'),
        non_validees=Count('id', filter=~Q(statut=StatutTache.VALIDEE)),
    )
    if compte['total'] == 0:
        messages.error(request, "⚠️ Aucune tâche sur cet OR. Impossible de clôturer.")
        return redirect('detail_or_atelier', or_id=or_id)
    if compte['non_validees']:
        messages.error(request, f"⚠️ {compte['non_validees']} tâche(s) non validée(s). Impossible de clôturer.")
        return redirect('detail_or_atelier', or_id=or_id)

    # Durées définitives (prévue + réelle) figées au moment de la clôture
    or_obj.recalculer_duree_prevue(save=False)
    or_obj.recalculer_duree_reelle(save=False)
    or_obj.statut = StatutOR.CLOTURE
    or_obj.date_cloture = timezone.now()
    or_obj.save(update_fields=['statut', 'date_cloture', 'duree_fin_prevu', 'duree_fin_reel'])

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj,
               {'statut': 'CLOTURE', 'numero': or_obj.numero})
    messages.success(request, f"✅ OR {or_obj.numero} clôturé.")
    return redirect('detail_or_atelier', or_id=or_id)



# ═══════════════════════════════════════════════════════════
#  RÉCEPTIONS
# ═══════════════════════════════════════════════════════════
@resp_atelier_required
def detail_reception(request, rec_id):
    rec = get_object_or_404(
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'entree', 'receptionniste')
        .prefetch_related('transferts__atelier'),
        id=rec_id,
    )
    entree = getattr(rec, 'entree', None)
    fiche_controle = getattr(entree, 'fiche_controle', None)
    fiche_technique = getattr(entree, 'fiche_technique', None)

    return render(request, 'atelier/resp/detail_reception.html', {
        'rec': rec,
        # OR d'origine de cette réception + OR réouverts sur cette réception
        'or_list': (OrdreReparation.objects
                    .filter(Q(reception=rec) | Q(reouvertures__reception=rec))
                    .distinct()
                    .prefetch_related('ateliers', 'taches').order_by('-date_creation')),
        'reouvertures': (ReouvertureOR.objects.filter(reception=rec)
                         .select_related('ordre_reparation', 'reouvert_par').prefetch_related('taches')),
        'bon_sortie': BonSortie.objects.filter(vehicule=rec.vehicule, reception=rec).first(),
        'fiche_controle': fiche_controle,
        'fiche_technique': fiche_technique,
        'a_fiche_controle': a_signe(fiche_controle, 'signature_technicien'),
        'a_fiche_technique': a_signe(fiche_technique, 'signature_controleur'),
        'client_a_signe': a_signe(fiche_controle, 'signature_client_avant'),
        'signature_apres_faite': a_signe(fiche_controle, 'signature_client_apres'),
    })


# ═══════════════════════════════════════════════════════════
#  TECHNICIEN
# ═══════════════════════════════════════════════════════════
@resp_atelier_required
def detail_technicien(request, tech_id):
    tech = get_object_or_404(User.objects.select_related('atelier'), id=tech_id, role=ROLE_TECH)

    # temps_tech = minutes saisies PAR CE technicien sur la tâche (une tâche
    # peut avoir plusieurs techniciens : on ne lui compte que ses comptes rendus)
    base = (
        Tache.objects.filter(techniciens=tech)
        .select_related('ordre_reparation__vehicule', 'atelier')
        .annotate(temps_tech=Sum('comptes_rendus__duree_minutes',
                                 filter=Q(comptes_rendus__technicien=tech)))
    )
    taches = list(base.order_by('-created_at'))
    for t in taches:
        t.temps_tech = t.temps_tech or 0
        t.temps_tech_label = _format_minutes(t.temps_tech)

    faites = sorted((t for t in taches if t.statut in (StatutTache.TERMINEE, StatutTache.VALIDEE)),
                    key=lambda t: t.date_fin or t.created_at, reverse=True)
    restantes = [t for t in taches if t.statut in (StatutTache.A_FAIRE, StatutTache.EN_COURS)]
    a_reprendre = [t for t in restantes if t.est_a_reprendre]
    refusees = [t for t in taches if t.nb_refus]
    reouvertes = [t for t in taches if t.nb_reouvertures]

    temps_total = (CompteRendu.objects.filter(technicien=tech)
                   .aggregate(s=Sum('duree_minutes'))['s'] or 0)
    temps_mois = (CompteRendu.objects.filter(
        technicien=tech,
        date_saisie__year=timezone.localdate().year,
        date_saisie__month=timezone.localdate().month,
    ).aggregate(s=Sum('duree_minutes'))['s'] or 0)
    temps_faites = [t.temps_tech for t in faites if t.temps_tech]
    delais = [t.delai_avant_demarrage_minutes for t in faites
              if t.delai_avant_demarrage_minutes is not None]
    estime_faites = sum(t.duree_estimee_minutes or 0 for t in faites)

    return render(request, 'atelier/resp/detail_technicien.html', {
        'tech': tech,
        'taches_restantes': restantes,
        'taches_a_reprendre': a_reprendre,
        'taches_faites': faites,
        'taches_refusees': refusees,
        'taches_reouvertes': reouvertes,
        'stats': {
            'nb_total': len(taches),
            'nb_effectuees': len(faites),
            'nb_validees': sum(t.statut == StatutTache.VALIDEE for t in faites),
            'nb_restantes': len(restantes),
            'nb_a_reprendre': len(a_reprendre),
            'nb_refus': sum(t.nb_refus for t in taches),
            'nb_taches_refusees': len(refusees),
            'nb_reouvertures': sum(t.nb_reouvertures for t in taches),
            'nb_taches_reouvertes': len(reouvertes),
            'nb_en_retard': sum(t.en_retard for t in faites),
            'temps_total': _format_minutes(temps_total),
            'temps_mois': _format_minutes(temps_mois),
            'temps_moyen': _format_minutes(int(_moyenne(temps_faites))),
            'temps_estime_faites': _format_minutes(estime_faites),
            'delai_moyen_demarrage': _format_minutes(int(_moyenne(delais))),
            'taux_refus': int(len(refusees) / len(faites) * 100) if faites else 0,
        },
    })


@resp_atelier_required
def liste_receptions(request):
    qs = (
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'receptionniste', 'ordre_reparation')
        .prefetch_related('ordre_reparation__ateliers')
        .order_by('-created_at')
    )
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(numero__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )
    return render(request, 'atelier/resp/liste_receptions.html', {
        'receptions': qs[:100],
        'statuts': StatutVehiculeAtelier.choices,
        'statut_filter': statut,
    })


# ═══════════════════════════════════════════════════════════
#  TECHNICIENS
# ═══════════════════════════════════════════════════════════
@resp_atelier_required
def liste_techniciens(request):
    q = request.GET.get('q', '').strip()
    qs = User.objects.filter(role=ROLE_TECH, is_active=True)
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(email__icontains=q))
    techniciens = list(qs.order_by('nom', 'prenom'))

    # CORRIGÉ : 1 seule requête groupée (avant : 4 requêtes PAR technicien)
    lignes = (
        Tache.objects.filter(techniciens__in=techniciens)
        .values('techniciens')
        .annotate(
            nb_total=Count('id'),
            nb_validees=Count('id', filter=Q(statut=StatutTache.VALIDEE)),
            nb_en_cours=Count('id', filter=Q(statut=StatutTache.EN_COURS)),
            nb_a_faire=Count('id', filter=Q(statut=StatutTache.A_FAIRE)),
        )
        .order_by()
    )
    par_tech = {l['techniciens']: l for l in lignes}
    for tech in techniciens:
        l = par_tech.get(tech.id, {})
        tech.nb_total = l.get('nb_total', 0)
        tech.nb_validees = l.get('nb_validees', 0)
        tech.nb_en_cours = l.get('nb_en_cours', 0)
        tech.nb_a_faire = l.get('nb_a_faire', 0)

    return render(request, 'atelier/resp/liste_techniciens.html', {'techniciens': techniciens, 'q': q})


def _moyenne(valeurs):
    return round(sum(valeurs) / len(valeurs), 1) if valeurs else 0



# ═══════════════════════════════════════════════════════════
#  ATELIER (nouveau)
# ═══════════════════════════════════════════════════════════
def detail_atelier(request, atelier_id):
    """Admin : n'importe quel atelier. Responsable : seulement le sien."""
    atelier = get_object_or_404(Atelier.objects.select_related('responsable', 'created_by'), id=atelier_id)
    user = request.user
    est_admin = getattr(user, 'role', None) == 'ADMIN' or user.is_superuser
    est_chef = atelier.responsable_id == user.id or getattr(user, 'atelier_id', None) == atelier.id


    # ── OR de l'atelier ──
    ors_base = OrdreReparation.objects.filter(ateliers=atelier)
    compteurs_or = ors_base.aggregate(
        total=Count('id', distinct=True),
        ouverts=Count('id', filter=Q(statut=StatutOR.OUVERT), distinct=True),
        en_cours=Count('id', filter=Q(statut=StatutOR.EN_COURS), distinct=True),
        reouverts=Count('id', filter=Q(statut=StatutOR.REOUVERT), distinct=True),
        clotures=Count('id', filter=Q(statut=StatutOR.CLOTURE), distinct=True),
    )

    statut = request.GET.get('statut', '').strip()
    q = request.GET.get('q', '').strip()
    ors = (ors_base.select_related('vehicule', 'vehicule__client', 'reception')
           .annotate(nb_reouv=Count('reouvertures', distinct=True)))
    if statut:
        ors = ors.filter(statut=statut)
    if q:
        ors = ors.filter(Q(numero__icontains=q)
                         | Q(vehicule__immatriculation__icontains=q)
                         | Q(vehicule__client__nom__icontains=q))
    ors = list(ors.order_by('-date_creation')[:100])

    # ── Tâches de l'atelier ──
    taches_atelier = Tache.objects.filter(atelier=atelier)
    compteurs_taches = taches_atelier.aggregate(
        total=Count('id'),
        a_faire=Count('id', filter=Q(statut=StatutTache.A_FAIRE)),
        en_cours=Count('id', filter=Q(statut=StatutTache.EN_COURS)),
        a_valider=Count('id', filter=Q(statut=StatutTache.TERMINEE)),
        validees=Count('id', filter=Q(statut=StatutTache.VALIDEE)),
        refusees=Count('id', filter=Q(nb_refus__gt=0)),
        nb_refus=Sum('nb_refus'),
        reouvertes=Count('id', filter=Q(nb_reouvertures__gt=0)),
        estime=Sum('duree_estimee_minutes'),
    )
    temps_reel = (CompteRendu.objects.filter(tache__atelier=atelier)
                  .aggregate(s=Sum('duree_minutes'))['s'] or 0)
    estime = compteurs_taches['estime'] or 0

    # ── Réouvertures touchant cet atelier ──
    reouvertures = list(
        ReouvertureOR.objects.filter(ordre_reparation__ateliers=atelier).distinct()
        .select_related('ordre_reparation__vehicule', 'reception', 'reouvert_par')
        .prefetch_related('taches__techniciens')
        .order_by('-date_reouverture')[:50]
    )

    # ── Techniciens de l'atelier : charge et performance ──
    techniciens = list(User.objects.filter(role=ROLE_TECH, atelier=atelier, is_active=True)
                       .order_by('nom', 'prenom'))
    lignes = {
        l['techniciens']: l for l in
        taches_atelier.filter(techniciens__in=techniciens).values('techniciens').annotate(
            nb_total=Count('id'),
            nb_validees=Count('id', filter=Q(statut=StatutTache.VALIDEE)),
            nb_en_cours=Count('id', filter=Q(statut=StatutTache.EN_COURS)),
            nb_a_faire=Count('id', filter=Q(statut=StatutTache.A_FAIRE)),
            nb_refus=Sum('nb_refus'),
            nb_reouv=Sum('nb_reouvertures'),
        ).order_by()
    }
    temps = {
        l['technicien']: l['s'] for l in
        CompteRendu.objects.filter(tache__atelier=atelier, technicien__in=techniciens)
        .values('technicien').annotate(s=Sum('duree_minutes')).order_by()
    }
    for tech in techniciens:
        l = lignes.get(tech.id, {})
        tech.nb_total = l.get('nb_total', 0)
        tech.nb_validees = l.get('nb_validees', 0)
        tech.nb_en_cours = l.get('nb_en_cours', 0)
        tech.nb_a_faire = l.get('nb_a_faire', 0)
        tech.nb_refus = l.get('nb_refus') or 0
        tech.nb_reouv = l.get('nb_reouv') or 0
        tech.temps_label = _format_minutes(temps.get(tech.id) or 0)

    return render(request, 'atelier/detail_atelier.html', {
        'atelier': atelier,
        'est_admin': est_admin,
        'compteurs_or': compteurs_or,
        'compteurs_taches': compteurs_taches,
        'temps': {
            'estime': _format_minutes(estime),
            'reel': _format_minutes(temps_reel),
            'ecart': _ecart_label(temps_reel, estime),
            'en_depassement': bool(estime) and temps_reel > estime,
        },
        'ors': ors,
        'statuts_or': StatutOR.choices,
        'statut': statut,
        'q': q,
        'reouvertures': reouvertures,
        'techniciens': techniciens,
        'taches_a_valider': list(
            taches_atelier.filter(statut=StatutTache.TERMINEE)
            .select_related('ordre_reparation__vehicule').prefetch_related('techniciens')
            .order_by('date_fin')[:10]
        ),
        'taches_a_reprendre': list(
            taches_atelier.exclude(type_retour='')
            .filter(statut__in=[StatutTache.A_FAIRE, StatutTache.EN_COURS])
            .select_related('ordre_reparation__vehicule').prefetch_related('techniciens')
            .order_by('-date_retour')[:10]
        ),
    })
