"""
Helpers partagés par les vues Atelier.
Certains sont importés par d'autres apps (reception, accounts) : ne pas les renommer.
"""
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect

from apps.accounts.models import User
from apps.atelier.models import Atelier, StatutOR, Tache, _format_minutes
from apps.atelier.roles import ROLE_TECH
from apps.audit.models import ActionType
from apps.audit.service import log_action

STATUTS_OR_ACTIFS = [StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT]


# ─── Atelier du responsable ──────────────────────────────────────────────
def get_atelier_du_resp(user):
    return Atelier.objects.filter(responsable=user, is_active=True).first()


def atelier_requis(view):
    """Injecte request.atelier, ou redirige si le responsable n'a pas d'atelier.

    CORRIGÉ : avant, avec atelier = None, `filter(ateliers=None)` renvoyait
    les OR SANS atelier, et les tâches étaient créées avec atelier = None.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        atelier = get_atelier_du_resp(request.user)
        if atelier is None:
            messages.error(request, "Aucun atelier ne vous est assigné comme responsable.")
            return redirect('dashboard_technicien')
        request.atelier = atelier
        return view(request, *args, **kwargs)
    return wrapper


# ─── Lecture sécurisée du POST ───────────────────────────────────────────
def post_str(request, key, default=''):
    return (request.POST.get(key) or default).strip()


def post_int(request, key, default=0):
    try:
        return max(int(request.POST.get(key, '').strip()), 0)
    except (ValueError, AttributeError):
        return default


def post_decimal(request, key):
    """Accepte « 1,5 » comme « 1.5 » (saisie FR). Négatif / invalide → 0."""
    brut = (request.POST.get(key) or '0').strip().replace(' ', '').replace(',', '.')
    try:
        val = Decimal(brut)
    except InvalidOperation:
        return Decimal('0')
    return val if val.is_finite() and val >= 0 else Decimal('0')


def get_or_none(qs, **kwargs):
    """Comme .filter().first(), mais None sur un id mal formé (au lieu d'une erreur 500)."""
    try:
        return qs.filter(**kwargs).first()
    except (ValueError, ValidationError):
        return None


def parse_duree_hm(request, h_name='duree_heures', m_name='duree_minutes', default=60):
    """Heures + minutes du POST → total en minutes (default si 0)."""
    total = post_int(request, h_name) * 60 + min(post_int(request, m_name), 59)
    return total if total > 0 else default


def lire_priorite(request, defaut='NORMALE'):
    """Priorité validée contre les choix du modèle (avant : n'importe quelle valeur)."""
    valeur = request.POST.get('priorite', defaut)
    choix = {c for c, _ in (Tache._meta.get_field('priorite').choices or [])}
    return valeur if not choix or valeur in choix else defaut


# ─── Techniciens ─────────────────────────────────────────────────────────
def techniciens_assignables(atelier, user):
    """Techniciens actifs + le responsable lui-même en tête."""
    techs = list(User.objects.filter(role=ROLE_TECH, is_active=True).order_by('nom', 'prenom'))
    if user not in techs:
        techs.insert(0, user)
    return techs


def get_technicien(request, tech_id):
    """Technicien assignable uniquement (avant : n'importe quel utilisateur, même un admin)."""
    if not tech_id:
        return None
    return get_or_none(
        User.objects.filter(Q(role=ROLE_TECH, is_active=True) | Q(id=request.user.id)),
        id=tech_id,
    )


# ─── OR ──────────────────────────────────────────────────────────────────
def _entree_from_or(or_obj):
    reception = getattr(or_obj, 'reception', None)
    return getattr(reception, 'entree', None) if reception else None


def passer_or_en_cours(request, or_obj):
    """OUVERT → EN_COURS (+ audit). Logique avant copiée à 3 endroits."""
    if or_obj.statut == StatutOR.OUVERT:
        or_obj.statut = StatutOR.EN_COURS
        or_obj.save(update_fields=['statut'])
        log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {'statut': 'EN_COURS'})


def a_signe(obj, champ):
    """True si le champ signature est rempli (fichier ou texte non vide)."""
    return bool(obj and str(getattr(obj, champ, '') or '').strip())


# ─── Durées ──────────────────────────────────────────────────────────────
def format_duree(minutes):
    if minutes is None:
        return "—"
    try:
        m = max(int(round(float(minutes))), 0)
    except (TypeError, ValueError):
        return "—"
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} h" if r == 0 else f"{h} h {r} min"


def enrich_taches_duree(taches):
    """Attache les labels de durée aux tâches (utilise les comptes rendus prefetchés)."""
    for t in taches:
        est = t.duree_estimee_minutes or 0
        t.est_h, t.est_m = divmod(est, 60)

        crs = list(t.comptes_rendus.all())
        total_cr = sum(cr.duree_minutes or 0 for cr in crs)

        t.calc_duree_technicien = total_cr
        t.calc_duree_reelle = t.duree_reelle_minutes or total_cr
        t.calc_duree_estimee_lbl = _format_minutes(est)
        t.calc_duree_technicien_lbl = _format_minutes(total_cr)
        t.calc_duree_reelle_lbl = _format_minutes(t.calc_duree_reelle)

        if t.duree_estimee_minutes is None:
            t.calc_ecart_lbl = '—'
        else:
            ecart = total_cr - est
            t.calc_ecart_lbl = f"{'+' if ecart > 0 else ''}{_format_minutes(abs(ecart))}" if ecart else '0 min'

        for cr in crs:
            cr.calc_duree_lbl = _format_minutes(cr.duree_minutes or 0)
    return taches
