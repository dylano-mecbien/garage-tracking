"""
Vues admin découpées par domaine.

Tout est ré-exporté ici : `from apps.accounts import views` puis
`views.connexion`, `views.admin_clients`… fonctionne comme avant,
donc urls.py n'a pas besoin d'être modifié.
"""
from .auth import (
    changer_langue, changer_theme, connexion, dashboard_redirect,
    deconnexion, index, profil,profil_signature
)
from .users import (
    admin_dashboard, audit_logs_view, creer_utilisateur, editer_utilisateur,
    liste_utilisateurs, reset_password_utilisateur, toggle_utilisateur,
)
from .mouvements import (creer_reception_admin,date_depot_devis,
    detail_entree, detail_or_admin, detail_reception, historique_entrees,
    liste_or, liste_receptions, liste_vehicules_presents, modifier_motif_admin, cloture_or, reouverture_or,
)
from .bons import (
    creer_bon_sortie, creer_bon_sortie_direct, creer_bon_sortie_divers, liste_bons_sortie,
)
from .vehicules import (
    admin_creer_vehicule, admin_modifier_vehicule, admin_mouvements_vehicule,
    admin_vehicules, detail_vehicule, photo_vehicule,
)
from .clients import (
    admin_clients, admin_creer_centre, admin_creer_client, admin_detail_client,
    admin_modifier_centre, admin_modifier_client, admin_supprimer_centre,
)
from .ateliers import admin_ateliers , detail_atelier
