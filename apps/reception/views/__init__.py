"""
Vues Réception découpées par domaine.

Tout est ré-exporté ici :
  - `from apps.reception import views` puis `views.dashboard` → urls.py inchangé
  - `from apps.reception.views import _gen_qr, paginate_queryset, ...`
    (utilisé par apps.accounts) continue de fonctionner.
"""
# Helpers utilisés par d'autres apps
from ._utils import (
    _gen_qr, _notifier, get_entrees_presentes_filtrees, get_filtered_entrees,
    paginate_queryset, save_signature_from_dataurl,
)

from .dashboard import dashboard, marquer_lues, notifs_json
from .receptions import (
    choisir_ateliers, creer_rapport, creer_reception, detail_entree, detail_reception,
    detail_vehicule, historique_entrees, liste_receptions, liste_vehicules_presents,
    modifier_motif_reception,ref_devis,
)
from .ors import cloture_or, detail_or_rec, liste_or, reouverture_or,date_depot_devis
from .bons import (
    creer_bon_sortie, creer_bon_sortie_direct, creer_bon_sortie_divers,
    detail_bon_sortie_guerite, export_bons_pdf, liste_bons_sortie, pdf_bon_sortie,
    pdf_bon_sortie_guerite, valider_bon_sortie_divers, valider_bon_sortie_vehicule,
)
from .api import (
    api_entrees_vehicule, api_vehicules, autocomplete_demandeur,
    autocomplete_vehicules_presents, autocomplete_vehicules_reception, creer_demandeur_ajax,
)
from .referentiels import (
    export_client_pdf, export_vehicules_pdf, rec_clients, rec_conducteurs,
    rec_detail_client, rec_modifier_client, rec_modifier_vehicule,
    rec_mouvements_vehicule, rec_vehicules,creer_centre, modifier_centre, supprimer_centre,
)
