"""
Tâches côté responsable : création, modification, suppression, validation,
refus (révocation), clôture directe.

Règles :
- OR clôturé  → aucune action possible (seule la réouverture le débloque) ;
- modifier    → tâche non démarrée (A_FAIRE) ;
- supprimer   → tâche non démarrée, sans compte rendu, jamais réouverte, en POST ;
- refuser     → tâche TERMINEE : elle repasse EN_COURS avec un motif.
"""
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from apps.accounts.decorators_atelier import resp_atelier_required
from apps.accounts.models import User
from apps.atelier.models import (
    CompteRendu, FicheTechnique, OrdreReparation, StatutTache, Tache, TypeRetour,
)
from apps.atelier.roles import ROLE_TECH
from apps.audit.models import ActionType
from apps.audit.service import log_action

from ._utils import (
    _entree_from_or, atelier_requis, get_or_none, get_technicien, lire_priorite,
    parse_duree_hm, passer_or_en_cours, post_str,
)


def _retour_or(or_id):
    return redirect('detail_or_atelier', or_id=or_id)


def _or_verrouille(request, or_obj):
    """True (+ message) si l'OR est clôturé : on ne touche plus à ses tâches."""
    if or_obj.est_cloture:
        messages.error(request, f"🔒 L'OR {or_obj.numero} est clôturé : "
                                f"aucune modification possible. Il doit d'abord être réouvert.")
        return True
    return False


def _nouvelle_tache(request, or_obj, atelier, libelle, duree, techniciens):
    """Création commune à creer_modifier_tache et creer_tache."""
    with transaction.atomic():
        t = Tache.objects.create(
            ordre_reparation=or_obj,
            atelier=atelier,
            libelle=libelle,
            description=post_str(request, 'description'),
            duree_estimee_minutes=duree,
            priorite=lire_priorite(request),
            date_assignation=timezone.now() if techniciens else None,
            created_by=request.user,
        )
        if techniciens:
            t.techniciens.set(techniciens)
        or_obj.recalculer_duree_prevue(save=True)
        passer_or_en_cours(request, or_obj)
    log_action(request, ActionType.CREATION, 'ATELIER', t,
               {'libelle': libelle, 'or': or_obj.numero, 'duree_min': duree})
    return t


@resp_atelier_required
@atelier_requis
def creer_modifier_tache(request, or_id):
    atelier = request.atelier
    or_obj = get_object_or_404(OrdreReparation, id=or_id, ateliers=atelier)
    if request.method != 'POST':
        return _retour_or(or_id)
    if _or_verrouille(request, or_obj):
        return _retour_or(or_id)

    entree = _entree_from_or(or_obj)
    if entree is None or not FicheTechnique.objects.filter(entre=entree).exists():
        messages.error(request, "⚠️ Créez d'abord la fiche technique.")
        return _retour_or(or_id)

    libelle = post_str(request, 'libelle')
    if not libelle:
        messages.error(request, "Le libellé de la tâche est obligatoire.")
        return _retour_or(or_id)

    duree = parse_duree_hm(request, default=1)  # même règle qu'avant : minimum 1 min
    technicien = get_technicien(request, post_str(request, 'technicien_id'))
    tache_id = post_str(request, 'tache_id')

    if not tache_id:
        _nouvelle_tache(request, or_obj, atelier, libelle, duree, [technicien] if technicien else [])
        messages.success(request, f"Tâche « {libelle} » créée.")
        return _retour_or(or_id)

    t = get_or_none(Tache.objects, id=tache_id, ordre_reparation=or_obj, atelier=atelier)
    if t is None:
        messages.error(request, "Tâche introuvable.")
        return _retour_or(or_id)

    # Seule une tâche non démarrée se modifie
    if t.statut != StatutTache.A_FAIRE:
        messages.error(request, f"La tâche « {t.libelle} » a déjà démarré : elle ne peut plus être modifiée.")
        return _retour_or(or_id)

    with transaction.atomic():
        t.libelle = libelle
        t.duree_estimee_minutes = duree
        t.priorite = lire_priorite(request, t.priorite)
        t.description = post_str(request, 'description')
        if technicien:
            t.techniciens.set([technicien])
            t.date_assignation = timezone.now()
        t.save()
        or_obj.recalculer_duree_prevue(save=True)
    log_action(request, ActionType.MODIFICATION, 'ATELIER', t, {'libelle': libelle, 'or': or_obj.numero})
    messages.success(request, f"Tâche « {libelle} » modifiée.")
    return _retour_or(or_id)


