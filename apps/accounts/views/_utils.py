"""
Constantes et helpers partagés par les vues admin.
"""
import json
import os
from urllib.parse import urlencode

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.http import url_has_allowed_host_and_scheme

from apps.guerite.models import EnregistrementEntree, StatutVehicule

# ─── Constantes ──────────────────────────────────────────────────────────
STATUTS_OR_ACTIFS = ['OUVERT', 'EN_COURS', 'REOUVERT']
DEFAULT_PASSWORD = getattr(settings, 'DEFAULT_USER_PASSWORD', 'garage2026')
NB_PHOTOS = 3
MOTIFS_VALIDES = {'REPARATION', 'VISITE', 'STATIONNEMENT', 'INTERNE'}

# TODO : remplacer par Vehicule.TypeCarburant.choices si tu as des TextChoices
CARBURANTS = [
    ('NON_DEFINI', 'Non défini'), ('ESSENCE', 'Essence'), ('DIESEL', 'Diesel'),
    ('ELECTRIQUE', 'Électrique'), ('HYBRIDE', 'Hybride'), ('GPL', 'GPL'),
]
TRANSMISSIONS = [
    ('NON_DEFINI', 'Non défini'), ('MANUELLE', 'Manuelle'), ('AUTOMATIQUE', 'Automatique'),
]


# ─── Requête ─────────────────────────────────────────────────────────────
def post_str(request, key, default=''):
    """Valeur POST nettoyée (jamais None)."""
    return (request.POST.get(key) or default).strip()


def post_int(request, key):
    """Entier POST ou None si vide / invalide (évite les erreurs 500)."""
    try:
        return int(request.POST.get(key, '').strip())
    except (ValueError, AttributeError):
        return None


def safe_referer(request, fallback='/'):
    """HTTP_REFERER uniquement s'il pointe vers notre site (anti open-redirect)."""
    url = request.META.get('HTTP_REFERER', '')
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return fallback


def qs_sans(request, *cles):
    """Querystring actuelle sans certaines clés (liens de pagination)."""
    params = {k: v for k, v in request.GET.items() if k not in cles and v != ''}
    return urlencode(params) + '&' if params else ''


# ─── Véhicules présents (autocomplétion bons de sortie) ──────────────────
def vehicules_presents_json():
    """Retourne (liste, json) des véhicules actuellement sur le site."""
    entrees = (
        EnregistrementEntree.objects
        .exclude(statut=StatutVehicule.SORTI)
        .select_related('vehicule', 'vehicule__client', 'conducteur')
    )
    data = [{
        'id': e.vehicule.id,
        'immatriculation': e.vehicule.immatriculation,
        'conducteur_nom': f"{e.conducteur.nom} {e.conducteur.prenom}".strip() if e.conducteur else '',
        'client_nom': e.vehicule.client.nom if e.vehicule.client else '',
    } for e in entrees]
    return data, json.dumps(data, cls=DjangoJSONEncoder)


# ─── Photos véhicules ────────────────────────────────────────────────────
def enregistrer_photo(immatriculation, fichier, index):
    """Sauve une photo véhicule et retourne son chemin dans le storage."""
    ext = os.path.splitext(fichier.name)[1].lower()
    immat = immatriculation.replace(' ', '').replace('-', '').upper()
    # On passe le fichier directement : pas de .read() qui charge tout en RAM
    return default_storage.save(f"vehicules/photos/{immat}_{index}{ext}", fichier)


def supprimer_fichier(path):
    if path and default_storage.exists(path):
        default_storage.delete(path)


def photos_list(vehicule):
    """Chemins des photos (toujours NB_PHOTOS éléments, '' si vide)."""
    chemins = [p.strip() for p in (vehicule.photos or '').split(';') if p.strip()][:NB_PHOTOS]
    return chemins + [''] * (NB_PHOTOS - len(chemins))


def appliquer_photos(vehicule, chemins):
    """Écrit la liste de chemins dans les champs photos / photo."""
    chemins = [p for p in chemins if p]
    vehicule.photos = ';'.join(chemins)
    vehicule.photo = chemins[0] if chemins else None
