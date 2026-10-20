"""
Dashboard réception + notifications.
"""
from django.db.models import Case, Count, F, FloatField, Q, Value, When
from django.db.models.functions import Cast, Coalesce
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts.choices import MotifEntree
from apps.accounts.decorators import receptionniste_required
from apps.atelier.models import OrdreReparation, StatutTache
from apps.guerite.models import EnregistrementEntree
from apps.reception.models import Notification, Reception, StatutVehicule

from ._utils import STATUTS_OR_ACTIFS, get_entrees_presentes_filtrees


@receptionniste_required
def dashboard(request):
    today = timezone.localdate()

    receptions_actives = Reception.objects.exclude(statut=StatutVehicule.SORTI)
    receptions = (
        receptions_actives
        .select_related('vehicule', 'vehicule__client')
        .prefetch_related('transferts__atelier')
        .order_by('-created_at')
    )

    # ── Notifications non lues ──
    notifs_qs = Notification.objects.filter(destinataire=request.user, lue=False)
    notifs = list(notifs_qs.select_related('reception')[:9])

    # ── OR actifs, triés par avancement ──
    or_actifs = (
        OrdreReparation.objects
        .filter(statut__in=STATUTS_OR_ACTIFS, reception__in=receptions_actives)
        .select_related('vehicule', 'reception')
        .prefetch_related('ateliers', 'taches')
        .annotate(
            nb_taches=Count('taches', distinct=True),
            nb_validees=Count('taches', filter=Q(taches__statut=StatutTache.VALIDEE), distinct=True),
        )
        .annotate(
            progression=Case(
                When(nb_taches=0, then=Value(0.0)),
                default=Cast(F('nb_validees'), FloatField()) / Cast(F('nb_taches'), FloatField()),
                output_field=FloatField(),
            ),
            est_complet=Case(
                When(nb_taches__gt=0, nb_validees=F('nb_taches'), then=Value(1)),
                default=Value(0),
            ),
        )
        .order_by('-est_complet', '-progression', '-nb_validees', '-date_creation')[:6]
    )

    # ── Compteurs entrées : 1 requête au lieu de 3 ──
    compteurs_entrees = EnregistrementEntree.objects.aggregate(
        nb_entrees_today=Count('id', filter=Q(date_entree__date=today)),
        nb_sorties_today=Count('id', filter=Q(date_sortie__date=today)),
        nb_a_traiter=Count('id', filter=Q(
            motif=MotifEntree.REPARATION,
            statut=StatutVehicule.EN_COURS,
            reception__isnull=True,
        )),
    )

    # ── KPI réceptions : 1 requête au lieu de 3 ──
    kpi = receptions_actives.aggregate(
        nb_en_atelier=Count('id', filter=Q(statut=StatutVehicule.RAPPORT_FAIT)),
        nb_presents=Count('id', filter=Q(statut=StatutVehicule.FICHE_CONTROLE)),
        nb_termines=Count('id', filter=Q(statut=StatutVehicule.TRAVAUX_TERMINES)),
    )

    # ── Réceptions sans OR, fiche de contrôle signée par le client ──
    base_attente_or = (
        receptions_actives
        .filter(ordre_reparation__isnull=True, entree__fiche_controle__isnull=False)
        .filter(entree__fiche_controle__signature_client_avant__isnull=False)
        .exclude(entree__fiche_controle__signature_client_avant='')
    )

    return render(request, 'reception/dashboard.html', {
        **compteurs_entrees,
        **kpi,
        'nb_attente_or': base_attente_or.count(),

        'receptions': receptions,
        'notifs': notifs,
        'nb_notifs': notifs_qs.count(),  # vrai total (avant : plafonné à 9)
        'or_actifs': or_actifs,
        'fiches_attente_or': (
            base_attente_or
            .select_related('vehicule', 'vehicule__client', 'entree', 'entree__fiche_controle')
            .order_by('-created_at')[:7]
        ),
        'entrees_recentes': (
            EnregistrementEntree.objects
            .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
            .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
            .order_by(F('date_tri').desc())[:7]
        ),
        'vehicules_presents': (
            EnregistrementEntree.objects
            .filter(date_sortie__isnull=True, bon_sortie__isnull=True, reception__isnull=True)
            .select_related('vehicule', 'vehicule__client', 'conducteur')
            .order_by('-date_entree')[:7]
        ),

        'today': today,
        # ⚠️ Dans le template, utilise {{ entreesNbr.count }} (1 requête COUNT)
        #    et pas {{ entreesNbr|length }} (charge toutes les lignes).
        'entreesNbr': get_entrees_presentes_filtrees(request),
    })


@receptionniste_required
def notifs_json(request):
    notifs = list(
        Notification.objects.filter(destinataire=request.user, lue=False)
        .values('id', 'type_notif', 'titre', 'message', 'created_at', 'reception_id')
    )
    return JsonResponse({'notifs': notifs, 'count': len(notifs)})


@receptionniste_required
def marquer_lues(request):
    Notification.objects.filter(destinataire=request.user, lue=False).update(lue=True)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('dashboard_reception')
