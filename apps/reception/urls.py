from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/',                           views.dashboard,          name='dashboard_reception'),
    path('liste/',                               views.liste_receptions,   name='liste_receptions'),
    path('creer/',                               views.creer_reception,    name='creer_reception'),
    path('<uuid:rec_id>/',                       views.detail_reception,   name='detail_reception'),
    path('<uuid:rec_id>/rapport/',               views.creer_rapport,      name='creer_rapport'),
    path('<uuid:rec_id>/ateliers/',              views.choisir_ateliers,   name='choisir_ateliers'),
    path('<uuid:rec_id>/or/',                    views.creer_or,           name='creer_or_rec'),

    path('historique/',                          views.historique_entrees, name='historique_entrees_rec'),
    path('vehicule/<uuid:vehicule_id>/',         views.detail_vehicule,    name='detail_vehicule_rec'),
    path('or/<uuid:or_id>/cloture/',             views.cloture_or,         name='cloture_or_rec'),
    path('or/<uuid:or_id>/reouverture/',         views.reouverture_or,     name='reouverture_or_rec'),
    path('bon/<uuid:bon_id>/',                   views.detail_bon_sortie,  name='detail_bon_sortie_rec'),
    path('bon/<uuid:bon_id>/pdf/',               views.pdf_bon_sortie,     name='pdf_bon_sortie_rec'),
    path('notifs/json/',                         views.notifs_json,        name='notifs_json_rec'),
    path('notifs/lues/',                         views.marquer_lues,       name='marquer_lues_rec'),
     path('vehicules-presents/', views.liste_vehicules_presents, name='vehicules_presents_rec'),

    path('<uuid:rec_id>/bon-sortie/',            views.creer_bon_sortie,   name='creer_bon_sortie_rec'),

    path('bons-sortie/creer/',                        views.creer_bon_sortie_direct,   name='creer_bon_sortie_direct'),
        path('entree/<uuid:entree_id>/', views.detail_entree, name='detail_entree_rec'),


        # ── Bons de sortie ──────────────────────────────────────────
    path('bons-sortie/',                              views.liste_bons_sortie,         name='liste_bons_sortie'),
    path('bons-sortie/<uuid:bon_id>/',                views.detail_bon_sortie_guerite, name='detail_bon_sortie_guerite'),
    path('bons-sortie/<uuid:bon_id>/valider/',        views.valider_bon_sortie_guerite,name='valider_bon_sortie_guerite'),
    path('bons-sortie/<uuid:bon_id>/pdf/',            views.pdf_bon_sortie_guerite,    name='pdf_bon_sortie_guerite'),
    path('bons-sortie/creer-divers/',            views.creer_bon_sortie_divers,    name='creer_bon_sortie_divers'),
    path('autocomplete/vehicules-presents/', views.autocomplete_vehicules_presents, name='autocomplete_vehicules_presents'),


]
 


 