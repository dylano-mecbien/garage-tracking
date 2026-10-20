"""
Dashboard guérite, historique, véhicules présents, consultation.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.accounts.choices import MotifEntree, StatutVehicule
from apps.accounts.decorators import guerite_required
from apps.accounts.models import Role 
from apps.guerite.models import BonSortie, EnregistrementEntree
from apps.reception.views import dashboard as reception_dashboard
from apps.reception.views._utils import paginate_queryset

from ._utils import STATUTS_HISTORIQUE, entrees_presentes_qs, get_entrees_presentes_filtrees, get_filtered_entrees

LIMITE_PRESENTS = 7
LIMITE_RECENTES = 9


@guerite_required
def dashboard(request):
    if request.user.role == Role.RECEPTIONNISTE:
        return reception_dashboard(request)

    # CORRIGÉ : date locale (Douala). Avant : date UTC → stats « du jour »
    # fausses entre minuit et 1h.
    today = timezone.localdate()
    compteurs = EnregistrementEntree.objects.aggregate(  # 1 requête au lieu de 2
        nb_entrees_today=Count('id', filter=Q(date_entree__date=today)),
        nb_sorties_today=Count('id', filter=Q(date_sortie__date=today)),
    )

    vehicules_presents = (
        EnregistrementEntree.objects
        .exclude(statut=StatutVehicule.SORTI)
        # Priorité : bon de sortie approuvé OU visite (prêts à sortir) en premier
        .annotate(priorite=Case(
            When(Q(bon_sortie__etats='APPROBATION') | Q(motif=MotifEntree.VISITE), then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        ))
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'conducteur__client')
        .order_by('priorite', '-date_entree')[:LIMITE_PRESENTS]
    )

    return render(request, 'guerite/dashboard.html', {
        **compteurs,
        'entrees': entrees_presentes_qs(request),
        'vehicules_presents': vehicules_presents,
        'entrees_recentes': (
            EnregistrementEntree.objects
            .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
            .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
            .order_by(F('date_tri').desc())[:LIMITE_RECENTES]
        ),
    })


@login_required  # AJOUTÉ : la vue était accessible sans connexion
def historique_entrees(request):
    page_obj = paginate_queryset(request, get_filtered_entrees(request), per_page=25)
    return render(request, 'guerite/historique.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'motifs': MotifEntree.choices,
        'statuts': STATUTS_HISTORIQUE,
    })


@login_required  # AJOUTÉ
def liste_vehicules_presents(request):
    page = get_entrees_presentes_filtrees(request, per_page=30)
    
    return render(request, 'guerite/vehicules_presents.html', {
        'entrees': page,
        'page_obj': page,
        'paginator': page.paginator,
        'motifs': MotifEntree.choices,
        'filters': {k: request.GET.get(k, '') for k in ('q', 'motif', 'date_debut', 'date_fin')},
    })


@guerite_required
def detail_entree(request, entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related(
            'vehicule', 'vehicule__client', 'conducteur', 'agent_entree'),
        id=entree_id,
    )
    return render(request, 'guerite/entree/detail.html', {'entree': entree})


@guerite_required
def consulter_bon_sortie(request):
    numero = request.GET.get('numero', '').strip()
    bon = None
    if numero:
        # Insensible à la casse : « bs-0012 » trouve « BS-0012 »
        bon = (BonSortie.objects.select_related('vehicule', 'vehicule__client')
               .filter(numero__iexact=numero).first())
        if bon is None:
            messages.warning(request, f"Aucun bon de sortie trouvé avec le numéro {numero}")
    return render(request, 'guerite/bon_sortie/consulter.html', {'bon': bon, 'numero': numero})
