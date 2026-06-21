from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard_guerite'),
    path('recherche/', views.recherche_vehicule, name='recherche_vehicule'),
    path('vehicules-presents/', views.liste_vehicules_presents, name='vehicules_presents'),
    path('historique/', views.historique_entrees, name='historique_entrees'),
    path('historique/export/excel/', views.export_entrees_excel, name='export_entrees_excel'),
    path('historique/export/pdf/', views.export_entrees_pdf, name='export_entrees_pdf'),

    # Nouvelle entrée
    path('entree/recherche/', views.recherche_vehicule, name='nouvelle_entree'),
    path('entree/nouvelle/', views.nouvelle_entree, name='entre_vehicule'),
    path('autocomplete/conducteurs/', views.autocomplete_conducteurs, name='autocomplete_conducteurs'),
   
    path('entree/creer-client/', views.creer_client, name='creer_client_guerite'),
    path('entree/creer-conducteur/', views.creer_conducteur, name='creer_conducteur_guerite'),
    path('entree/creer-vehicule/', views.creer_vehicule, name='creer_vehicule_guerite'),
    path('entree/enregistrer/', views.enregistrer_entree, name='enregistrer_entree'),
    path('entree/<uuid:entree_id>/', views.detail_entree, name='detail_entree'),
    path(
    "entrees/<uuid:entree_id>/modifier-motif/",
    views.modifier_motif_entree,
    name="modifier_motif_entree"
),

    # Sortie
    path('sortie/<uuid:entree_id>/', views.enregistrer_sortie, name='enregistrer_sortie'),
    path('bon-sortie/consulter/', views.consulter_bon_sortie, name='consulter_bon_sortie'),


 
    # ── AJAX ────────────────────────────────────────────────────
    path('ajax/clients/',             views.autocomplete_clients,    name='autocomplete_clients'),
    path('ajax/client/creer/',        views.creer_client_ajax,       name='creer_client_ajax'),
    path('ajax/conducteurs/',         views.autocomplete_conducteurs, name='autocomplete_conducteurs'),
    path('ajax/conducteur/creer/',    views.creer_conducteur_ajax,   name='creer_conducteur_ajax'),
    # urls.py
    path('autocomplete/marques/', views.autocomplete_marques, name='autocomplete_marques'),

    path('autocomplete/modeles/', views.autocomplete_modeles, name='autocomplete_modeles'),

]
