"""
Entrées / sorties, réceptions, ordres de réparation.
"""
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Case, IntegerField, Sum, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.choices import StatutOR, StatutReception, StatutTache
from apps.atelier.models import OrdreReparation, ReouvertureOR, Tache
from apps.atelier.views import _entree_from_or, enrich_taches_duree
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.models import BonSortie, EnregistrementEntree, MotifEntree, StatutVehicule
from apps.reception.models import Reception
from apps.reception.views import (
    get_entrees_presentes_filtrees, get_filtered_entrees, paginate_queryset,
)
from apps.reception.views._utils import _notifier, get_or_none, post_str
from apps.reception.views.receptions import _contexte_or_reception, _signe
from apps.vehicules.models import Vehicule

from ..decorators import admin_required, receptionniste_required
from ._utils import MOTIFS_VALIDES


# ─── Entrées ─────────────────────────────────────────────────────────────
@admin_required
def historique_entrees(request):
    page_obj = paginate_queryset(request, get_filtered_entrees(request), per_page=25)
    return render(request, 'admin_custom/mouvements/historique_admin.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'statuts': StatutVehicule.choices,
        'motifs': MotifEntree.choices,
    })


@admin_required  # CORRIGÉ : la vue était accessible sans connexion
def liste_vehicules_presents(request):
    page_obj = paginate_queryset(request, get_entrees_presentes_filtrees(request), per_page=25)
    return render(request, 'admin_custom/mouvements/vehicules_presents_admin.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'motifs': MotifEntree.choices,
    })


@admin_required
def detail_entree(request, entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related(
            'vehicule', 'vehicule__client', 'conducteur', 'agent_entree'),
        id=entree_id,
    )
    return render(request, 'admin_custom/mouvements/Entre_detail.html', {'entree': entree})


@admin_required
@require_POST
def modifier_motif_admin(request, entree_id):
    entree = get_object_or_404(EnregistrementEntree, pk=entree_id)
    motif = request.POST.get('motif')

    if motif in MOTIFS_VALIDES:
        entree.motif = motif
        entree.save(update_fields=['motif'])
        # CORRIGÉ : on ne logue que si la modification a réellement eu lieu
        log_action(request, ActionType.MODIFICATION, 'ADMIN', entree, {'motif': motif})
        messages.success(request, f"Motif modifié : {entree.get_motif_display()}")
    else:
        messages.error(request, "Motif invalide.")

    return redirect('detail_entree_admin', entree_id=entree.id)



def _ordre_receptions(qs):
    """Fiches (contrôle / technique) en premier, puis réparation, puis le reste."""
    return qs.annotate(
        priorite=Case(
            When(statut=StatutReception.FICHE_CONTROLE, then=0),   # PRESENT_ATELIER
            When(statut=StatutReception.FICHE_TECHNIQUE, then=1),
            When(statut=StatutReception.RAPPORT_FAIT, then=2),
            When(statut=StatutReception.REPARATION_EN_COURS, then=3),
            When(statut=StatutReception.TRAVAUX_TERMINES, then=4),
            When(statut=StatutReception.BON_SORTIE_FAIT, then=5),
            default=9,
            output_field=IntegerField(),
        )
    ).order_by('priorite', '-created_at')

# ─── Réceptions ──────────────────────────────────────────────────────────
@admin_required
def liste_receptions(request):
    qs = (
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'receptionniste', 'ordre_reparation')
        .prefetch_related('ordre_reparation__ateliers')
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

    qs = _ordre_receptions(qs)
    page_obj = paginate_queryset(request, qs, per_page=25)
    return render(request, 'admin_custom/mouvements/liste_receptions_admin.html', {
        'receptions': page_obj,
        'page_obj': page_obj,
        'statuts': StatutReception.choices,
        'statut_filter': statut,
    })


# Vue admin (dans le fichier des vues admin)
@admin_required
def detail_reception(request, rec_id):
    rec = get_object_or_404(
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'entree', 'receptionniste')
        .prefetch_related('transferts__atelier'),
        id=rec_id,
    ) 
    entree = getattr(rec, 'entree', None)
    fiche = getattr(entree, 'fiche_controle', None)

    bon_sortie = None
    if rec.entree_id:
        bon_sortie = getattr(rec.entree, 'bon_sortie', None)

    if bon_sortie is None:
        qs = BonSortie.objects.filter(vehicule=rec.vehicule)
    # si le champ existe :
        if any(f.name == 'reception' for f in BonSortie._meta.fields):
            qs_rec = qs.filter(reception=rec)
            bon_sortie = qs_rec.order_by('-created_at').first() or qs.order_by('-created_at').first()
        else:
            bon_sortie = qs.order_by('-created_at').first()

    return render(request, 'admin_custom/mouvements/detail_rec_admin.html', {
        'rec': rec,
        **_contexte_or_reception(rec),
        'bon_sortie': bon_sortie,
        'fiche_technique': getattr(entree, 'fiche_technique', None),
        'fiche_controle': fiche,
        'a_fiche_controle': _signe(fiche, 'signature_technicien'),
        'client_a_signe': _signe(fiche, 'signature_client_avant'),
        'signature_apres_faite': _signe(fiche, 'signature_client_apres'),
    })




