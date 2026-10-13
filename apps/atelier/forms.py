"""
apps/atelier/forms.py

Chaque fiche = exactement 3 pages :
  1. En-tête et sécurité
  2. Éléments mécaniques et intérieur
  3. Synthèse et signature du technicien

Les formulaires de chaque page sont générés depuis le modèle (modelform_factory).
Les signatures sont converties en fichiers image et stockées en chemin dans le champ.
"""
import base64
import uuid
import logging

from django import forms
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.forms import modelform_factory

from .models import FicheControle, FicheTechnique

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
    (local ou MinIO) et retourne le chemin relatif.

    Retourne :
        - str  : chemin du fichier (ex: "signatures/client_abc123.png")
        - None : si la conversion échoue
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
        'entree_le', 'sortie_le', 'immatriculation', 'telephone','nom_client','vehicule', 
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, f in self.fields.items():

            # ══════════════════════════════════════════════
            #  1) D'ABORD : appliquer les widgets normaux
            # ══════════════════════════════════════════════

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

            # ══════════════════════════════════════════════
            #  2) ENSUITE : marquer les champs verrouillés
            # ══════════════════════════════════════════════
            if name in self.READONLY_FIELDS:
                f.disabled = True
                f.required = False

                # On AJOUTE la classe sans écraser l'existante
                existing = f.widget.attrs.get('class', '')
                if 'fi-locked' not in existing:
                    f.widget.attrs['class'] = f"{existing} fi-locked".strip()


# ══════════════════════════════════════════════════════════════
    #  ✅ NOUVEAU : normaliser les booléens nullables
    # ══════════════════════════════════════════════════════════════
    def clean(self):
        """
        Convertit les chaînes vides en None pour les champs
        BooleanField(null=True), sinon PostgreSQL rejette l'INSERT
        avec 'invalid input syntax for type boolean: ""'.
        """
        cleaned = super().clean()

        from django.db import models as dj_models

        for field in self._meta.model._meta.fields:
            name = field.name
            if name not in cleaned:
                continue

            # Booléen nullable → '' devient None
            if isinstance(field, dj_models.BooleanField) and field.null:
                if cleaned[name] in ('', 'None'):
                    cleaned[name] = None

            # Entier nullable → '' devient None
            elif isinstance(field, (dj_models.IntegerField, dj_models.BigIntegerField,
                                    dj_models.PositiveIntegerField,
                                    dj_models.PositiveSmallIntegerField)) and field.null:
                if cleaned[name] == '':
                    cleaned[name] = None

            # Décimal nullable → '' devient None
            elif isinstance(field, dj_models.DecimalField) and field.null:
                if cleaned[name] == '':
                    cleaned[name] = None

            # Date/DateTime nullables → '' devient None
            elif isinstance(field, (dj_models.DateField, dj_models.DateTimeField)) and field.null:
                if cleaned[name] == '':
                    cleaned[name] = None

        return cleaned

    def clean_points_degats_carrosserie(self):
        v = self.cleaned_data.get('points_degats_carrosserie')
        return v if isinstance(v, list) else []



    # ── Nettoyage des signatures : dataURL → chemin de fichier ──
    def _clean_signature(self, name):
        value = self.cleaned_data.get(name)
        if not value:
            return value

        if isinstance(value, str) and not value.startswith('data:'):
            return value

        folder = 'signatures/controle' if 'FicheControle' in self.__class__.__name__ \
                 else 'signatures/technique'
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
    if isinstance(w, forms.CheckboxSelectMultiple):
        return 'checkbox-multiple'
    if isinstance(w, forms.SelectMultiple):
        return 'select-multiple'
    if isinstance(w, forms.Select):
        return 'select'
    if isinstance(w, forms.Textarea):
        return 'textarea'
    if isinstance(w, forms.DateInput):
        return 'date'
    if isinstance(w, forms.DateTimeInput):
        return 'datetime'
    if isinstance(w, forms.NumberInput):
        return 'number'
    return 'text'


