"""
apps/atelier/views.py
Vues Atelier — Responsable + Technicien + audit
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from apps.accounts.decorators_atelier import resp_atelier_required, technicien_required
from apps.accounts.models import User
from apps.guerite.models import BonSortie
from apps.reception.models import Reception
from apps.audit.service import log_action
from apps.audit.models import ActionType
from apps.accounts.choices import StatutVehicule, StatutVehiculeAtelier
from .roles import ROLE_TECH
from .models import (
    Atelier, OrdreReparation, FicheControle, FicheTechnique,
    Tache, CompteRendu, ReouvertureOR, StatutOR, StatutTache, _format_minutes,
)


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def get_atelier_du_resp(user):
    return Atelier.objects.filter(responsable=user, is_active=True).first()


def techniciens_assignables(atelier, user):
    qs = list(
        User.objects.filter(role='TECHNICIEN', is_active=True)
        .order_by('nom', 'prenom')
    )
    if user not in qs:
        qs.insert(0, user)
    return qs


def _entree_from_or(or_obj):
    reception = getattr(or_obj, 'reception', None)
    if reception is None:
        return None
    return getattr(reception, 'entree', None)


def format_duree(minutes):
    if minutes is None:
        return "—"
    try:
        m = int(round(float(minutes)))
    except (TypeError, ValueError):
        return "—"
    if m < 0:
        m = 0
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} h" if r == 0 else f"{h} h {r} min"



def parse_duree_hm(request, h_name='duree_heures', m_name='duree_minutes', default=60):
    """Lit heures + minutes du POST → total en minutes (min 1)."""
    try:
        h = int(request.POST.get(h_name) or 0)
    except (TypeError, ValueError):
        h = 0
    try:
        m = int(request.POST.get(m_name) or 0)
    except (TypeError, ValueError):
        m = 0
    h = max(h, 0)
    m = min(max(m, 0), 59)
    total = h * 60 + m
    return total if total > 0 else default


def enrich_taches_duree(taches):
    """Attache les labels de durée aux tâches — noms préfixés pour éviter les conflits."""
    for t in taches:
        est = t.duree_estimee_minutes or 0
        t.est_h, t.est_m = divmod(est, 60)

        # ── Comptes rendus prefetchés ──
        crs = list(t.comptes_rendus.all())
        total_cr = sum(cr.duree_minutes or 0 for cr in crs)

        # ── Attributs calculés (évite les N+1) ──
        t.calc_duree_technicien   = total_cr
        t.calc_duree_reelle       = t.duree_reelle_minutes or total_cr
        t.calc_duree_estimee_lbl  = _format_minutes(est)
        t.calc_duree_technicien_lbl = _format_minutes(total_cr)
        t.calc_duree_reelle_lbl   = _format_minutes(t.calc_duree_reelle)

        if t.duree_estimee_minutes is not None:
            ecart = total_cr - est
            signe = '+' if ecart > 0 else ''
            t.calc_ecart_lbl = f"{signe}{_format_minutes(abs(ecart))}" if ecart else '0 min'
        else:
            t.calc_ecart_lbl = '—'

        for cr in crs:
            cr.calc_duree_lbl = _format_minutes(cr.duree_minutes or 0)

    return taches

# ═══════════════════════════════════════════════════════════
#  DASHBOARD / LISTES (lecture)
# ═══════════════════════════════════════════════════════════

@resp_atelier_required
def dashboard_atelier(request):
    atelier = get_atelier_du_resp(request.user)
    if not atelier:
        messages.error(request, "Aucun atelier ne vous est assigné comme responsable.")
        return redirect('dashboard_technicien')

    today = timezone.localdate()
    ors_actifs = list(
        OrdreReparation.objects
        .filter(
            ateliers=atelier,
            statut__in=[StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT],
        )
        .select_related('vehicule', 'vehicule__client', 'reception')
        .prefetch_related('taches', 'ateliers')
        .order_by('-date_creation')
    )
    taches_a_valider = (
        Tache.objects
        .filter(atelier=atelier, statut=StatutTache.TERMINEE)
        .select_related('ordre_reparation__vehicule', 'valide_par')
        .prefetch_related('techniciens', 'comptes_rendus')
        .order_by('date_fin')
    )
    or_clotures_recents = (
        OrdreReparation.objects
        .filter(ateliers=atelier, statut=StatutOR.CLOTURE)
        .select_related('vehicule')
        .order_by('-date_cloture')[:6]
    )
    Vehicule_controle = (
        Reception.objects
        .filter(statut=StatutVehicule.RAPPORT_FAIT)
        .select_related('vehicule', 'vehicule__client')
        .order_by('-created_at')[:5]
    )
    Vehicule_mecanique = (
        Reception.objects
        .filter(statut=StatutVehicule.FICHE_CONTROLE)
        .select_related('vehicule', 'vehicule__client')
        .order_by('-created_at')[:5]
    )
    stats = {
        'or_ouverts': sum(1 for o in ors_actifs if o.statut == StatutOR.OUVERT),
        'or_en_cours': sum(1 for o in ors_actifs if o.statut == StatutOR.EN_COURS),
        'a_valider': taches_a_valider.count(),
        'termine_today': Tache.objects.filter(
            atelier=atelier,
            statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE],
            date_fin__date=today,
        ).count(),
    }
    return render(request, 'atelier/resp/dashboard.html', {
        'atelier': atelier,
        'ors_actifs': ors_actifs[:6],
        'taches_a_valider': taches_a_valider[:6],
        'stats': stats,
        'Vehicule_controle': Vehicule_controle,
        'Vehicule_mecanique': Vehicule_mecanique,
        'or_clotures_recents': or_clotures_recents,
        'today': today,
    })


@resp_atelier_required
def liste_or_atelier(request):
    atelier = get_atelier_du_resp(request.user)
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()
    qs = (
        OrdreReparation.objects
        .filter(ateliers=atelier)
        .select_related('vehicule', 'vehicule__client')
        .prefetch_related('taches')
    )
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(numero__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )
    ors = list(qs.order_by('statut', '-urgence', 'date_creation'))
    return render(request, 'atelier/resp/liste_or.html', {
        'atelier': atelier, 'ors': ors, 'statut': statut, 'q': q,
    })

@resp_atelier_required
def detail_or_atelier(request, or_id):
    atelier = get_atelier_du_resp(request.user)

    or_obj = get_object_or_404(
        OrdreReparation.objects
        .select_related('vehicule', 'vehicule__client', 'reception')
        .prefetch_related('ateliers'),
        id=or_id,
        ateliers=atelier,
    )

    entree = _entree_from_or(or_obj)
    fiche_controle  = getattr(entree, 'fiche_controle',  None) if entree else None
    fiche_technique = getattr(entree, 'fiche_technique', None) if entree else None

    taches = list(
        or_obj.taches
        .select_related('atelier', 'valide_par', 'created_by')
        .prefetch_related('techniciens', 'comptes_rendus')
        .order_by('created_at')
    )
    enrich_taches_duree(taches)

    nb_a_valider = sum(1 for t in taches if t.statut == StatutTache.TERMINEE)
    nb_validees  = sum(1 for t in taches if t.statut == StatutTache.VALIDEE)

    reouvertures = or_obj.reouvertures.select_related('reouvert_par', 'tache')

    return render(request, 'atelier/resp/detail_or.html', {
        'or':              or_obj,
        'atelier':         atelier,
        'entree':          entree,
        'fiche_controle':  fiche_controle,
        'fiche_technique': fiche_technique,
        'taches':          taches,
        'nb_a_valider':    nb_a_valider,          # ← ajouté
        'nb_validees':     nb_validees,
        'stats':           or_obj.stats_pour_atelier,   # ← corrigé (au lieu de description_travaux)
        'reouvertures':    reouvertures,
        'techniciens':     techniciens_assignables(atelier, request.user),
    })

# ═══════════════════════════════════════════════════════════
#  TÂCHES — mutations + audit
# ═══════════════════════════════════════════════════════════

@resp_atelier_required
def creer_modifier_tache(request, or_id):
    atelier = get_atelier_du_resp(request.user)
    or_obj = get_object_or_404(
        OrdreReparation.objects.prefetch_related('ateliers'),
        id=or_id, ateliers=atelier,
    )
    entree = _entree_from_or(or_obj)
    if entree is None or not FicheTechnique.objects.filter(entre=entree).exists():
        messages.error(request, "⚠️ Créez d'abord la fiche technique.")
        return redirect('detail_or_atelier', or_id=or_id)

    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=or_id)

    tache_id = request.POST.get('tache_id', '').strip()
    libelle = request.POST.get('libelle', '').strip()
    if not libelle:
        messages.error(request, "Le libellé de la tâche est obligatoire.")
        return redirect('detail_or_atelier', or_id=or_id)

    heures = request.POST.get('duree_heures', '0').strip()
    minutes = request.POST.get('duree_minutes', '0').strip()
    heures = int(heures) if heures.isdigit() else 0
    minutes = int(minutes) if minutes.isdigit() else 0
    if minutes > 59:
        minutes = 59

    duree = max(heures * 60 + minutes, 1)  # stocké en minutes en base

    priorite = request.POST.get('priorite', 'NORMALE')
    description = request.POST.get('description', '').strip()
    tech_id = request.POST.get('technicien_id', '').strip()
    technicien = User.objects.filter(id=tech_id).first() if tech_id else None

    if tache_id:
        t = get_object_or_404(Tache, id=tache_id, ordre_reparation=or_obj)
        t.libelle = libelle
        t.duree_estimee_minutes = duree
        t.priorite = priorite
        t.description = description
        if technicien:
            t.techniciens.set([technicien])
            t.date_assignation = timezone.now()
        t.save()
        log_action(request, ActionType.MODIFICATION, 'ATELIER', t, {
            'libelle': libelle, 'or': or_obj.numero,
        })
        messages.success(request, f"Tâche « {libelle} » modifiée.")
    else:
        t = Tache.objects.create(
            ordre_reparation=or_obj,
            atelier=atelier,
            libelle=libelle,
            duree_estimee_minutes=duree,
            priorite=priorite,
            description=description,
            date_assignation=timezone.now() if technicien else None,
            created_by=request.user,
        )
        if technicien:
            t.techniciens.set([technicien])
        if or_obj.statut == StatutOR.OUVERT:
            or_obj.statut = StatutOR.EN_COURS
            or_obj.save(update_fields=['statut'])
            log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {
                'statut': 'EN_COURS',
            })
        log_action(request, ActionType.CREATION, 'ATELIER', t, {
            'libelle': libelle, 'or': or_obj.numero,
        })
        messages.success(request, f"Tâche « {libelle} » créée.")

    return redirect('detail_or_atelier', or_id=or_id)


@resp_atelier_required
def supprimer_tache(request, tache_id):
    atelier = get_atelier_du_resp(request.user)
    t = get_object_or_404(
        Tache, id=tache_id, atelier=atelier, statut=StatutTache.A_FAIRE,
    )
    or_id = t.ordre_reparation_id
    libelle = t.libelle
    log_action(request, ActionType.SUPPRESSION, 'ATELIER', t, {
        'libelle': libelle, 'or_id': str(or_id),
    })
    t.delete()
    messages.success(request, "Tâche supprimée.")
    return redirect('detail_or_atelier', or_id=or_id)


@resp_atelier_required
def valider_tache_chef(request, tache_id):
    atelier = get_atelier_du_resp(request.user)
    t = get_object_or_404(
        Tache, id=tache_id, atelier=atelier, statut=StatutTache.TERMINEE,
    )

    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=t.ordre_reparation_id)

    # ── Signature obligatoire ──


    from django.db import transaction

    with transaction.atomic():
        # ══════════════════════════════════════════════════════════
        #  1) Valider la tâche
        # ══════════════════════════════════════════════════════════
        t.statut                 = StatutTache.VALIDEE
        t.valide_par             = request.user
        t.date_validation        = timezone.now()
        t.commentaire_validation = request.POST.get('commentaire_validation', '').strip()
        t.save(update_fields=[
            'statut', 'valide_par', 'date_validation',
            'commentaire_validation', 'signature_chef',
        ])

        log_action(
            request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t,
            {'statut': 'VALIDEE', 'libelle': t.libelle},
        )

        # ══════════════════════════════════════════════════════════
        #  2) Recalculer la durée réelle de l'OR
        #     (mais PAS de clôture automatique)
        # ══════════════════════════════════════════════════════════
        or_obj = t.ordre_reparation
        or_obj.recalculer_duree_reelle(save=True)

        # Message contextuel
        stats = or_obj.stats_globales()
        reste = stats['total'] - stats['validees']

        if reste == 0:
            messages.success(
                request,
                f"✅ Tâche « {t.libelle} » validée. "
                f"Toutes les tâches sont validées — "
                f"vous pouvez maintenant clôturer l'OR."
            )
        else:
            messages.success(
                request,
                f"✅ Tâche « {t.libelle} » validée et signée. "
                f"({stats['validees']}/{stats['total']} — "
                f"{reste} tâche{'s' if reste > 1 else ''} restante{'s' if reste > 1 else ''})"
            )

    return redirect('detail_or_atelier', or_id=t.ordre_reparation_id)

@resp_atelier_required
def cloture_directe_tache(request, tache_id):
    atelier = get_atelier_du_resp(request.user)
    t = get_object_or_404(Tache, id=tache_id, atelier=atelier)

    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=t.ordre_reparation_id)

    # ── Technicien ──
    tech_id = request.POST.get('technicien_id', '').strip()
    technicien = User.objects.filter(id=tech_id).first() if tech_id else None
    if technicien is None:
        technicien = t.techniciens.first()

    # ── Durée (parse_duree_hm retourne déjà un int) ──
    duree = parse_duree_hm(
        request,
        'duree_reelle_heures',
        'duree_reelle_minutes',
        default=t.duree_estimee_minutes or 60,
    )

    description = request.POST.get('description', '').strip()
    pieces      = request.POST.get('pieces_utilisees', '').strip()
    now = timezone.now()

    from django.db import transaction

    with transaction.atomic():
        # ── Assigner le technicien ──
        if technicien:
            t.techniciens.set([technicien])

        # ── Créer le compte rendu AVANT de modifier la tâche ──
        cr = CompteRendu.objects.create(
            tache=t,
            technicien=technicien,
            description=description,
            pieces_utilisees=pieces,
            duree_minutes=duree,
            saisie_par_chef=True,
        )

        # ── Mettre à jour la tâche ──
        t.statut                 = StatutTache.VALIDEE
        t.date_debut             = t.date_debut or now
        t.date_fin               = now
        t.valide_par             = request.user
        t.date_validation        = now
        t.cloturee_manuellement  = True
        t.commentaire_validation = "Clôturée directement par le responsable d'atelier."

        # ⚠️ La durée réelle = SOMME des comptes rendus
        t.recalculer_duree_reelle(save=False)

        t.save()

        # ── Recalculer la durée réelle de l'OR ──
        t.ordre_reparation.recalculer_duree_reelle(save=True)

    # ── Log ──
    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {
        'statut':    'VALIDEE',
        'mode':      'cloture_directe',
        'libelle':   t.libelle,
        'technicien': str(technicien.id) if technicien else None,
    })

    messages.success(request, f"🔒 Tâche « {t.libelle} » clôturée directement.")
    return redirect('detail_or_atelier', or_id=t.ordre_reparation_id)

@resp_atelier_required
def cloture_or_atelier(request, or_id):
    atelier = get_atelier_du_resp(request.user)
    or_obj = get_object_or_404(OrdreReparation, id=or_id, ateliers=atelier)

    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=or_id)

    non_validees = or_obj.taches.exclude(statut=StatutTache.VALIDEE).count()
    if non_validees > 0:
        messages.error(
            request,
            f"⚠️ {non_validees} tâche(s) non validée(s). Impossible de clôturer.",
        )
        return redirect('detail_or_atelier', or_id=or_id)

    or_obj.statut = StatutOR.CLOTURE
    or_obj.date_cloture = timezone.now()
    or_obj.save(update_fields=['statut', 'date_cloture'])

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {
        'statut': 'CLOTURE', 'numero': or_obj.numero,
    })
    messages.success(request, f"✅ OR {or_obj.numero} clôturé.")
    return redirect('detail_or_atelier', or_id=or_id)


@resp_atelier_required
def reouverture_or_atelier(request, or_id):
    atelier = get_atelier_du_resp(request.user)
    or_obj = get_object_or_404(
        OrdreReparation, id=or_id, ateliers=atelier, statut=StatutOR.CLOTURE,
    )
    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=or_id)

    raison = request.POST.get('raison', '').strip()
    if not raison:
        messages.error(request, "La raison de la réouverture est obligatoire.")
        return redirect('detail_or_atelier', or_id=or_id)

    tache_id = request.POST.get('tache_id', '').strip()
    tache = (
        Tache.objects.filter(id=tache_id, ordre_reparation=or_obj).first()
        if tache_id else None
    )

    or_obj.statut = StatutOR.REOUVERT
    or_obj.save(update_fields=['statut'])

    if tache:
        tache.statut = StatutTache.A_FAIRE
        tache.date_debut = None
        tache.date_fin = None
        tache.date_validation = None
        tache.valide_par = None
        tache.save()

    ReouvertureOR.objects.create(
        ordre_reparation=or_obj,
        tache=tache,
        raison=raison,
        reouvert_par=request.user,
    )

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {
        'statut': 'REOUVERT', 'raison': raison, 'numero': or_obj.numero,
    })
    messages.success(request, f"🔓 OR {or_obj.numero} réouvert.")
    return redirect('detail_or_atelier', or_id=or_id)


# ═══════════════════════════════════════════════════════════
#  TECHNICIEN — mutations + audit
# ═══════════════════════════════════════════════════════════

@technicien_required
def demarrer_tache(request, tache_id):
    t = get_object_or_404(
        Tache, id=tache_id, techniciens=request.user, statut=StatutTache.A_FAIRE,
    )


    t.date_debut = timezone.now()
    t.statut = StatutTache.EN_COURS
    t.save(update_fields=['date_debut', 'statut'])

    or_obj = t.ordre_reparation
    if or_obj.statut == StatutOR.OUVERT:
        or_obj.statut = StatutOR.EN_COURS
        or_obj.save(update_fields=['statut'])
        log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {
            'statut': 'EN_COURS',
        })

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {
        'statut': 'EN_COURS', 'libelle': t.libelle,
    })
    messages.success(request, f"▶️ Tâche « {t.libelle} » démarrée.")
    return redirect('detail_tache', tache_id=tache_id)

@technicien_required
def soumettre_compte_rendu(request, tache_id):
    t = get_object_or_404(
        Tache,
        id=tache_id,
        techniciens=request.user,
        statut__in=[StatutTache.EN_COURS, StatutTache.A_FAIRE],
    )

    if request.method != 'POST':
        return redirect('detail_tache', tache_id=tache_id)

    description = request.POST.get('description', '').strip()
    if not description:
        messages.error(request, "La description est obligatoire.")
        return redirect('detail_tache', tache_id=tache_id)

    pieces       = request.POST.get('pieces_utilisees', '').strip()
    observations = request.POST.get('observations', '').strip()
    action       = request.POST.get('action', 'sauvegarder')

    # ── Parsing de la durée ──
    if 'duree_heures' in request.POST or 'duree_minutes' in request.POST:
        duree = parse_duree_hm(
            request,
            'duree_heures', 'duree_minutes',
            default=t.duree_estimee_minutes or 60,
        )
    else:
        raw = request.POST.get('duree_minutes', '').strip()
        duree = int(raw) if raw.isdigit() else (t.duree_estimee_minutes or 60)

    from django.db import transaction

    with transaction.atomic():
        # ══════════════════════════════════════════════════════════
        #  1) Créer le compte rendu
        # ══════════════════════════════════════════════════════════
        cr = CompteRendu.objects.create(
            tache=t,
            technicien=request.user,
            description=description,
            pieces_utilisees=pieces,
            observations=observations,
            duree_minutes=duree,
        )
        log_action(
            request, ActionType.CREATION, 'ATELIER', cr,
            {'tache': t.libelle, 'action': action},
        )

        # ══════════════════════════════════════════════════════════
        #  2) Recalculer la durée réelle de la tâche
        #     = SOMME de tous les comptes rendus (pas seulement le dernier)
        # ══════════════════════════════════════════════════════════
        t.recalculer_duree_reelle(save=False)

        # ══════════════════════════════════════════════════════════
        #  3) Action
        # ══════════════════════════════════════════════════════════
        if action == 'terminer':
            # ── Terminer la tâche ──
            t.statut = StatutTache.TERMINEE
            t.date_fin = timezone.now()
            t.save(update_fields=[
                'statut', 'date_fin', 'duree_reelle_minutes',
            ])

            # Recalculer la durée réelle totale de l'OR
            t.ordre_reparation.recalculer_duree_reelle(save=True)

            log_action(
                request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t,
                {'statut': 'TERMINEE', 'libelle': t.libelle},
            )
            messages.success(
                request,
                "✅ Tâche terminée. En attente de validation par le responsable.",
            )

        else:
            # ── Sauvegarder le brouillon ──
            # Si la tâche était A_FAIRE, la passer EN_COURS automatiquement
            if t.statut == StatutTache.A_FAIRE:
                t.statut = StatutTache.EN_COURS
                t.date_debut = t.date_debut or timezone.now()
                t.save(update_fields=['statut', 'date_debut', 'duree_reelle_minutes'])
            else:
                t.save(update_fields=['duree_reelle_minutes'])

            # Recalculer la durée réelle totale de l'OR
            t.ordre_reparation.recalculer_duree_reelle(save=True)

            messages.success(request, "💾 Compte rendu sauvegardé.")

    return redirect('detail_tache', tache_id=tache_id)
# ═══════════════════════════════════════════════════════════
#  RÉCEPTIONS (atelier)
# ═══════════════════════════════════════════════════════════

@resp_atelier_required
def detail_reception(request, rec_id):
    rec = get_object_or_404(
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'entree', 'receptionniste')
        .prefetch_related('transferts__atelier'),
        id=rec_id,
    )
    or_list = (
        OrdreReparation.objects
        .filter(reception=rec)
        .prefetch_related('ateliers', 'taches')
        .order_by('-date_creation')
    )
    bon_sortie = BonSortie.objects.filter(
        vehicule=rec.vehicule, reception=rec,
    ).first()

    entree = getattr(rec, 'entree', None)
    fiche_controle = getattr(entree, 'fiche_controle', None) if entree else None
    fiche_technique = getattr(entree, 'fiche_technique', None) if entree else None

    technicien_a_signe = bool(
        fiche_controle
        and fiche_controle.signature_technicien
        and str(fiche_controle.signature_technicien).strip()
    )
    technicien_a_signe_technique = bool(
        fiche_technique
        and fiche_technique.signature_controleur
        and str(fiche_technique.signature_controleur).strip()
    )
    client_a_signe = bool(
        fiche_controle and fiche_controle.signature_client_avant
    )
    signature_apres_faite = bool(
        fiche_controle
        and fiche_controle.signature_client_apres
        and str(fiche_controle.signature_client_apres).strip()
)

    return render(request, 'atelier/resp/detail_reception.html', {
        'rec': rec,
        'or_list': or_list,
        'bon_sortie': bon_sortie,
        'fiche_controle': fiche_controle,
        'fiche_technique': fiche_technique,
        'a_fiche_controle': technicien_a_signe,
        'a_fiche_technique': technicien_a_signe_technique,
        'client_a_signe': client_a_signe,
        'signature_apres_faite':  signature_apres_faite, 
    })


@resp_atelier_required
def liste_receptions(request):
    qs = (
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'receptionniste')
        .select_related('ordre_reparation')
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
#  FICHES contrôle / technique
# ═══════════════════════════════════════════════════════════

@resp_atelier_required
def creer_fiche_controle(request, rec_id):
    """rec_id = id OrdreReparation."""
    atelier = get_atelier_du_resp(request.user)
    if atelier is None:
        messages.error(request, "Aucun atelier ne vous est assigné.")
        return redirect('dashboard_atelier')

    or_obj = (
        OrdreReparation.objects
        .filter(id=rec_id)
        .select_related('vehicule', 'reception')
        .prefetch_related('ateliers')
        .first()
    )
    if or_obj is None:
        messages.error(request, "Ordre de réparation introuvable.")
        return redirect('dashboard_atelier')

    if not or_obj.ateliers.filter(id=atelier.id).exists():
        messages.error(request, "Cet OR n'appartient pas à votre atelier.")
        return redirect('dashboard_atelier')

    entree = _entree_from_or(or_obj)
    if entree is None:
        messages.error(request, "Aucune entrée guérite liée à cette réception.")
        return redirect('detail_or_atelier', or_id=rec_id)

    fiche = FicheControle.objects.filter(entree=entree).first()

    if request.method == 'POST':
        kilometrage = request.POST.get('kilometrage', '0').strip()
        km_value = int(kilometrage) if kilometrage.isdigit() else 0

        if fiche:
            fiche.kilometrage = km_value or fiche.kilometrage
            fiche.etat_general = request.POST.get('etat_general', fiche.etat_general)
            fiche.defauts_observes = request.POST.get('defauts_observes', '').strip()
            fiche.commentaires = request.POST.get('commentaires', '').strip()
            fiche.travail_a_effectuer = request.POST.get(
                'travail_a_effectuer', fiche.travail_a_effectuer
            )
            fiche.save()
            log_action(request, ActionType.MODIFICATION, 'ATELIER', fiche, {
                'or': or_obj.numero, 'type': 'fiche_controle',
            })
            messages.success(request, "✅ Fiche de contrôle mise à jour.")
        else:
            fiche = FicheControle.objects.create(
                entree=entree,
                immatriculation=or_obj.vehicule.immatriculation,
                kilometrage=km_value,
                etat_general=request.POST.get('etat_general', 'BON'),
                defauts_observes=request.POST.get('defauts_observes', '').strip(),
                commentaires=request.POST.get('commentaires', '').strip(),
                travail_a_effectuer=request.POST.get('travail_a_effectuer', '').strip(),
                inspecte_par=request.user,
            )
            if or_obj.statut == StatutOR.OUVERT:
                or_obj.statut = StatutOR.EN_COURS
                or_obj.save(update_fields=['statut'])
            log_action(request, ActionType.CREATION, 'ATELIER', fiche, {
                'or': or_obj.numero, 'type': 'fiche_controle',
            })
            messages.success(request, "✅ Fiche de contrôle créée.")

        return redirect('detail_or_atelier', or_id=rec_id)

    return render(request, 'atelier/resp/fiche_controle.html', {
        'or': or_obj, 'entree': entree, 'fiche': fiche,
    })


@resp_atelier_required
def creer_fiche_technique(request, rec_id):
    atelier = get_atelier_du_resp(request.user)
    or_obj = get_object_or_404(
        OrdreReparation.objects.prefetch_related('ateliers'),
        id=rec_id, ateliers=atelier,
    )
    entree = _entree_from_or(or_obj)
    if entree is None:
        messages.error(request, "Aucune entrée guérite liée.")
        return redirect('detail_or_atelier', or_id=rec_id)

    if not FicheControle.objects.filter(entree=entree).exists():
        messages.error(request, "⚠️ La fiche de contrôle doit être créée avant.")
        return redirect('detail_or_atelier', or_id=rec_id)

    # Adapte 'entre' / 'entree' selon ton modèle
    fiche = FicheTechnique.objects.filter(entre=entree).first()

    if request.method == 'POST':
        diagnostic = request.POST.get('diagnostic', '').strip()
        if not diagnostic:
            messages.error(request, "Le diagnostic est obligatoire.")
            return redirect('creer_fiche_technique', rec_id=rec_id)

        def to_dec(name):
            v = request.POST.get(name, '0').strip()
            try:
                return float(v)
            except ValueError:
                return 0

        if fiche:
            fiche.diagnostic = diagnostic
            fiche.pieces_recommandees = request.POST.get('pieces_recommandees', '').strip()
            fiche.temps_estime_heures = to_dec('temps_estime_heures')
            fiche.main_oeuvre_estimee = to_dec('main_oeuvre_estimee')
            fiche.pieces_estimees = to_dec('pieces_estimees')
            fiche.observations = request.POST.get('observations', '').strip()
            fiche.save()
            log_action(request, ActionType.MODIFICATION, 'ATELIER', fiche, {
                'or': or_obj.numero, 'type': 'fiche_technique',
            })
            messages.success(request, "✅ Fiche technique mise à jour.")
        else:
            fiche = FicheTechnique.objects.create(
                entre=entree,
                immatriculation=or_obj.vehicule.immatriculation,
                diagnostic=diagnostic,
                pieces_recommandees=request.POST.get('pieces_recommandees', '').strip(),
                temps_estime_heures=to_dec('temps_estime_heures'),
                main_oeuvre_estimee=to_dec('main_oeuvre_estimee'),
                pieces_estimees=to_dec('pieces_estimees'),
                observations=request.POST.get('observations', '').strip(),
                cree_par=request.user,
            )
            log_action(request, ActionType.CREATION, 'ATELIER', fiche, {
                'or': or_obj.numero, 'type': 'fiche_technique',
            })
            messages.success(request, "✅ Fiche technique créée.")

        return redirect('detail_or_atelier', or_id=rec_id)

    return render(request, 'atelier/resp/fiche_technique.html', {
        'or': or_obj, 'entree': entree, 'fiche': fiche,
    })



@technicien_required
def dashboard_technicien(request):
    today = timezone.localdate()

    # ══════════════════════════════════════════════════════════════
    #  Tâche en cours
    # ══════════════════════════════════════════════════════════════
    tache_en_cours = (
        Tache.objects
        .filter(techniciens=request.user, statut=StatutTache.EN_COURS)
        .select_related('ordre_reparation__vehicule', 'atelier')
        .prefetch_related('comptes_rendus', 'comptes_rendus__technicien')
        .first()
    )
    if tache_en_cours:
        enrich_taches_duree([tache_en_cours])

    # ══════════════════════════════════════════════════════════════
    #  Tâches à faire
    # ══════════════════════════════════════════════════════════════
    taches_a_faire = list(
        Tache.objects
        .filter(techniciens=request.user, statut=StatutTache.A_FAIRE)
        .select_related('ordre_reparation__vehicule', 'atelier')
        .prefetch_related('comptes_rendus', 'comptes_rendus__technicien')
        .order_by('-priorite', 'created_at')
    )
    enrich_taches_duree(taches_a_faire)

    # ══════════════════════════════════════════════════════════════
    #  Tâches terminées aujourd'hui
    # ══════════════════════════════════════════════════════════════
    taches_today = list(
        Tache.objects
        .filter(
            techniciens=request.user,
            statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE],
            date_fin__date=today,
        )
        .select_related('ordre_reparation__vehicule', 'atelier')
        .prefetch_related('comptes_rendus', 'comptes_rendus__technicien')
        .order_by('-date_fin')
    )
    enrich_taches_duree(taches_today)

    # ══════════════════════════════════════════════════════════════
    #  Stats
    # ══════════════════════════════════════════════════════════════
    stats = {
        'en_cours':        1 if tache_en_cours else 0,
        'a_faire':         len(taches_a_faire),
        'terminees_today': len(taches_today),
    }

    return render(request, 'atelier/technicien/dashboard.html', {
        'tache_en_cours':        tache_en_cours,
        'taches_a_faire':        taches_a_faire,
        'taches_terminees_today': taches_today,
        'stats':                 stats,
        'today':                 today,
    })



@technicien_required
def mes_taches(request):
    statut = request.GET.get('statut', '').strip()

    qs = (
        Tache.objects
        .filter(techniciens=request.user)
        .select_related('ordre_reparation__vehicule', 'atelier')
        .prefetch_related('comptes_rendus', 'comptes_rendus__technicien')
    )

    if statut:
        qs = qs.filter(statut=statut)

    taches = list(
        qs.order_by('statut', '-priorite', 'created_at')
    )

    # ── Enrichissement complet (durées + écart + CR) ──
    enrich_taches_duree(taches)

    # ── Compteurs par statut ──
    total_par_statut = {
        'tous':     len(taches),
        'a_faire':  sum(1 for t in taches if t.statut == StatutTache.A_FAIRE),
        'en_cours': sum(1 for t in taches if t.statut == StatutTache.EN_COURS),
        'terminee': sum(1 for t in taches if t.statut == StatutTache.TERMINEE),
        'validee':  sum(1 for t in taches if t.statut == StatutTache.VALIDEE),
    }

    return render(request, 'atelier/technicien/mes_taches.html', {
        'taches':           taches,
        'statut':           statut,
        'total_par_statut': total_par_statut,
    })

@technicien_required
def detail_tache(request, tache_id):
    t = get_object_or_404(
        Tache.objects
        .select_related(
            'ordre_reparation',
            'ordre_reparation__vehicule',
            'ordre_reparation__reception',
            'atelier',
            'valide_par',
            'created_by',
        )
        .prefetch_related(
            'techniciens',
            'comptes_rendus',
            'comptes_rendus__technicien',
        ),
        id=tache_id,
        techniciens=request.user,
    )

    # ── Enrichissement des durées (évite les N+1) ──
    enrich_taches_duree([t])

    # ── Comptes rendus triés ──
    crs = sorted(
        t.comptes_rendus.all(),
        key=lambda cr: cr.date_saisie,
        reverse=True,
    )

    return render(request, 'atelier/technicien/detail_tache.html', {
        'tache':          t,
        'comptes_rendus': crs,
    })

# ═══════════════════════════════════════════════════════════
#  LISTE / DÉTAIL TECHNICIENS
# ═══════════════════════════════════════════════════════════

@resp_atelier_required
def liste_techniciens(request):
    q = request.GET.get('q', '').strip()
    qs = User.objects.filter(role='TECHNICIEN', is_active=True)
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(email__icontains=q)
        )
    techniciens = []
    for tech in qs.order_by('nom', 'prenom'):
        taches = Tache.objects.filter(techniciens=tech)
        tech.nb_total = taches.count()
        tech.nb_validees = taches.filter(statut=StatutTache.VALIDEE).count()
        tech.nb_en_cours = taches.filter(statut=StatutTache.EN_COURS).count()
        tech.nb_a_faire = taches.filter(statut=StatutTache.A_FAIRE).count()
        techniciens.append(tech)
    return render(request, 'atelier/resp/liste_techniciens.html', {
        'techniciens': techniciens, 'q': q,
    })


@resp_atelier_required
def detail_technicien(request, tech_id):
    tech = get_object_or_404(User, id=tech_id, role='TECHNICIEN')
    taches_faites = (
        Tache.objects
        .filter(techniciens=tech, statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE])
        .select_related('ordre_reparation__vehicule', 'atelier')
        .order_by('-date_fin')
    )
    taches_restantes = (
        Tache.objects
        .filter(techniciens=tech, statut__in=[StatutTache.A_FAIRE, StatutTache.EN_COURS])
        .select_related('ordre_reparation__vehicule', 'atelier')
        .order_by('-priorite')
    )
    durees_reelles = [t.duree_reelle_minutes for t in taches_faites if t.duree_reelle_minutes]
    delais_demarrage = [
        t.delai_avant_demarrage_minutes for t in taches_faites
        if getattr(t, 'delai_avant_demarrage_minutes', None) is not None
    ]
    nb_retard = sum(1 for t in taches_faites if getattr(t, 'en_retard', False))
    durees_total = sum(durees_reelles) if durees_reelles else 0
    duree_moyenne = round(sum(durees_reelles) / len(durees_reelles), 1) if durees_reelles else 0
    delai_moyen = (
        round(sum(delais_demarrage) / len(delais_demarrage), 1)
        if delais_demarrage else 0
    )
    stats = {
        'nb_effectuees': taches_faites.count(),
        'nb_restantes': taches_restantes.count(),
        'nb_en_retard': nb_retard,
        'duree_totale': format_duree(durees_total),
        'duree_moyenne': format_duree(duree_moyenne),
        'delai_moyen_demarrage': format_duree(delai_moyen),
    }
    return render(request, 'atelier/resp/detail_technicien.html', {
        'tech': tech,
        'taches_faites': taches_faites,
        'taches_restantes': taches_restantes,
        'stats': stats,
    })


# ═══════════════════════════════════════════════════════════
#  Variante OR / tâche (si encore utilisée dans urls)
# ═══════════════════════════════════════════════════════════

def _mon_atelier(user):
    return Atelier.objects.filter(responsable=user, is_active=True).first()



@resp_atelier_required
def creer_tache(request, or_id):
    mon_atelier = _mon_atelier(request.user)
    or_obj = get_object_or_404(OrdreReparation, id=or_id, ateliers=mon_atelier)

    if request.method != 'POST':
        return redirect('detail_or_atelier', or_id=or_id)

    libelle = request.POST.get('libelle', '').strip()
    if not libelle:
        messages.error(request, "Le libellé de la tâche est obligatoire.")
        return redirect('detail_or_atelier', or_id=or_id)

    duree = parse_duree_hm(request, 'duree_heures', 'duree_minutes', default=60)
    tech_ids = request.POST.getlist('techniciens')

    tache = Tache.objects.create(
        ordre_reparation=or_obj,
        atelier=mon_atelier,
        libelle=libelle,
        description=request.POST.get('description', '').strip(),
        duree_estimee_minutes=duree,
        priorite=request.POST.get('priorite', 'NORMALE'),
        created_by=request.user,
    )
    if tech_ids:
        tache.techniciens.set(User.objects.filter(id__in=tech_ids, role=ROLE_TECH))

    log_action(request, ActionType.CREATION, 'ATELIER', tache, {
        'libelle': libelle, 'or': or_obj.numero, 'duree_min': duree,
    })
    messages.success(request, f"✅ Tâche « {libelle} » créée.")
    return redirect('detail_or_atelier', or_id=or_id)