@receptionniste_required
def creer_reception_admin(request):
    entree = None
    entree_id = request.GET.get('entree_id')
    if entree_id:
        entree = get_object_or_404(
            EnregistrementEntree.objects.select_related('vehicule'),
            id=entree_id, motif=MotifEntree.REPARATION,
        )
        if hasattr(entree, 'reception'):
            messages.warning(request, "Cette entrée a déjà une réception.")
            return redirect('detail_rec_admin', rec_id=entree.reception.id)

    if request.method != 'POST':
        return render(request, 'admin_custom/mouvements/creer_reception.html', {'entree': entree})

    entree_id_post = post_str(request, 'entree_id') or post_str(request, 'entree_select')
    vehicule_id_post = post_str(request, 'vehicule_id')
    decision = request.POST.get('decision', 'VERS_ATELIER')
    observations = post_str(request, 'observations')

    error, vehicule = None, None
    if not (vehicule_id_post or entree_id_post):
        error = "Sélectionnez un véhicule ou une entrée guérite."
    elif not observations:
        error = "Les observations sont obligatoires."
    elif entree_id_post:
        entree = get_or_none(EnregistrementEntree.objects.select_related('vehicule'), id=entree_id_post)
        if entree is None:
            error = "Entrée introuvable."
        elif hasattr(entree, 'reception'):
            # CORRIGÉ : évite une IntegrityError (2 réceptions pour la même entrée)
            error = "Cette entrée a déjà une réception."
        else:
            vehicule = entree.vehicule
    else:
        vehicule = get_or_none(Vehicule.objects, id=vehicule_id_post)
        if vehicule is None:
            error = "Véhicule introuvable."

    if error:
        return render(request, 'admin_custom/mouvements/creer_reception.html', {'entree': entree, 'error': error})

    with transaction.atomic():
        rec = Reception.objects.create(
            entree=entree,
            vehicule=vehicule,
            statut=StatutVehicule.RAPPORT_FAIT,
            receptionniste=request.user,
            observations=observations,
        )
        if entree:
            entree.statut = StatutVehicule.RAPPORT_FAIT
            entree.save(update_fields=['statut'])

    log_action(request, ActionType.CREATION, 'RECEPTION', rec, {'decision': decision})
    messages.success(request, f"Réception {rec.numero} créée.")

    if decision == 'SORTIE_DIRECTE':
        if entree:
            return redirect('creer_sortie_lien_admin', rec_id=entree.id)
        # CORRIGÉ : avant, crash (entree = None) quand on passait par le véhicule seul
        messages.warning(request, "Sortie directe impossible sans entrée guérite.")

    return redirect('detail_rec_admin', rec_id=rec.id)


# ─── Ordres de réparation ────────────────────────────────────────────────
@admin_required
def liste_or(request):
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()

    qs = OrdreReparation.objects.select_related('vehicule', 'vehicule__client').prefetch_related('taches')
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(numero__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )

    page_obj = paginate_queryset(request, qs.order_by('statut', '-urgence', 'date_creation'), per_page=25)
    return render(request, 'admin_custom/mouvements/liste_or.html', {
        'ors': page_obj, 'page_obj': page_obj, 'statut': statut, 'q': q,
    })


@admin_required
def detail_or_admin(request, or_id):
    # Les tâches sont chargées une seule fois (plus de double prefetch)
    or_obj = get_object_or_404(
        OrdreReparation.objects
        .select_related('vehicule', 'vehicule__client', 'reception', 'created_by')
        .prefetch_related('ateliers'),
        id=or_id,
    )

    taches = list(
        or_obj.taches
        .select_related('atelier', 'valide_par', 'created_by')
        .prefetch_related('techniciens', 'comptes_rendus__technicien')
        .order_by('atelier__nom', 'created_at')
    )
    enrich_taches_duree(taches)

    entree = _entree_from_or(or_obj)
    return render(request, 'admin_custom/mouvements/detail_or.html', {
        'or': or_obj,
        'entree': entree,
        'fiche_controle': getattr(entree, 'fiche_controle', None),
        'fiche_technique': getattr(entree, 'fiche_technique', None),
        'taches': taches,
        'nb_validees': sum(1 for t in taches if t.statut == StatutTache.VALIDEE),
    })




