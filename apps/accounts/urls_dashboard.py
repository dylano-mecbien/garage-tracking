
from django.urls import path
from . import views
from . import admin_views_conducteurs_nettoyage as views2
from .views_user_stats import detail_utilisateur


urlpatterns = [
    path('', views.dashboard_redirect, name='dashboard'),
    # Admin

    path('admin-garage/audit/', views.audit_logs_view, name='audit_logs'),
    path('admin-garage/bons-sortie/',  views.liste_bons_sortie,         name='liste_bons_admin'),
    path('Ordre-reparation/admin/',                            views.liste_or,           name='liste_or_admin'),
    path('<uuid:or_id>/details_or/',               views.detail_or_admin,            name='detail_or_admin'),
        
    

    path('admin-garage/bons-sortie/creer-divers/',            views.creer_bon_sortie_divers,    name='creer_bon_divers_admin'),
    path('admin-garage/bons-sortie/creer/',                        views.creer_bon_sortie_direct,   name='creer_bon_direct_admin'),
    path('entree/<uuid:entree_id>/', views.detail_entree, name='detail_entree_admin'),
     path('utilisateurs/<uuid:user_id>/', detail_utilisateur, name='detail_utilisateur'),
    path('admin-garage/<uuid:rec_id>/rec',                          views.detail_reception,            name='detail_rec_admin'),

    path('admin-garage/<uuid:rec_id>/bon-sortie/',            views.creer_bon_sortie,   name='creer_sortie_lien_admin'),
 
    path('admin-garage/historique/',                          views.historique_entrees, name='historique_entrees_admin'),
    path('admin-garage/vehicules-presents/',            views.liste_vehicules_presents, name='vehicules_presents_admin'),
    path('admin-garage/liste-receptions/',                               views.liste_receptions,   name='liste_receptions_admin'),
    # ── Véhicules ──────────────────────────────────────────────────
  
    path('admin-garage/vehicule/<uuid:vehicule_id>/',         views.detail_vehicule,    name='detail_vehicule_admin'),

     # Ateliers
    path('ateliers/',                              views.admin_ateliers,                name='admin_ateliers'),
 
    path('dashboard/',                     views.admin_dashboard,             name='admin_dashboard'),
    path('utilisateurs/',                  views.liste_utilisateurs,          name='liste_utilisateurs'),
    path('utilisateurs/creer/',            views.creer_utilisateur,           name='creer_utilisateur'),
    path('utilisateurs/<uuid:user_id>/editer/',        views.editer_utilisateur,          name='editer_utilisateur'),
    path('utilisateurs/<uuid:user_id>/reset-pwd/',     views.reset_password_utilisateur,  name='reset_password_utilisateur'),
    path('utilisateurs/<uuid:user_id>/toggle/',        views.toggle_utilisateur,          name='toggle_utilisateur'),
    path('audit/',                         views.audit_logs_view,             name='audit_logs'),
    # Véhicules
    path('vehicules/',                                views.admin_vehicules,               name='admin_vehicules'),
    path('vehicules/creer-vehicule/',                 views.admin_creer_vehicule, name='creer_vehicule_admin'),
    path('vehicules/<uuid:vehicule_id>/modifier/',    views.admin_modifier_vehicule,       name='admin_modifier_vehicule'),
    path('vehicules/<uuid:vehicule_id>/mouvements/',  views.admin_mouvements_vehicule,     name='admin_mouvements_vehicule'),
    path(
        "entrees/<uuid:entree_id>/modifier-motif/",
        views.modifier_motif_admin,
        name="modifier_motif_admin"
    ),
    # Clients
    path('clients/',                               views.admin_clients,             name='admin_clients'),
    path('clients/creer-vehicule/',             views.admin_creer_client, name='creer_client_admin'),
    path('clients/<uuid:client_id>/',              views.admin_detail_client,       name='admin_detail_client'),
    path('clients/<uuid:client_id>/modifier/',     views.admin_modifier_client,     name='admin_modifier_client'),
    # Conducteurs
    path('conducteurs/',                              views2.admin_conducteurs,             name='admin_conducteurs'),
    path('conducteurs/<uuid:cond_id>/supprimer/',     views2.admin_supprimer_conducteur,    name='admin_supprimer_conducteur'),
    # Nettoyage
    path('nettoyage/',                                views2.admin_nettoyage,                       name='admin_nettoyage'),
    path('nettoyage/vehicules/',                      views2.admin_supprimer_vehicules_orphelins,   name='admin_supprimer_vehicules_orphelins'),
    path('nettoyage/clients/',                        views2.admin_supprimer_clients_orphelins,     name='admin_supprimer_clients_orphelins'),
    path('nettoyage/conducteurs/',                    views2.admin_supprimer_conducteurs_orphelins, name='admin_supprimer_conducteurs_orphelins'),
    # Langue/Thème
    path('langue/',                        views.changer_langue,              name='changer_langue'),
    path('theme/',                         views.changer_theme,               name='changer_theme'),

]


