"""
Helpers partagés par les vues Réception / Guérite.
Certains sont importés par d'autres apps (accounts) : ne pas les renommer.
"""
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from io import BytesIO

import qrcode
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Q
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.atelier.models import StatutOR
from apps.guerite.models import EnregistrementEntree
from apps.reception.models import Notification, StatutVehicule

logger = logging.getLogger(__name__)

# ─── Constantes ──────────────────────────────────────────────────────────
STATUTS_OR_ACTIFS = [StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT]
MOTIFS_VALIDES = {'REPARATION', 'VISITE', 'STATIONNEMENT', 'INTERNE'}
NB_PHOTOS = 3
DUREE_UNITES = {'h': timedelta(hours=1), 'j': timedelta(days=1), 'm': timedelta(days=30)}

CARBURANTS = [
    ('NON_DEFINI', 'Non défini'), ('ESSENCE', 'Essence'), ('DIESEL', 'Diesel'),
    ('ELECTRIQUE', 'Électrique'), ('HYBRIDE', 'Hybride'), ('GPL', 'GPL'),
]
TRANSMISSIONS = [
    ('NON_DEFINI', 'Non défini'), ('MANUELLE', 'Manuelle'), ('AUTOMATIQUE', 'Automatique'),
]


# ─── Petits helpers ──────────────────────────────────────────────────────
def post_str(request, key, default=''):
    """Valeur POST nettoyée (jamais None)."""
    return (request.POST.get(key) or default).strip()


def post_int(request, key):
    """Entier POST, ou None si vide / invalide (évite les erreurs 500)."""
    try:
        return int(request.POST.get(key, '').strip())
    except (ValueError, AttributeError):
        return None


def parse_date(valeur):
    """'YYYY-MM-DD' → date, ou None si vide / invalide (évite les erreurs 500)."""
    try:
        return datetime.strptime((valeur or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def get_or_none(qs, **kwargs):
    """Comme .filter().first(), mais renvoie None sur un id mal formé au lieu de planter."""
    try:
        return qs.filter(**kwargs).first()
    except (ValueError, ValidationError):
        return None


def fmt_dt(dt, fmt='%d/%m/%Y %H:%M'):
    """Datetime formatée à l'heure locale (Douala), pas en UTC."""
    return timezone.localtime(dt).strftime(fmt) if dt else ''


def a_champ(obj, nom):
    try:
        obj._meta.get_field(nom)
        return True
    except FieldDoesNotExist:
        return False


def pdf_response(contenu, nom_fichier):
    r = HttpResponse(contenu, content_type='application/pdf')
    r['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
    return r


def url_liste_bons(user):
    return 'liste_bons_admin' if user.role == Role.ADMIN else 'liste_bons_sortie'


# ─── Pagination ──────────────────────────────────────────────────────────
def paginate_queryset(request, qs, per_page=25):
    """get_page gère déjà les numéros invalides / hors limites."""
    return Paginator(qs, per_page).get_page(request.GET.get('page'))


# ─── Notifications ───────────────────────────────────────────────────────
def _notifier(type_notif, titre, message, reception=None):
    """Notifie tous les réceptionnistes actifs.
    create() en boucle (pas bulk_create) pour garder les signaux post_save éventuels."""
    for user in User.objects.filter(role=Role.RECEPTIONNISTE, is_active=True).only('id'):
        Notification.objects.create(
            type_notif=type_notif, titre=titre, message=message,
            reception=reception, destinataire=user,
        )


# ─── Filtres des entrées ─────────────────────────────────────────────────
def get_entrees_presentes_filtrees(request):
    """Entrées encore sur site, filtrées (sans pagination) — utile pour exports."""
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
    if g.get('motif'):
        qs = qs.filter(motif=g['motif'])

    if (d := parse_date(g.get('date_debut'))):
        qs = qs.filter(date_entree__date__gte=d)
    if (d := parse_date(g.get('date_fin'))):
        qs = qs.filter(date_entree__date__lte=d)

    # Présents depuis plus de N heures / jours / mois
    try:
        n = int(g.get('duree_valeur', '').strip())
    except ValueError:
        n = None
    if n is not None and n >= 0:
        unite = DUREE_UNITES.get(g.get('duree_unite', 'h').strip() or 'h', DUREE_UNITES['j'])
        qs = qs.filter(date_entree__lt=timezone.now() - unite * max(n, 1))

    return qs


def get_filtered_entrees(request):
    """Historique complet des entrées, filtré."""
    qs = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
        .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
        .order_by(F('date_tri').desc())
    )
    g = request.GET
    statut = g.get('statut')

    if statut == 'SORTI':
        qs = qs.filter(statut='SORTI')
    elif statut == 'PRESENT':
        qs = qs.exclude(statut='SORTI')
    if g.get('motif'):
        qs = qs.filter(motif=g['motif'])
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


# ─── Filtres réutilisés par listes ET exports PDF ───────────────────────
def filtrer_bons(request, qs):
    g = request.GET
    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(numero__icontains=q) | Q(nom_demandeur__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(Origine_demande__icontains=q) | Q(observations__icontains=q)
        )
    if g.get('type', '').strip():
        qs = qs.filter(types=g['type'].strip())
    if g.get('etat', '').strip():
        qs = qs.filter(etats=g['etat'].strip())

    now = timezone.localtime()
    periode = g.get('periode', '')
    if periode == 'today':
        qs = qs.filter(created_at__date=now.date())
    elif periode == 'week':
        qs = qs.filter(created_at__gte=now - timedelta(days=7))
    elif periode == 'month':
        qs = qs.filter(created_at__year=now.year, created_at__month=now.month)
    elif periode == 'custom':
        if (d := parse_date(g.get('date_debut'))):
            qs = qs.filter(created_at__date__gte=d)
        if (d := parse_date(g.get('date_fin'))):
            qs = qs.filter(created_at__date__lte=d)

    if g.get('sort') == 'numero':
        qs = qs.order_by('numero')
    return qs


def filtrer_clients(request, qs):
    g = request.GET
    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q)
            | Q(email__icontains=q) | Q(ninea__icontains=q) | Q(ville__icontains=q)
            | Q(numero_client__icontains=q)
        )
    type_client = g.get('type', '').strip()
    if type_client and type_client != 'tous':
        qs = qs.filter(type_client=type_client)
    if g.get('ville', '').strip():
        qs = qs.filter(ville=g['ville'].strip())
    return qs