@receptionniste_required
def cloture_or(request, or_id):
    o = get_object_or_404(OrdreReparation.objects.select_related('vehicule', 'reception'), id=or_id)
    if request.method != 'POST':
        return redirect('detail_rec_admin', or_id=or_id)


    date_str = request.POST.get('date_depot_devis', '').strip()
    if not date_str:
        messages.error(request, "La date de dépôt du devis est obligatoire.")
        if o.reception_id:
            return redirect('detail_rec_admin', rec_id=o.reception_id)
        return redirect('detail_or_admin', or_id=o.id)

    try:
        from datetime import datetime
        date_depot = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        messages.error(request, "Date de dépôt invalide.")
        if o.reception_id:
            return redirect('detail_rec_admin', rec_id=o.reception_id)
        return redirect('detail_or_admin', or_id=o.id)
    
    now = timezone.now()
    with transaction.atomic():  # AJOUTÉ : tout ou rien
        a_valider = list(o.taches.exclude(statut=StatutTache.VALIDEE))
        for t in a_valider:
            t.date_debut = t.date_debut or now
            t.date_fin = t.date_fin or now
            t.duree_reelle_minutes = t.duree_reelle_minutes or t.duree_estimee_minutes or 0
            t.statut = StatutTache.VALIDEE
            t.valide_par = request.user
            t.date_validation = now
            t.commentaire_validation = (t.commentaire_validation
                                        or "Validée automatiquement à la clôture de l'OR.")
            t.save()

        o.duree_totale_minutes = o.taches.aggregate(t=Sum('duree_reelle_minutes'))['t'] or 0
        o.statut = StatutOR.CLOTURE
        o.date_cloture = now
        o.save()

        if o.reception:
            o.reception.statut = StatutVehicule.TRAVAUX_TERMINES
            o.reception.date_depot_devis = date_depot
            o.reception.save(update_fields=['statut', 'date_depot_devis'])

    if o.reception:
        _notifier('OR_CLOTURE', f"OR {o.numero} clôturé",
                  f"Travaux terminés sur {o.vehicule.immatriculation}.", o.reception)

    log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', o, {
        'statut': 'CLOTURE', 'nb_taches_auto_validees': len(a_valider),
        'date_depot_devis': str(date_depot),
    })
    messages.success(
        request,
        f"OR {o.numero} clôturé ({len(a_valider)} tâche(s) validée(s)). "
        f"Dépot devis : {date_depot.strftime('%d/%m/%Y')}.",
    )
    # CORRIGÉ : avant, crash si l'OR n'avait pas de réception (rec_id=None)
    if o.reception_id:
        return redirect('detail_rec_admin', rec_id=o.reception_id)
    return redirect('detail_or_admin', or_id=o.id)


def _lire_duree(request):
    """Durée en minutes depuis duree_heures / duree_minutes, ou None si invalide."""
    try:
        heures = int(request.POST.get('duree_heures') or 0)
        minutes = int(request.POST.get('duree_minutes') or 0)
    except ValueError:
        return None
    if heures < 0 or not 0 <= minutes < 60:
        return None
    return heures * 60 + minutes


@receptionniste_required
def reouverture_or(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id, statut=StatutOR.CLOTURE)
    if request.method != 'POST':
        return redirect('detail_or_admin', or_id=or_id)

    def erreur(msg):
        messages.error(request, msg)
        return redirect('detail_or_admin', or_id=or_id)

    raison = request.POST.get('raison', '').strip()
    if not raison:
        return erreur("La raison de la réouverture est obligatoire.")

    tache_ids = [t for t in request.POST.getlist('taches') if t.strip()]
    taches = list(Tache.objects.filter(id__in=tache_ids, ordre_reparation=or_obj))
    if not taches:
        return erreur("Sélectionnez au moins une tâche à refaire.")

    duree_totale = _lire_duree(request)
    if duree_totale is None:
        return erreur("Durée invalide.")
    if duree_totale <= 0:
        return erreur("La durée de la réouverture doit être supérieure à 0.")

    with transaction.atomic():
        or_obj.statut = StatutOR.REOUVERT
        or_obj.save(update_fields=['statut'])

        for tache in taches:
            tache.statut = StatutTache.A_FAIRE
            tache.date_debut = tache.date_fin = tache.date_validation = None
            tache.valide_par = None
            tache.save()

        reouverture = ReouvertureOR.objects.create(
            ordre_reparation=or_obj,
            raison=raison,
            duree_prevue_minutes=duree_totale,
            reouvert_par=request.user,
        )
        reouverture.taches.set(taches)

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {
        'statut': 'REOUVERT',
        'raison': raison,
        'numero': or_obj.numero,
        'taches': [t.libelle for t in taches],
        'duree_prevue_minutes': duree_totale,
    })
    messages.success(
        request,
        f"🔓 OR {or_obj.numero} réouvert : {len(taches)} tâche(s) à refaire, "
        f"durée prévue {reouverture.duree_prevue_label}."
    )
    return redirect('detail_or_admin', or_id=or_id)
