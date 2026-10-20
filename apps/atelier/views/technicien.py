"""
Espace technicien : dashboard, mes tâches, détail, démarrage, comptes rendus.

Nouveau : les tâches refusées par le responsable ou remises à faire par une
réouverture de l'OR apparaissent comme « À reprendre », avec leur motif.
"""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators_atelier import technicien_required
from apps.atelier.models import CompteRendu, StatutOR, StatutTache, Tache
from apps.audit.models import ActionType
from apps.audit.service import log_action

from ._utils import enrich_taches_duree, parse_duree_hm, passer_or_en_cours, post_str

# Filtre « à reprendre » : revenue au technicien et pas encore refaite
Q_A_REPRENDRE = ~Q(type_retour='') & Q(statut__in=[StatutTache.A_FAIRE, StatutTache.EN_COURS])


def _mes_taches(user):
    return (
        Tache.objects.filter(techniciens=user)
        .select_related('ordre_reparation__vehicule', 'atelier')
        .prefetch_related('comptes_rendus__technicien')
    )


def _taches_actives(user):
    """Tâches sur lesquelles le technicien peut agir : OR non clôturé."""
    return _mes_taches(user).exclude(ordre_reparation__statut=StatutOR.CLOTURE)


@technicien_required
def dashboard_technicien(request):
    today = timezone.localdate()
    base = _mes_taches(request.user)

    tache_en_cours = base.filter(statut=StatutTache.EN_COURS).order_by('-date_retour', 'date_debut').first()
    a_reprendre = list(base.filter(Q_A_REPRENDRE).order_by('-date_retour'))
    # Les tâches à reprendre ont leur propre bloc : on ne les répète pas ici
    a_faire = list(base.filter(statut=StatutTache.A_FAIRE, type_retour='').order_by('-priorite', 'created_at'))
    today_list = list(base.filter(
        statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE], date_fin__date=today,
    ).order_by('-date_fin'))

    enrich_taches_duree(([tache_en_cours] if tache_en_cours else []) + a_faire + today_list + a_reprendre)

    return render(request, 'atelier/technicien/dashboard.html', {
        'tache_en_cours': tache_en_cours,
        'taches_a_reprendre': a_reprendre,
        'taches_a_faire': a_faire,
        'taches_terminees_today': today_list,
        'stats': {
            'en_cours': int(bool(tache_en_cours)),
            'a_reprendre': len(a_reprendre),
            'a_faire': len(a_faire),
            'terminees_today': len(today_list),
        },
        'today': today,
    })


@technicien_required
def mes_taches(request):
    statut = request.GET.get('statut', '').strip()
    base = _mes_taches(request.user)

    if statut == 'A_REPRENDRE':
        qs = base.filter(Q_A_REPRENDRE)
    elif statut:
        qs = base.filter(statut=statut)
    else:
        qs = base
    taches = enrich_taches_duree(list(qs.order_by('statut', '-priorite', 'created_at')))

    compteurs = Tache.objects.filter(techniciens=request.user).aggregate(
        tous=Count('id', distinct=True),
        a_reprendre=Count('id', filter=Q_A_REPRENDRE, distinct=True),
        a_faire=Count('id', filter=Q(statut=StatutTache.A_FAIRE), distinct=True),
        en_cours=Count('id', filter=Q(statut=StatutTache.EN_COURS), distinct=True),
        terminee=Count('id', filter=Q(statut=StatutTache.TERMINEE), distinct=True),
        validee=Count('id', filter=Q(statut=StatutTache.VALIDEE), distinct=True),
    )

    return render(request, 'atelier/technicien/mes_taches.html', {
        'taches': taches,
        'statut': statut,
        'total_par_statut': compteurs,
    })


@technicien_required
def detail_tache(request, tache_id):
    t = get_object_or_404(
        Tache.objects
        .select_related('ordre_reparation', 'ordre_reparation__vehicule', 'ordre_reparation__reception',
                        'atelier', 'valide_par', 'created_by')
        .prefetch_related('techniciens', 'comptes_rendus__technicien'),
        id=tache_id, techniciens=request.user,
    )
    enrich_taches_duree([t])
    return render(request, 'atelier/technicien/detail_tache.html', {
        'tache': t,
        'comptes_rendus': sorted(t.comptes_rendus.all(), key=lambda cr: cr.date_saisie, reverse=True),
    })


@technicien_required
def demarrer_tache(request, tache_id):
    t = get_object_or_404(
        _taches_actives(request.user),
        id=tache_id, statut=StatutTache.A_FAIRE,
    )
    if request.method != 'POST':
        return redirect('detail_tache', tache_id=tache_id)

    with transaction.atomic():
        t.date_debut = timezone.now()
        t.statut = StatutTache.EN_COURS
        t.save(update_fields=['date_debut', 'statut'])
        passer_or_en_cours(request, t.ordre_reparation)

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {'statut': 'EN_COURS', 'libelle': t.libelle})
    messages.success(request, f"▶️ Tâche « {t.libelle} » démarrée.")
    return redirect('detail_tache', tache_id=tache_id)


@technicien_required
def soumettre_compte_rendu(request, tache_id):
    t = get_object_or_404(
        _taches_actives(request.user),
        id=tache_id, statut__in=[StatutTache.EN_COURS, StatutTache.A_FAIRE],
    )
    if request.method != 'POST':
        return redirect('detail_tache', tache_id=tache_id)

    description = post_str(request, 'description')
    if not description:
        messages.error(request, "La description est obligatoire.")
        return redirect('detail_tache', tache_id=tache_id)

    action = request.POST.get('action', 'sauvegarder')
    duree = parse_duree_hm(request, default=t.duree_estimee_minutes or 60)
    now = timezone.now()

    with transaction.atomic():
        cr = CompteRendu.objects.create(
            tache=t,
            technicien=request.user,
            description=description,
            pieces_utilisees=post_str(request, 'pieces_utilisees'),
            observations=post_str(request, 'observations'),
            duree_minutes=duree,
        )
        # Durée réelle = SOMME de tous les comptes rendus
        t.recalculer_duree_reelle(save=False)
        champs = ['duree_reelle_minutes']

        if action == 'terminer':
            t.statut = StatutTache.TERMINEE
            t.date_fin = now
            champs += ['statut', 'date_fin']
        elif t.statut == StatutTache.A_FAIRE:
            t.statut = StatutTache.EN_COURS
            t.date_debut = t.date_debut or now
            champs += ['statut', 'date_debut']
            passer_or_en_cours(request, t.ordre_reparation)

        t.save(update_fields=champs)
        t.ordre_reparation.recalculer_duree_reelle(save=True)

    log_action(request, ActionType.CREATION, 'ATELIER', cr, {'tache': t.libelle, 'action': action})
    if action == 'terminer':
        log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', t, {'statut': 'TERMINEE', 'libelle': t.libelle})
        messages.success(request, "✅ Tâche terminée. En attente de validation par le responsable.")
    else:
        messages.success(request, "💾 Compte rendu sauvegardé.")

    return redirect('detail_tache', tache_id=tache_id)
