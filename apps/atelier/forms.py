"""
apps/atelier/forms.py

Fiche de contrôle (entrée) = 3 pages :
  1. En-tête, équipements et habitacle
  2. Extérieur, capot et carrosserie
  3. Synthèse et signature du technicien
Contrôle de sortie = 2 pages (mêmes éléments, sur la table temporaire), puis vérification.
Fiche technique = 3 pages.

Les formulaires de chaque page sont générés depuis le modèle (modelform_factory).
Les signatures sont converties en fichiers image et stockées en chemin dans le champ.
"""
import base64
import uuid
import logging

from django import forms
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import models as dj_models
from django.core.files.storage import default_storage
from django.forms import modelform_factory

from .controle import CATEGORIES, CATEGORIE_DE, LIBELLES
from .models import FicheControle, FicheControleTemporaire, FicheTechnique

logger = logging.getLogger(__name__)


TOKENS = {'av': 'AV', 'ar': 'AR', 'g': 'gauche', 'd': 'droit', 'mm': '(mm)', 'lamda': 'lambda'}


def pretty_label(name):
    s = ' '.join(TOKENS.get(p, p) for p in name.split('_'))
    return s[:1].upper() + s[1:]


# ══════════════════════════════════════════════════════════════════
#  SIGNATURES — Conversion dataURL → fichier image → chemin
# ══════════════════════════════════════════════════════════════════

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'webp'}
MAX_SIZE = 2 * 1024 * 1024  # 2 Mo


def save_signature_to_storage(data_url, folder='signatures', field_name='sig'):
    """
    Convertit un dataURL (base64) en fichier image, le sauvegarde sur le storage
    (local ) et retourne le chemin relatif, ou None si la conversion échoue.
    """
    if not data_url or not isinstance(data_url, str) or not data_url.startswith('data:image'):
        return None

    try:
        header, imgstr = data_url.split(';base64,')
        ext = header.split('/')[-1].lower()
        if ext == 'jpeg':
            ext = 'jpg'

        if ext not in ALLOWED_EXT:
            logger.warning("Signature : extension non autorisée %s", ext)
            return None

        data = base64.b64decode(imgstr)
        if len(data) > MAX_SIZE:
            logger.warning("Signature : image trop volumineuse (%d octets)", len(data))
            return None

        filename = f"{folder}/{field_name}_{uuid.uuid4().hex[:10]}.{ext}"
        saved_path = default_storage.save(filename, ContentFile(data))
        return saved_path

    except (ValueError, base64.binascii.Error) as e:
        logger.warning("Signature : décodage base64 échoué — %s", e)
        return None
    except Exception as e:
        logger.error("Signature : erreur inattendue — %s", e, exc_info=True)
        return None


def signature_preview_url(value):
    """Retourne l'URL affichable pour une valeur de signature (base64 ou chemin)."""
    if not value:
        return ''
    s = str(value)
    if s.startswith('data:'):
        return s                                    # base64 → utilisable tel quel
    try:
        return default_storage.url(s)               # chemin → URL storage
    except Exception:
        return ''