@resp_atelier_required
@atelier_requis
def creer_tache(request, or_id):
    """Variante multi-techniciens (conservée pour urls.py)."""
    or_obj = get_object_or_404(OrdreReparation, id=or_id, ateliers=request.atelier)
    if request.method != 'POST':
        return _retour_or(or_id)
    if _or_verrouille(request, or_obj):
        return _retour_or(or_id)

    libelle = post_str(request, 'libelle')
    if not libelle:
        messages.error(request, "Le libellé de la tâche est obligatoire.")
        return _retour_or(or_id)

    tech_ids = [i for i in request.POST.getlist('techniciens') if i.strip()]
    try:
        techs = list(User.objects.filter(id__in=tech_ids, role=ROLE_TECH)) if tech_ids else []
    except ValueError:
        techs = []

    _nouvelle_tache(request, or_obj, request.atelier, libelle,
                    parse_duree_hm(request, default=60), techs)
    messages.success(request, f"✅ Tâche « {libelle} » créée.")
    return _retour_or(or_id)


@resp_atelier_required
@atelier_requis
def supprimer_tache(request, tache_id):
    t = get_object_or_404(Tache.objects.select_related('ordre_reparation'),
                          id=tache_id, atelier=request.atelier)
    or_obj = t.ordre_reparation
    # CORRIGÉ : avant, un simple lien (GET) supprimait la tâche
    if request.method != 'POST':
        return _retour_or(or_obj.id)
    if _or_verrouille(request, or_obj):
        return _retour_or(or_obj.id)

    if t.statut != StatutTache.A_FAIRE:
        messages.error(request, f"La tâche « {t.libelle} » a déjà démarré : suppression impossible.")
        return _retour_or(or_obj.id)
    if not t.est_supprimable:
        messages.error(request, f"La tâche « {t.libelle} » a un historique (comptes rendus ou réouverture) : "
                                f"suppression impossible.")
        return _retour_or(or_obj.id)

    log_action(request, ActionType.SUPPRESSION, 'ATELIER', t, {'libelle': t.libelle, 'or_id': str(or_obj.id)})
    with transaction.atomic():
        t.delete()
        or_obj.recalculer_duree_prevue(save=True)
    messages.success(request, "Tâche supprimée.")
    return _retour_or(or_obj.id)


@resp_atelier_required
@atelier_requis
def valider_tache_chef(request, tache_id):
    t = get_object_or_404(
        Tache.objects.select_related('ordre_reparation'),
        id=tache_id, atelier=request.atelier, statut=StatutTache.TERMINEE,
    )
    if request.method != 'POST':
        return _retour_or(t.ordre_reparation_id)
    if _or_verrouille(request, t.ordre_reparation):
        return _retour_or(t.ordre_reparation_id)

    with transaction.atomic():
        t.statut = StatutTache.VALIDEE
        t.valide_par = request.user
        t.date_validation = timezone.now()
        t.commentaire_validation = post_str(request, 'commentaire_validation')
        # La tâche est refaite et acceptée : elle n'est plus « à reprendre »
        # (les compteurs nb_refus / nb_reouvertures restent pour l'historique)
        t.type_retour = TypeRetour.AUCUN
        t.save(update_fields=['statut', 'valide_par', 'date_validation',
                              'commentaire_validation', 'type_retour'])

        or_obj = t.ordre_reparation
        or_obj.recalculer_duree_reelle(save=True)
        stats = or_obj.stats_globales()

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {'statut': 'VALIDEE', 'libelle': t.libelle})

    reste = stats['total'] - stats['validees']
    if reste == 0:
        messages.success(request, f"✅ Tâche « {t.libelle} » validée. Toutes les tâches sont "
                                  f"validées — vous pouvez maintenant clôturer l'OR.")
    else:
        s = 's' if reste > 1 else ''
        messages.success(request, f"✅ Tâche « {t.libelle} » validée et signée. "
                                  f"({stats['validees']}/{stats['total']} — {reste} tâche{s} restante{s})")
    return _retour_or(t.ordre_reparation_id)