def filtrer_vehicules(request, qs, today):
    g = request.GET
    q = g.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(immatriculation__icontains=q) | Q(marque__icontains=q) | Q(modele__icontains=q)
            | Q(numero_chassis__icontains=q) | Q(client__nom__icontains=q)
            | Q(client__prenom__icontains=q) | Q(client__telephone__icontains=q)
        )
    if g.get('carburant', '').strip():
        qs = qs.filter(type_carburant=g['carburant'].strip())
    if g.get('type_client', '').strip():
        qs = qs.filter(client__type_client=g['type_client'].strip())

    assurance = g.get('assurance', '').strip()
    if assurance == 'expiree':
        qs = qs.filter(expiry_assurance__lt=today)
    elif assurance == 'valide':
        qs = qs.filter(expiry_assurance__gte=today)

    presence = g.get('presence', '').strip()
    if presence == 'presents':
        qs = qs.filter(Q_PRESENT).distinct()
    elif presence == 'atelier':
        qs = qs.filter(Q_ATELIER).distinct()
    elif presence == 'libres':
        qs = qs.exclude(Q_PRESENT).distinct()
    return qs


Q_PRESENT = Q(entrees__statut='EN_COURS')
Q_ATELIER = Q(ordres_reparation__statut__in=STATUTS_OR_ACTIFS)


# ─── Véhicules présents (autocomplétion bons de sortie) ──────────────────
def vehicules_presents_json():
    """Retourne (liste, json) des véhicules actuellement sur site."""
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


# ─── QR code & signatures ────────────────────────────────────────────────
def _gen_qr(bon):
    """Génère le QR du bon. N'interrompt jamais le flux, mais trace l'erreur."""
    try:
        immat = bon.vehicule.immatriculation if bon.vehicule_id else ''
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(f"GARAGE|{bon.numero}|{immat}")
        qr.make(fit=True)
        buf = BytesIO()
        qr.make_image().save(buf, 'PNG')
    except Exception:
        logger.exception("Échec génération QR pour le bon %s", getattr(bon, 'numero', '?'))


def save_signature_from_dataurl(instance, data_url, field_name='signature'):
    """Convertit un dataURL canvas en image et l'attache au champ (sans save)."""
    if not data_url or not data_url.startswith('data:image'):
        return False
    try:
        entete, imgstr = data_url.split(';base64,')
        ext = entete.split('/')[-1]
        filename = f"sig_{uuid.uuid4().hex[:10]}.{ext}"
        getattr(instance, field_name).save(
            filename, ContentFile(base64.b64decode(imgstr), name=filename), save=False)
        return True
    except Exception:
        logger.exception("Erreur enregistrement signature")
        return False


# ─── Photos véhicules ────────────────────────────────────────────────────
def enregistrer_photo(immatriculation, fichier, index):
    ext = os.path.splitext(fichier.name)[1].lower()
    immat = immatriculation.replace(' ', '').replace('-', '').upper()
    return default_storage.save(f"vehicules/photos/{immat}_{index}{ext}", fichier)


def supprimer_fichier(path):
    if path and default_storage.exists(path):
        default_storage.delete(path)


def photos_list(vehicule):
    chemins = [p.strip() for p in (vehicule.photos or '').split(';') if p.strip()][:NB_PHOTOS]
    return chemins + [''] * (NB_PHOTOS - len(chemins))


def appliquer_photos(vehicule, chemins):
    chemins = [p for p in chemins if p]
    vehicule.photos = ';'.join(chemins)
    vehicule.photo = chemins[0] if chemins else None
