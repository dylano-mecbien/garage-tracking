"""
Ordres de réparation : liste, détail, clôture, réouverture.
"""
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.choices import StatutReception, TypeRetour
from apps.accounts.decorators import receptionniste_required
from apps.atelier.models import OrdreReparation, ReouvertureOR, StatutOR, StatutTache, Tache
from apps.atelier.views import _entree_from_or, enrich_taches_duree
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.reception.models import Reception, StatutVehicule
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from ._utils import _notifier


@receptionniste_required
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

    return render(request, 'reception/liste_or.html', {
        'ors': qs.order_by('statut', '-urgence', 'date_creation'),
        'statut': statut,
        'q': q,
    })


@receptionniste_required
def detail_or_rec(request, or_id):
    # Les tâches sont chargées UNE seule fois (avant : prefetch en double)
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
    return render(request, 'reception/detail_or.html', {
        'or': or_obj,
        'entree': entree,
        'fiche_controle': getattr(entree, 'fiche_controle', None),
        'fiche_technique': getattr(entree, 'fiche_technique', None),
        'taches': taches,
        'nb_validees': sum(1 for t in taches if t.statut == StatutTache.VALIDEE),
    })



@receptionniste_required
@require_POST
def date_depot_facture(request, rec_id):
    rec = get_object_or_404(Reception, id=rec_id)

    # ── Le véhicule doit être sorti ──
    if rec.statut != 'SORTI':
        messages.error(request, "Le véhicule doit être sorti pour saisir la date de dépôt.")
        return redirect('detail_reception', rec_id=rec.id)

    # ── Récupération des champs ──
    date_str    = request.POST.get('date_depot_facture', '').strip()
    ref_facture = request.POST.get('reference_facture', '').strip()

    if not date_str:
        messages.error(request, "La date de dépôt est obligatoire.")
        return redirect('detail_reception', rec_id=rec.id)

    # ── Parsing (accepte YYYY-MM-DD et autres formats ISO) ──
    date_depot = parse_date(date_str)
    if date_depot is None:
        messages.error(request, "Date invalide.")
        return redirect('detail_reception', rec_id=rec.id)

    # ── Enregistrement ──
    rec.statut             = StatutReception.FACTURE
    rec.date_depot_facture = date_depot
    rec.reference_facture  = ref_facture
    rec.date_systeme_facture_create = timezone.localdate()  # auto

    rec.save(update_fields=['statut', 'date_depot_facture', 'reference_facture', 'date_systeme_facture_create'])

    log_action(request, ActionType.MODIFICATION, 'RECEPTION', rec, {
        'date_depot_facture': str(date_depot),
        'reference_facture':  ref_facture,
    })

    messages.success(
        request,
        f"Date de dépôt enregistrée : {date_depot.strftime('%d/%m/%Y')}.",
    )
    return redirect('detail_reception', rec_id=rec.id)



@receptionniste_required
def cloture_or(request, or_id):
    o = get_object_or_404(
        OrdreReparation.objects.select_related('vehicule', 'reception'),
        id=or_id,
    )
    if request.method != 'POST':
        return redirect('detail_or_rec', or_id=or_id)

    now = timezone.now()
    with transaction.atomic():
        a_valider = list(o.taches.exclude(statut=StatutTache.VALIDEE))
        for t in a_valider:
            t.date_debut = t.date_debut or now
            t.date_fin = t.date_fin or now
            t.duree_reelle_minutes = t.duree_reelle_minutes or t.duree_estimee_minutes or 0
            t.statut = StatutTache.VALIDEE
            t.valide_par = request.user
            t.date_validation = now
            t.commentaire_validation = (
                t.commentaire_validation
                or "Validée automatiquement à la clôture de l'OR."
            )
            t.save()

        o.duree_totale_minutes = o.taches.aggregate(t=Sum('duree_reelle_minutes'))['t'] or 0
        o.statut = StatutOR.CLOTURE
        o.date_cloture = now
        o.save()

        if o.reception:
            o.reception.statut = StatutVehicule.TRAVAUX_TERMINES
            o.reception.save(update_fields=['statut'])

    if o.reception:
        _notifier(
            'OR_CLOTURE',
            f"OR {o.numero} clôturé",
            f"Travaux terminés sur {o.vehicule.immatriculation}.",
            o.reception,
        )

    log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', o, {
        'statut': 'CLOTURE',
        'nb_taches_auto_validees': len(a_valider),
    })
    messages.success(
        request,
        f"OR {o.numero} clôturé ({len(a_valider)} tâche(s) validée(s)). "
    )

    if o.reception_id:
        return redirect('detail_reception', rec_id=o.reception_id)
    return redirect('detail_or_rec', or_id=o.id)



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