def build_fields_meta(form):
    """
    Prépare les métadonnées pour itérer les champs dans le template.
    Retourne une liste de dicts :
    [{'name', 'bf' (BoundField), 'label', 'help', 'kind', 'preview_url'}, ...]
    """
    meta = []
    for name, field in form.fields.items():
        bf = form[name]                     # ← BoundField (essentiel !)

        item = {
            'name':     name,
            'bf':       bf,
            'label':    field.label or pretty_label(name),
            'help':     field.help_text or '',
            'kind':     field_kind(field, name),
            'preview_url': '',
        }

        # URL de prévisualisation pour les signatures
        if item['kind'] == 'signature':
            val = bf.value() or form.initial.get(name) or getattr(form.instance, name, None)
            item['preview_url'] = signature_preview_url(val)

        meta.append(item)
    return meta


# ══════════════════════════════════════════════════════════════════
#  FICHE DE CONTRÔLE — 3 étapes
# ══════════════════════════════════════════════════════════════════

CONTROLE_ETAPE_1 = [   # En-tête et sécurité
    'entree_le', 'immatriculation', 'marque', 'modele',
    'kilometrage', 'telephone',
    'alarme_fonctionne', 'verrouillage_portes', 'telecommande_ouverture', 'trappe_carburant',
    'tirette_capot', 'climatisation_fonctionne', 'climatisation_fait_froid', 'voyant_moteur_tableau_bord',
    'autoradio_s_allume', 'son_dans_baffles', 'dossier_vehicule_complet', 'horloge_a_heure',
    'triangles_securite_presents', 'triangles_securite_nombre', 'cales_metalliques_presentes',
    'cales_metalliques_nombre', 'gilet_securite_present', 'extincteur_present', 'boite_pharmacie_presente',
    'bouton_eclairage_plafonnier', 'roue_secours_gonflee', 'cric_present', 'manivelle_presente',
    'cle_roue_presente', 'joints_portieres_propres', 'enjoliveurs_roues_presents',
    'plaques_immatriculation_avant_arriere', 'tares_avant_arriere_presentes',
    'garde_boues_presents_bien_montes', 'agrafes_presentes',
]

CONTROLE_ETAPE_2 = [   # Éléments mécaniques et intérieur
    'bavettes_et_goujons_roues_presents', 'pare_brise_etat', 'pression_pneus_bonne',
    'balais_essuie_glace_avant_arriere', 'gicleur_lave_glace_bocal_reserve', 'miroirs_retroviseurs_etat',
    'retroviseurs_se_rabattent', 'phares_avant_etat', 'camera_recul_fonctionne', 'klaxon_fonctionne',
    'clignotants_avant_arriere_fonctionnent', 'capteurs_position_avant_arriere_bipent',
    'antibrouillards_feux_jour_bon_etat', 'feux_arriere_etat', 'systeme_demarrage_fonctionne',
    'voyant_ceintures_securite_s_allume',
    'sieges_propres_bon_etat', 'tapis_sol_5_presents', 'vitres_avant_se_baissent', 'vitres_arriere_se_baissent',
    'telecommande_vitres_fonctionne', 'autocollants_pare_brise_presents', 'voiles_peinture_sur_vitres',
    'jauge_carburant', 'type_vehicule', 'points_degats_carrosserie',
]

CONTROLE_ETAPE_3 = [   # Synthèse et signature du technicien
    'etat_general', 'commentaires',
    'nom_technicien', 'signature_technicien',
]

CONTROLE_ETAPES = [
    ("En-tête et sécurité", CONTROLE_ETAPE_1),
    ("Éléments mécaniques et intérieur", CONTROLE_ETAPE_2),
    ("Synthèse et signature du technicien", CONTROLE_ETAPE_3),
]


def FicheControleStepForm(step, *args, **kwargs):
    Form = modelform_factory(
        FicheControle,
        form=StepFormBase,
        fields=CONTROLE_ETAPES[step - 1][1],
    )
    form = Form(*args, **kwargs)
    if step == 3:
        form.fields['nom_technicien'].required = True
        form.fields['signature_technicien'].required = True
    return form


# ══════════════════════════════════════════════════════════════════
#  FICHE TECHNIQUE — 3 étapes
# ══════════════════════════════════════════════════════════════════