# ══════════════════════════════════════════════════════════════════
#  FORMULAIRE DE BASE (widgets auto)
# ══════════════════════════════════════════════════════════════════
class StepFormBase(forms.ModelForm):
    """Choisit automatiquement le bon widget selon le type réel de chaque champ."""

    READONLY_FIELDS = {
        'entree_le', 'sortie_le', 'immatriculation', 'telephone', 'nom_client', 'vehicule',
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, f in self.fields.items():
            if name in LIBELLES:
                f.label = LIBELLES[name]

            # Champ signature → HiddenInput
            if name.startswith('signature_'):
                f.widget = forms.HiddenInput()
                f.required = False

            # Oui / Non
            elif isinstance(f, forms.NullBooleanField):
                f.widget = forms.RadioSelect(choices=[('True', 'Oui'), ('False', 'Non')])

            # Schéma carrosserie (JSON)
            elif isinstance(f, forms.JSONField):
                f.widget = forms.HiddenInput()

            # Choix (Bon/Défaut, Intact/Fissuré…)
            elif isinstance(f, forms.ChoiceField):
                f.widget = forms.RadioSelect(choices=[c for c in f.choices if c[0] != ''])

            # Date
            elif isinstance(f, forms.DateField):
                f.widget = forms.DateInput(
                    attrs={'type': 'date', 'class': 'form-input'},
                    format='%Y-%m-%d',
                )

            # Textarea
            elif isinstance(f.widget, forms.Textarea):
                f.widget.attrs.update({'rows': 3, 'class': 'form-textarea'})

            # Inputs texte / nombre
            elif isinstance(f.widget, (forms.TextInput, forms.NumberInput)):
                f.widget.attrs.update({'class': 'form-input'})

            # Champs verrouillés : `readonly` et pas `disabled` (sinon Django
            # ignore la valeur envoyée et enregistre la valeur initiale, vide sur une fiche neuve).
            if name in self.READONLY_FIELDS:
                f.required = False
                f.widget.attrs['readonly'] = 'readonly'
                f.widget.attrs['tabindex'] = '-1'
                existing = f.widget.attrs.get('class', '')
                if 'fi-locked' not in existing:
                    f.widget.attrs['class'] = f"{existing} fi-locked".strip()

    @staticmethod
    def _vide(v):
        return v is None or v == ''

    def _valeur_verrouillee(self, name, envoyee):
        """
        Priorité : valeur déjà en base > valeur envoyée (readonly) > initial= de la vue.
        """
        try:
            en_base = getattr(self.instance, name, None)
        except ObjectDoesNotExist:
            en_base = None
        if not self._vide(en_base):
            return en_base
        if not self._vide(envoyee):
            return envoyee

        initiale = self.initial.get(name)
        if self._vide(initiale):
            return envoyee
        try:
            return self.fields[name].clean(initiale)
        except ValidationError:
            return initiale

    def clean(self):
        """
        - Réinjecte les valeurs des champs verrouillés.
        - Convertit les chaînes vides en None pour les champs nullables
          (sinon PostgreSQL rejette l'INSERT).
        """
        cleaned = super().clean()

        for name in self.READONLY_FIELDS.intersection(self.fields):
            cleaned[name] = self._valeur_verrouillee(name, cleaned.get(name))

        for field in self._meta.model._meta.fields:
            name = field.name
            if name not in cleaned:
                continue
            if isinstance(field, dj_models.BooleanField) and field.null:
                if cleaned[name] in ('', 'None'):
                    cleaned[name] = None
            elif isinstance(field, (dj_models.IntegerField, dj_models.DecimalField,
                                    dj_models.DateField, dj_models.DateTimeField)) and field.null:
                if cleaned[name] == '':
                    cleaned[name] = None
        return cleaned

    def clean_points_degats_carrosserie(self):
        v = self.cleaned_data.get('points_degats_carrosserie')
        return v if isinstance(v, list) else []

    # ── Signatures : dataURL → chemin de fichier ──
    def _clean_signature(self, name):
        value = self.cleaned_data.get(name)
        if not value:
            return value
        if isinstance(value, str) and not value.startswith('data:'):
            return value
        folder = 'signatures/technique' if self._meta.model is FicheTechnique else 'signatures/controle'
        chemin = save_signature_to_storage(value, folder=folder, field_name=name)
        return chemin or ''

    def clean_signature_technicien(self):
        return self._clean_signature('signature_technicien')

    def clean_signature_controleur(self):
        return self._clean_signature('signature_controleur')

    def clean_signature_receptionniste(self):
        return self._clean_signature('signature_receptionniste')

    def clean_signature_client_avant(self):
        return self._clean_signature('signature_client_avant')

    def clean_signature_client_apres(self):
        return self._clean_signature('signature_client_apres')


# ══════════════════════════════════════════════════════════════════
#  MÉTADONNÉES POUR LE TEMPLATE
# ══════════════════════════════════════════════════════════════════

def field_kind(field, name):
    """Retourne un type lisible pour le template."""
    if name.startswith('signature_'):
        return 'signature'
    if name == 'points_degats_carrosserie':
        return 'damage'

    w = field.widget
    if isinstance(w, forms.HiddenInput):
        return 'hidden'
    if isinstance(w, forms.RadioSelect):
        return 'radio'
    if isinstance(w, forms.CheckboxInput):
        return 'check'
    if isinstance(w, forms.Select):
        return 'select'
    if isinstance(w, forms.Textarea):
        return 'textarea'
    if isinstance(w, forms.DateInput):
        return 'date'
    if isinstance(w, forms.NumberInput):
        return 'number'
    return 'text'


def build_fields_meta(form, categories=None):
    """
    Liste de dicts pour itérer les champs dans le template :
    {'name', 'bf', 'label', 'help', 'kind', 'preview_url', 'readonly', 'categorie'}.
    `categories` : {champ: titre} pour afficher un intertitre à chaque changement.
    """
    categories = categories or {}
    meta = []
    for name, field in form.fields.items():
        bf = form[name]
        item = {
            'name': name,
            'bf': bf,
            'label': field.label or pretty_label(name),
            'help': field.help_text or '',
            'kind': field_kind(field, name),
            'preview_url': '',
            'readonly': 'readonly' in field.widget.attrs,
            'categorie': categories.get(name, ''),
        }
        if item['kind'] == 'signature':
            val = bf.value() or form.initial.get(name) or getattr(form.instance, name, None)
            item['preview_url'] = signature_preview_url(val)
        meta.append(item)
    return meta


# ══════════════════════════════════════════════════════════════════
#  FICHE DE CONTRÔLE (ENTRÉE) — 3 étapes
# ══════════════════════════════════════════════════════════════════
_CAT = dict(CATEGORIES)

CONTROLE_ENTETE = ['entree_le', 'immatriculation', 'marque', 'modele', 'kilometrage', 'telephone']

CONTROLE_ETAPE_1 = (CONTROLE_ENTETE
                    + _CAT["Équipements et sécurité"]
                    + _CAT["Habitacle"])

CONTROLE_ETAPE_2 = (_CAT["Extérieur, vitrage et éclairage"]
                    + _CAT["Sous le capot"]
                    + _CAT["Peinture et carrosserie"])

CONTROLE_ETAPE_3 = ['etat_general', 'commentaires', 'nom_technicien', 'signature_technicien']

CONTROLE_ETAPES = [
    ("En-tête, équipements et habitacle", CONTROLE_ETAPE_1),
    ("Extérieur, capot et carrosserie", CONTROLE_ETAPE_2),
    ("Synthèse et signature du technicien", CONTROLE_ETAPE_3),
]

# Intertitres du formulaire (catégorie de chaque champ)
CONTROLE_CATEGORIES_FORM = {
    **{c: "En-tête" for c in CONTROLE_ENTETE},
    **CATEGORIE_DE,
    **{c: "Synthèse" for c in CONTROLE_ETAPE_3},
}


def FicheControleStepForm(step, *args, **kwargs):
    Form = modelform_factory(FicheControle, form=StepFormBase, fields=CONTROLE_ETAPES[step - 1][1])
    form = Form(*args, **kwargs)
    if step == 3:
        form.fields['nom_technicien'].required = True
        form.fields['signature_technicien'].required = True
    return form


# ══════════════════════════════════════════════════════════════════
#  CONTRÔLE DE SORTIE (table temporaire)
#  Seuls les éléments cochés à l'entrée sont affichés, VIDES, et doivent être recochés.
# ══════════════════════════════════════════════════════════════════
SORTIE_CATEGORIES_FORM = {
    'kilometrage_sortie': "Kilométrage",
    **CATEGORIE_DE,
    'commentaires': "Commentaires",
}

_OUI_NON_BOOL = [('True', 'Oui'), ('False', 'Non')]


class ControleSortieFormBase(StepFormBase):
    kilometrage_entree = 0
    a_cocher = ()

    def clean(self):
        cleaned = super().clean()
        for nom in self.a_cocher:
            if nom in self.fields and nom != 'points_degats_carrosserie' \
                    and cleaned.get(nom) in (None, '') and nom not in self.errors:
                self.add_error(nom, "À recocher.")
        return cleaned

    def clean_kilometrage_sortie(self):
        km = self.cleaned_data.get('kilometrage_sortie')
        if km is not None and km < (self.kilometrage_entree or 0):
            raise ValidationError(
                f"Le kilométrage à la sortie ne peut pas être inférieur à celui de l'entrée "
                f"({self.kilometrage_entree} km).")
        return km


def ControleSortieForm(champs, *args, kilometrage_entree=0, avec_km=True, vides=(), **kwargs):
    """
    champs : éléments à recocher (cochés à l'entrée, ou signalés en erreur de saisie).
    vides  : éléments à afficher sans valeur même si la ligne temporaire en a une
             (cases Oui/Non des cric, manivelle, clé de roue).
    """
    fields = (['kilometrage_sortie'] if avec_km else []) + list(champs) + (['commentaires'] if avec_km else [])
    Form = modelform_factory(FicheControleTemporaire, form=ControleSortieFormBase, fields=fields)
    initial = kwargs.pop('initial', None) or {}
    initial.update({n: None for n in vides})
    form = Form(*args, initial=initial, **kwargs)
    form.kilometrage_entree = kilometrage_entree or 0
    form.a_cocher = tuple(champs)
    for nom in champs:
        f = form.fields[nom]
        mf = FicheControleTemporaire._meta.get_field(nom)
        if mf.get_internal_type() == 'BooleanField' and not mf.null:
            # Case à cocher → Oui / Non obligatoire (sinon « non coché » = « pas encore vu »)
            form.fields[nom] = forms.TypedChoiceField(
                label=f.label, choices=_OUI_NON_BOOL, coerce=lambda v: v == 'True',
                widget=forms.RadioSelect(choices=_OUI_NON_BOOL), required=True)
        elif nom != 'points_degats_carrosserie':
            f.required = True
    if 'kilometrage_sortie' in form.fields:
        f = form.fields['kilometrage_sortie']
        f.required = True
        f.label = "Kilométrage à la sortie"
        f.widget.attrs['min'] = form.kilometrage_entree
    return form


# ══════════════════════════════════════════════════════════════════
#  FICHE TECHNIQUE — 3 étapes (alignées sur le nouveau modèle)
# ══════════════════════════════════════════════════════════════════

TECHNIQUE_ETAPE_1 = [  # En-tête + véhicule au sol
    'entree_le', 'nom_client', 'immatriculation', 'vehicule', 'kilometrage',
    'preconisation_courroie_distribution', 'rendre_pieces', 'ecrou_antivol', 'alarme',
    'eclairage_av_veilleuses', 'eclairage_av_croisement', 'eclairage_av_route',
    'eclairage_av_antibrouillard', 'eclairage_av_clignotants',
    'eclairage_ar_feux_position', 'eclairage_ar_stop', 'eclairage_ar_clignotants', 'eclairage_ar_recul',
    'eclairage_ar_antibrouillard', 'eclairage_ar_feu_plaque', 'eclairage_ar_3eme_feu_stop',
    'controle_hauteur_phare', 'voyant_tableau_bord', 'code_defaut', 'sieges', 'bougies_faisceau', 'sonde_lamda',
    'course_pedale_frein', 'course_frein_main', 'liquide_frein_temperature', 'liquide_frein_etat',
    'maitre_cylindre_fuite', 'climatisation_temperature_soufflage', 'climatisation_filtre_habitacle',
    'niveau_huile_prise_en_charge', 'balais_essuie_glace_av', 'balais_essuie_glace_ar', 'pare_brise_impact',
    'pare_brise_fissure', 'pare_brise_fissure_appeler_le', 'jauge_carburant', 'plaques_immatriculation_av',
    'plaques_immatriculation_ar', 'batterie', 'alternateur_demarreur', 'liquide_refroidissement',
    'siege_conducteur_etat', 'siege_passager_etat', 'sieges_arriere_etat', 'ceintures_securite_etat',
]

TECHNIQUE_ETAPE_2 = [  # Mi-hauteur + véhicule levé
    'pneu_av_g_profondeur', 'pneu_av_d_profondeur', 'pneu_ar_g_profondeur', 'pneu_ar_d_profondeur',
    'pneu_roue_secours_profondeur', 'pneu_av_g_usure', 'pneu_av_d_usure', 'pneu_ar_g_usure', 'pneu_ar_d_usure',
    'ecrou_goujons_av_g', 'ecrou_goujons_av_d', 'ecrou_goujons_ar_g', 'ecrou_goujons_ar_d',
    'geometrie_necessaire',
    'susp_amortisseurs_av_g', 'susp_amortisseurs_av_d', 'susp_amortisseurs_ar_g', 'susp_amortisseurs_ar_d',
    'susp_coupelles_av_g', 'susp_coupelles_av_d', 'susp_coupelles_ar_g', 'susp_coupelles_ar_d',
    'susp_ressorts_av_g', 'susp_ressorts_av_d', 'susp_ressorts_ar_g', 'susp_ressorts_ar_d',
    'susp_kit_protection_av_g', 'susp_kit_protection_av_d', 'susp_kit_protection_ar_g', 'susp_kit_protection_ar_d',
    'susp_butees_av_g', 'susp_butees_av_d', 'susp_butees_ar_g', 'susp_butees_ar_d',
    'susp_biellettes_av_g', 'susp_biellettes_av_d', 'susp_biellettes_ar_g', 'susp_biellettes_ar_d',
    'roulements_av_g', 'roulements_av_d', 'roulements_ar_g', 'roulements_ar_d',
    'rotules_av_g', 'rotules_av_d', 'rotules_ar_g', 'rotules_ar_d',
    'bras_de_suspension_av_g', 'bras_de_suspension_av_d', 'bras_de_suspension_ar_g', 'bras_de_suspension_ar_d',
    'silent_bloc_s_av_g', 'silent_bloc_s_av_d', 'silent_bloc_s_ar_g', 'silent_bloc_s_ar_d',
    'frein_flexibles_av_g', 'frein_flexibles_av_d', 'frein_flexibles_ar_g', 'frein_flexibles_ar_d',
    'frein_disques_av_g', 'frein_disques_av_d', 'frein_disques_ar_g', 'frein_disques_ar_d',
    'frein_disques_epaisseur_mm', 'frein_plaquettes_av_g', 'frein_plaquettes_av_d', 'frein_plaquettes_ar_g',
    'frein_plaquettes_ar_d', 'frein_kit_frein_ar_g', 'frein_kit_frein_ar_d', 'frein_tambours_ar_g',
    'frein_tambours_ar_d', 'frein_tambours_diametre_mm',
    'train_flexibles_av_g', 'train_flexibles_av_d', 'train_flexibles_ar_g', 'train_flexibles_ar_d',
    'train_disques_av_g', 'train_disques_av_d', 'train_disques_ar_g', 'train_disques_ar_d',
    'train_plaquettes_av_g', 'train_plaquettes_av_d', 'train_plaquettes_ar_g', 'train_plaquettes_ar_d',
    'train_kit_frein_av_g', 'train_kit_frein_av_d', 'train_tambours_av_g', 'train_tambours_av_d',
    'train_tambours_ar_g', 'train_tambours_ar_d',
    'echap_catalyseur_filtre_particules', 'echap_partie_avant', 'echap_partie_intermediaire',
    'echap_partie_arriere', 'echap_fixations',
    'transmission_soufflets_g', 'transmission_soufflets_d', 'transmission_cardans_g', 'transmission_cardans_d',
    'frein_canalisation', 'frein_cable_frein_main', 'frein_repartiteur_fuite', 'fuite_moteur',
]

TECHNIQUE_ETAPE_3 = [  # Post-contrôles, diagnostic et signature
    'niveau_huile_apres_intervention', 'ok_lave_glace', 'ok_liquide_refroidissement', 'ok_kit_securite',
    'ok_boite_ampoules', 'ok_etiquette_vidange', 'ok_etiquette_monte_pneumatique', 'ok_remise_a_zero_maintenance',
    'ok_pression_des_pneus',
    'diagnostic', 'nom_controleur', 'signature_controleur',
]

# Intertitres de la fiche technique, page 1 (les sièges forment la catégorie « Habitacle »)
TECHNIQUE_CATEGORIES_FORM = {
    **{c: "Véhicule au sol" for c in TECHNIQUE_ETAPE_1},
    **{c: "En-tête" for c in TECHNIQUE_ETAPE_1[:TECHNIQUE_ETAPE_1.index('eclairage_av_veilleuses')]},
    **{c: "Habitacle" for c in ('siege_conducteur_etat', 'siege_passager_etat',
                                'sieges_arriere_etat', 'ceintures_securite_etat')},
}

TECHNIQUE_ETAPES = [
    ("En-tête et véhicule au sol", TECHNIQUE_ETAPE_1),
    ("Mi-hauteur et véhicule levé", TECHNIQUE_ETAPE_2),
    ("Post-contrôles, diagnostic et signature", TECHNIQUE_ETAPE_3),
]


def FicheTechniqueStepForm(step, *args, **kwargs):
    Form = modelform_factory(FicheTechnique, form=StepFormBase, fields=TECHNIQUE_ETAPES[step - 1][1])
    form = Form(*args, **kwargs)
    if step == 3:
        form.fields['nom_controleur'].required = True
        form.fields['signature_controleur'].required = True
    return form
