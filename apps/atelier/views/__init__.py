"""
Vues Atelier découpées par rôle.

Tout est ré-exporté ici :
  - `from apps.atelier import views` puis `views.dashboard_atelier` → urls.py inchangé
  - `from apps.atelier.views import _entree_from_or, enrich_taches_duree`
    (utilisé par reception et accounts) continue de fonctionner.
"""
# Helpers utilisés par d'autres apps
from ._utils import (
    _entree_from_or, enrich_taches_duree, format_duree, get_atelier_du_resp,
    parse_duree_hm, techniciens_assignables,
)

# Alias de compatibilité (ancien doublon de get_atelier_du_resp)
_mon_atelier = get_atelier_du_resp

from .resp import (
    cloture_or_atelier, dashboard_atelier, detail_or_atelier, detail_reception,
    detail_technicien, liste_or_atelier, liste_receptions, liste_techniciens, detail_atelier,
)
from .taches import (
    cloture_directe_tache, creer_modifier_tache, creer_tache, supprimer_tache, valider_tache_chef,refuser_tache,
)
from .fiches import creer_fiche_controle, creer_fiche_technique
from .technicien import (
    dashboard_technicien, demarrer_tache, detail_tache, mes_taches, soumettre_compte_rendu,
)