TECHNIQUE_ETAPE_1 = [  # En-tête et sécurité (+ véhicule au sol)
    'entree_le',  'nom_client', 'immatriculation', 'vehicule', 
    'preconisation_courroie_distribution', 'rendre_pieces', 'ecrou_antivol', 'alarme',
    'eclairage_av_veilleuses', 'eclairage_av_croisement', 'eclairage_av_route',
    'eclairage_av_antibrouillard', 'eclairage_av_clignotants',
    'eclairage_ar_feux_position', 'eclairage_ar_stop', 'eclairage_ar_clignotants', 'eclairage_ar_recul',
    'eclairage_ar_antibrouillard', 'eclairage_ar_feu_plaque', 'eclairage_ar_3eme_feu_stop',
    'controle_hauteur_phare', 'voyant_tableau_bord', 'code_defaut', 'bougies_faisceau', 'sonde_lamda',
    'course_pedale_frein', 'course_frein_main', 'liquide_frein_temperature', 'liquide_frein_etat',
    'maitre_cylindre_fuite', 'climatisation_temperature_soufflage', 'climatisation_filtre_habitacle',
    'niveau_huile_prise_en_charge', 'balais_essuie_glace_av', 'balais_essuie_glace_ar', 'pare_brise_impact',
    'pare_brise_fissure', 'pare_brise_fissure_appeler_le', 'jauge_carburant', 'plaques_immatriculation_av',
    'plaques_immatriculation_ar', 'batterie', 'alternateur_demarreur', 'liquide_refroidissement',
]

TECHNIQUE_ETAPE_2 = [  # Éléments mécaniques (mi-hauteur + véhicule levé)
    'pneu_av_g_profondeur', 'pneu_av_d_profondeur', 'pneu_ar_g_profondeur', 'pneu_ar_d_profondeur',
    'pneu_roue_secours_profondeur', 'pneu_av_g_usure', 'pneu_av_d_usure', 'pneu_ar_g_usure', 'pneu_ar_d_usure',
    'geometrie_necessaire',
    'susp_amortisseurs_av_g', 'susp_amortisseurs_av_d', 'susp_amortisseurs_ar_g', 'susp_amortisseurs_ar_d',
    'susp_coupelles_av_g', 'susp_coupelles_av_d', 'susp_coupelles_ar_g', 'susp_coupelles_ar_d',
    'susp_ressorts_av_g', 'susp_ressorts_av_d', 'susp_ressorts_ar_g', 'susp_ressorts_ar_d',
    'susp_kit_protection_av_g', 'susp_kit_protection_av_d', 'susp_kit_protection_ar_g', 'susp_kit_protection_ar_d',
    'susp_butees_av_g', 'susp_butees_av_d', 'susp_butees_ar_g', 'susp_butees_ar_d',
    'susp_biellettes_av_g', 'susp_biellettes_av_d', 'susp_biellettes_ar_g', 'susp_biellettes_ar_d',
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

TECHNIQUE_ETAPE_3 = [  # Synthèse et signature du technicien
    'niveau_huile_apres_intervention', 'ok_lave_glace', 'ok_liquide_refroidissement', 'ok_kit_securite',
    'ok_boite_ampoules', 'ok_etiquette_vidange', 'ok_etiquette_monte_pneumatique', 'ok_remise_a_zero_maintenance',
    
    'commentaires',     'nom_controleur', 'signature_controleur',
]

TECHNIQUE_ETAPES = [
    ("En-tête et sécurité", TECHNIQUE_ETAPE_1),
    ("Éléments mécaniques et intérieur", TECHNIQUE_ETAPE_2),
    ("Synthèse et signature du technicien", TECHNIQUE_ETAPE_3),
]


def FicheTechniqueStepForm(step, *args, **kwargs):
    Form = modelform_factory(
        FicheTechnique,
        form=StepFormBase,
        fields=TECHNIQUE_ETAPES[step - 1][1],
    )
    form = Form(*args, **kwargs)
    if step == 3:
        form.fields['nom_controleur'].required = True
        form.fields['signature_controleur'].required = True
    return form




