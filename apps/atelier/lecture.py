"""
apps/atelier/lecture.py — mise en forme LECTURE SEULE des deux fiches.

Les sections sont exactement les 3 pages de la saisie (forms.CONTROLE_ETAPES / TECHNIQUE_ETAPES) ;
les libellés et valeurs sont lus depuis les modèles (aucun champ retapé à la main).
"""
import datetime
from decimal import Decimal
from django.db import models
from .forms import pretty_label

CLASSES = {'BON': 'good', 'INTACT': 'good', 'DEFAUT': 'bad', 'CASSE': 'bad', 'FISSURE': 'warn'}
MAUVAIS = ('DEFAUT', 'CASSE', 'FISSURE')


def _label(field):
    v = str(field.verbose_name)
    return pretty_label(field.name) if v == field.name.replace('_', ' ') else v[:1].upper() + v[1:]


def _valeur(obj, field):
    brut = getattr(obj, field.name)
    if field.name.startswith('ok_'):
        return ('✓ OK' if brut else 'Non fait'), ''
    if isinstance(field, models.BooleanField):
        return ('—' if brut is None else ('Oui' if brut else 'Non')), ''
    if field.choices:
        if brut in (None, ''):
            return '—', ''
        return getattr(obj, f'get_{field.name}_display')(), CLASSES.get(brut, '')
    if brut in (None, '', []):
        return '—', ''
    if isinstance(brut, datetime.datetime):
        return brut.strftime('%d/%m/%Y %H:%M'), ''
    if isinstance(brut, datetime.date):
        return brut.strftime('%d/%m/%Y'), ''
    if isinstance(brut, Decimal):
        txt = f"{brut:f}".rstrip('0').rstrip('.') if '.' in f"{brut:f}" else f"{brut:f}"
        unite = {'mm': ' mm', '°C': ' °C'}.get(field.help_text, '')
        return txt + unite, ''
    return str(brut), ''


def construire(obj, etapes):
    """→ (sections, defauts) ; section = {'title', 'items'} ; item = {'label','value','css','kind'}."""
    modele = obj._meta.model
    sections, defauts = [], []
    for titre, champs in etapes:
        items = []
        for nom in champs:
            f = modele._meta.get_field(nom)
            if nom.startswith('signature_'):
                continue                                   # rendues à part (bloc Signatures)
            if nom == 'points_degats_carrosserie':
                nb = len(getattr(obj, nom) or [])
                items.append({'label': "Schéma carrosserie", 'value': f"{nb} point(s) marqué(s)" if nb else "Aucun dégât marqué",
                              'css': 'bad' if nb else '', 'kind': 'damage'})
                continue
            valeur, css = _valeur(obj, f)
            item = {'label': _label(f), 'value': valeur, 'css': css, 'kind': 'text'}
            items.append(item)
            if getattr(obj, nom) in MAUVAIS:
                defauts.append({'section': titre, 'label': item['label'], 'value': valeur, 'css': css})
        sections.append({'title': titre, 'items': items})
    return sections, defauts
