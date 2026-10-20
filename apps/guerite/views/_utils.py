"""
Helpers partagés par les vues Guérite.

Les helpers génériques (photos, dates, POST…) sont réutilisés depuis
apps.reception.views._utils pour éviter une 3e copie du même code.
"""
import json

from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.choices import StatutVehicule
from apps.guerite.models import EnregistrementEntree
from apps.reception.views._utils import paginate_queryset, parse_date

# Conservé pour compatibilité (était importé par apps.accounts)
PHOTO_FIELDS = ['photo1', 'photo2', 'photo3']

STATUTS_HISTORIQUE = [('PRESENT', 'Présent'), ('SORTI', 'Sorti')]
TYPES_CLIENT = ('PARTICULIER', 'ENTREPRISE')


# ─── Requête / JSON ──────────────────────────────────────────────────────
def safe_next(request, fallback):
    """?next=… seulement s'il pointe vers notre site (anti open-redirect)."""
    url = request.GET.get('next', '')
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return fallback


def json_body(request):
    """Corps JSON en dict, ou None s'il est invalide."""
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def jstr(data, key, default=''):
    """Valeur texte d'un dict JSON, nettoyée (gère None et les non-str)."""
    val = data.get(key)
    return default if val is None else str(val).strip()


def get_or_create_nom(model, nom, **extra):
    """get_or_create insensible à la casse : « toyota » ne recrée pas « Toyota »."""
    return model.objects.filter(nom__iexact=nom, **extra).first() or model.objects.create(nom=nom, **extra)


# ─── Entrées ─────────────────────────────────────────────────────────────
def get_entree_non_sortie(entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related('vehicule', 'bon_sortie'), id=entree_id)
    if entree.statut == StatutVehicule.SORTI:
        raise Http404("Entrée déjà sortie")
    return entree


def entree_active(vehicule):
    """Entrée en cours (non sortie) du véhicule, ou None."""
    return (EnregistrementEntree.objects.filter(vehicule=vehicule)
            .exclude(statut=StatutVehicule.SORTI).order_by('-date_entree').first())


def get_filtered_entrees(request):
    """Historique filtré (statut, motif, dates, recherche)."""
    qs = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
        .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
        .order_by(F('date_tri').desc())
    )
    g = request.GET
    statut = g.get('statut', '').strip()
    if statut == 'SORTI':
        qs = qs.filter(statut='SORTI')
    elif statut == 'PRESENT':
        qs = qs.exclude(statut='SORTI')
    if g.get('motif', '').strip():
        qs = qs.filter(motif=g['motif'].strip())
    if (d := parse_date(g.get('date_debut'))):
        qs = qs.filter(date_entree__date__gte=d)
    if (d := parse_date(g.get('date_fin'))):
        qs = qs.filter(date_entree__date__lte=d)

    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(numero__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )
    return qs


def entrees_presentes_qs(request):
    """Véhicules encore sur site, filtrés — même filtre pour l'écran ET les exports."""
    qs = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'conducteur__client')
        .filter(date_sortie__isnull=True)
        .order_by('-date_entree')
    )
    g = request.GET
    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
            | Q(vehicule__client__telephone__icontains=q)
            | Q(conducteur__nom__icontains=q)
        )
    if g.get('motif', '').strip():
        qs = qs.filter(motif=g['motif'].strip())
    # CORRIGÉ : une date mal formée dans l'URL provoquait une erreur 500 (strptime)
    if (d := parse_date(g.get('date_debut'))):
        qs = qs.filter(date_entree__date__gte=d)
    if (d := parse_date(g.get('date_fin'))):
        qs = qs.filter(date_entree__date__lte=d)
    return qs


def get_entrees_presentes_filtrees(request, per_page=30):
    """Signature conservée : retourne une Page (itérable + infos pagination)."""
    return paginate_queryset(request, entrees_presentes_qs(request), per_page=per_page)
