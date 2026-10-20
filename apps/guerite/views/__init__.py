"""
Vues Guérite découpées par domaine.

Tout est ré-exporté ici : `from apps.guerite import views` puis
`views.dashboard` → urls.py inchangé.
"""
# Helpers / constantes potentiellement importés ailleurs
from ._utils import (
    PHOTO_FIELDS, entrees_presentes_qs, get_entree_non_sortie,
    get_entrees_presentes_filtrees, get_filtered_entrees,
)

from .dashboard import (
    consulter_bon_sortie, dashboard, detail_entree, historique_entrees, liste_vehicules_presents,
)
from .entrees import enregistrer_entree, enregistrer_sortie, modifier_motif_entree, nouvelle_entree
from .referentiels import (
    creer_client, creer_conducteur, creer_vehicule, modifier_vehicule,
    modifier_vehicule_recherche, recherche_vehicule,
)
from .api import (
    autocomplete_clients, autocomplete_conducteurs, autocomplete_inventaires,
    autocomplete_marques, autocomplete_modeles, autocomplete_vehicules,
    creer_client_ajax, creer_conducteur_ajax,
)