def _reception_actuelle(or_obj):
    """Dernière réception du véhicule (celle en cours), sinon celle d'origine de l'OR."""
    return (
        Reception.objects.filter(vehicule=or_obj.vehicule)
        .order_by('-created_at')
        .first()
    ) or or_obj.reception


@receptionniste_required
def reouverture_or(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id, statut=StatutOR.CLOTURE)

    if request.method != 'POST':
        return redirect('detail_or_rec', or_id=or_id)

    # ── Raison ──
    raison = request.POST.get('raison', '').strip()
    if not raison:
        messages.error(request, "La raison de la réouverture est obligatoire.")
        return redirect('detail_or_rec', or_id=or_id)

    # ── Tâches à refaire (cases à cocher name="taches") ──
    tache_ids = [t for t in request.POST.getlist('taches') if t.strip()]
    taches = list(Tache.objects.filter(id__in=tache_ids, ordre_reparation=or_obj))
    if not taches:
        messages.error(request, "Sélectionnez au moins une tâche à refaire.")
        return redirect('detail_or_rec', or_id=or_id)

    # ── Durée générale (heures + minutes) ──
    try:
        heures = int(request.POST.get('duree_heures') or 0)
        minutes = int(request.POST.get('duree_minutes') or 0)
    except ValueError:
        heures, minutes = -1, -1
    if heures < 0 or not (0 <= minutes < 60):
        messages.error(request, "Durée invalide.")
        return redirect('detail_or_rec', or_id=or_id)
    duree_totale = heures * 60 + minutes
    if duree_totale <= 0:
        messages.error(request, "La durée de la réouverture doit être supérieure à 0.")
        return redirect('detail_or_rec', or_id=or_id)

    reception = _reception_actuelle(or_obj)
    now = timezone.now()

    with transaction.atomic():
        or_obj.statut = StatutOR.REOUVERT
        or_obj.date_cloture = None  # l'OR n'est plus clôturé
        or_obj.save(update_fields=['statut', 'date_cloture'])

        for tache in taches:
            tache.statut = StatutTache.A_FAIRE
            tache.date_debut = None
            tache.date_fin = None
            tache.date_validation = None
            tache.valide_par = None
            tache.commentaire_validation = ''
            tache.cloturee_manuellement = False
            tache.date_assignation = now
            # Visible côté technicien : « À refaire » + raison
            tache.type_retour = TypeRetour.REOUVERTURE
            tache.motif_retour = raison
            tache.date_retour = now
            tache.nb_reouvertures += 1
            tache.save()

        reouverture = ReouvertureOR.objects.create(
            ordre_reparation=or_obj,
            reception=reception,
            raison=raison,
            duree_prevue_minutes=duree_totale,
            reouvert_par=request.user,
        )
        reouverture.taches.set(taches)

        # Durée prévue de l'OR = Σ tâches + Σ réouvertures (celle-ci comprise)
        or_obj.recalculer_duree_prevue(save=True)

    log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {
        'statut': 'REOUVERT',
        'raison': raison,
        'numero': or_obj.numero,
        'reception': getattr(reception, 'numero', None),
        'taches': [t.libelle for t in taches],
        'duree_prevue_minutes': duree_totale,
    })
    messages.success(
        request,
        f"🔓 OR {or_obj.numero} réouvert sur la réception {getattr(reception, 'numero', '')} : "
        f"{len(taches)} tâche(s) à refaire, durée prévue {reouverture.duree_prevue_label}."
    )
    return redirect('detail_or_rec', or_id=or_id)