@resp_atelier_required
@atelier_requis
def refuser_tache(request, tache_id):
    """Révoque une tâche terminée : elle repasse EN_COURS chez le technicien,
    avec le motif. Les comptes rendus déjà saisis sont conservés."""
    t = get_object_or_404(
        Tache.objects.select_related('ordre_reparation'),
        id=tache_id, atelier=request.atelier, statut=StatutTache.TERMINEE,
    )
    if request.method != 'POST':
        return _retour_or(t.ordre_reparation_id)
    if _or_verrouille(request, t.ordre_reparation):
        return _retour_or(t.ordre_reparation_id)

    motif = post_str(request, 'motif_refus')
    if not motif:
        messages.error(request, "Le motif du refus est obligatoire.")
        return _retour_or(t.ordre_reparation_id)

    now = timezone.now()
    with transaction.atomic():
        t.statut = StatutTache.EN_COURS
        t.date_fin = None
        t.type_retour = TypeRetour.REFUS
        t.motif_retour = motif
        t.date_retour = now
        t.nb_refus += 1
        t.save(update_fields=['statut', 'date_fin', 'type_retour', 'motif_retour', 'date_retour', 'nb_refus'])

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {
        'statut': 'EN_COURS', 'mode': 'refus', 'libelle': t.libelle, 'motif': motif, 'nb_refus': t.nb_refus,
    })
    messages.warning(request, f"↩️ Tâche « {t.libelle} » refusée : renvoyée au technicien.")
    return _retour_or(t.ordre_reparation_id)


@resp_atelier_required
@atelier_requis
def cloture_directe_tache(request, tache_id):
    t = get_object_or_404(
        Tache.objects.select_related('ordre_reparation'), id=tache_id, atelier=request.atelier)
    if request.method != 'POST':
        return _retour_or(t.ordre_reparation_id)
    if _or_verrouille(request, t.ordre_reparation):
        return _retour_or(t.ordre_reparation_id)

    if t.statut == StatutTache.VALIDEE:
        messages.info(request, f"La tâche « {t.libelle} » est déjà validée.")
        return _retour_or(t.ordre_reparation_id)

    technicien = get_technicien(request, post_str(request, 'technicien_id')) or t.techniciens.first()
    duree = parse_duree_hm(request, 'duree_reelle_heures', 'duree_reelle_minutes',
                           default=t.duree_estimee_minutes or 60)
    now = timezone.now()

    with transaction.atomic():
        if technicien:
            t.techniciens.set([technicien])

        CompteRendu.objects.create(
            tache=t,
            technicien=technicien,
            description=post_str(request, 'description'),
            pieces_utilisees=post_str(request, 'pieces_utilisees'),
            duree_minutes=duree,
            saisie_par_chef=True,
        )

        t.statut = StatutTache.VALIDEE
        t.date_debut = t.date_debut or now
        t.date_fin = now
        t.valide_par = request.user
        t.date_validation = now
        t.cloturee_manuellement = True
        t.commentaire_validation = "Clôturée directement par le responsable d'atelier."
        t.type_retour = TypeRetour.AUCUN
        t.recalculer_duree_reelle(save=False)  # = somme des comptes rendus
        t.save()

        t.ordre_reparation.recalculer_duree_reelle(save=True)

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {
        'statut': 'VALIDEE', 'mode': 'cloture_directe', 'libelle': t.libelle,
        'technicien': str(technicien.id) if technicien else None,
    })
    messages.success(request, f"🔒 Tâche « {t.libelle} » clôturée directement.")
    return _retour_or(t.ordre_reparation_id)
