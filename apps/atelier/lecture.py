"""
apps/atelier/lecture.py — mise en forme LECTURE SEULE des deux fiches.

Fiche de contrôle : une section par catégorie (dont « Habitacle »), libellés et couleurs de controle.py.
Fiche technique   : une section par page de saisie (forms.TECHNIQUE_ETAPES).
"""
import datetime
from decimal import Decimal

from django.db import models

from . import controle
from .forms import pretty_label, CONTROLE_ENTETE

CLASSES = {'BON': 'good', 'INTACT': 'good', 'DEFAUT': 'bad', 'CASSE': 'bad', 'FISSURE': 'warn'}
MAUVAIS = ('DEFAUT', 'CASSE', 'FISSURE')

# Sections de lecture de la fiche de contrôle
CONTROLE_SECTIONS = (
    [("En-tête", CONTROLE_ENTETE + ['travail_a_effectuer'])]
    + [(titre, champs + ['commentaires']) if titre == "Synthèse" else (titre, champs)
       for titre, champs in controle.CATEGORIES]
)


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
    est_controle = 'points_degats_carrosserie' in {f.name for f in modele._meta.fields}
    sections, defauts = [], []
    for titre, champs in etapes:
        items = []
        for nom in champs:
            if nom.startswith('signature_'):
                continue                                   # rendues à part (bloc Signatures)
            f = modele._meta.get_field(nom)
            if nom == 'points_degats_carrosserie':
                nb = len(getattr(obj, nom) or [])
                items.append({'label': "Schéma carrosserie",
                              'value': f"{nb} point(s) marqué(s)" if nb else "Aucun dégât marqué",
                              'css': 'bad' if nb else '', 'kind': 'damage'})
                continue
            if est_controle and nom in controle.CHAMPS_COMPARES:
                brut = getattr(obj, nom)
                item = {'label': controle.libelle(nom), 'value': controle.afficher(nom, brut),
                        'css': controle.qualite(nom, brut), 'kind': 'text'}
                mauvais = item['css'] == 'bad'
            else:
                valeur, css = _valeur(obj, f)
                item = {'label': controle.LIBELLES.get(nom) or _label(f), 'value': valeur, 'css': css, 'kind': 'text'}
                mauvais = getattr(obj, nom) in MAUVAIS
            items.append(item)
            if mauvais:
                defauts.append({'section': titre, 'label': item['label'], 'value': item['value'], 'css': item['css']})
        sections.append({'title': titre, 'items': items})
    return sections, defauts
