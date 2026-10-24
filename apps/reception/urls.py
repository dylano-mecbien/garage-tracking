from django.urls import path

from apps.reception import views_or
from . import views


urlpatterns = [
    # ── Dashboard & liste ────────────────────────────────────────
    path('dashboard/',                              views.dashboard,                   name='dashboard_reception'),
    path('liste/',                                  views.liste_receptions,            name='liste_receptions'),
    path('creer/',                                   views.creer_reception,             name='creer_reception'),
        path('<uuid:or_id>/details_or/',               views.detail_or_rec,            name='detail_or_rec'),
    path('Ordre-reparation/',                            views.liste_or,           name='liste_or'),

path('reception/<uuid:rec_id>/ref-devis/', views.ref_devis, name='ref_devis'),

    # ── Réceptions (détail + actions) ────────────────────────────
    path('<uuid:rec_id>/',                          views.detail_reception,            name='detail_reception'),
    path('<uuid:rec_id>/rapport/',                  views.creer_rapport,               name='creer_rapport'),
    path('<uuid:rec_id>/ateliers/',                 views.choisir_ateliers,            name='choisir_ateliers'),
    path('<uuid:rec_id>/bon-sortie/',               views.creer_bon_sortie,            name='creer_bon_sortie_rec'),

    # ── Historique & véhicules présents ──────────────────────────
    path('historique/',                             views.historique_entrees,          name='historique_entrees_rec'),
    path('vehicules-presents/',                     views.liste_vehicules_presents,    name='vehicules_presents_rec'),
    path('entree/<uuid:entree_id>/',                views.detail_entree,               name='detail_entree_rec'),
    path('vehicule/<uuid:vehicule_id>/',            views.detail_vehicule,             name='detail_vehicule_rec'),

    # ── Ordres de réparation ─────────────────────────────────────
    path('or/<uuid:or_id>/cloture/',                views.cloture_or,                  name='cloture_or_rec'),
    path('reception/<uuid:rec_id>/date-depot-devis/', views.date_depot_devis, name='date_depot_devis'),
    path('or/<uuid:or_id>/reouverture/',            views.reouverture_or,              name='reouverture_or_rec'),

    # ── Bons de sortie — liste & export ──────────────────────────
    path('bons-sortie/',                            views.liste_bons_sortie,           name='liste_bons_sortie'),
    path('bons/export-pdf/',                        views.export_bons_pdf,             name='export_bons_liste_pdf'),

    # ── Bons de sortie — création ────────────────────────────────
    path('bons-sortie/creer/',                      views.creer_bon_sortie_direct,     name='creer_bon_sortie_direct'),
    path('bons-sortie/creer-divers/',               views.creer_bon_sortie_divers,     name='creer_bon_sortie_divers'),

    # ── Bons de sortie — détail & actions ────────────────────────
    path('bons-sortie/<uuid:bon_id>/',              views.detail_bon_sortie_guerite,   name='detail_bon_sortie_guerite'),
    path('bons-sortie/<uuid:bon_id>/valider/',      views.valider_bon_sortie_divers,   name='valider_bon_sortie_guerite'),
    path('bons-sortie/<uuid:bon_id>/validerAdmin/', views.valider_bon_sortie_vehicule, name='valider_bon_sortie_super'),
    path('bons-sortie/<uuid:bon_id>/pdf/',          views.pdf_bon_sortie_guerite,      name='pdf_bon_sortie_guerite'),

    # ── Bons de sortie — alias reception (bon/<id>) ──────────────
    path('bon/<uuid:bon_id>/pdf/',                  views.pdf_bon_sortie,              name='pdf_bon_sortie_rec'),

    # ── Autocomplete & AJAX ──────────────────────────────────────
    path('autocomplete/vehicules-presents/',        views.autocomplete_vehicules_presents, name='autocomplete_vehicules_presents'),
    path('autocomplete/vehicules-reception/',        views.autocomplete_vehicules_reception, name='autocomplete_vehicules_reception'),
    path('autocomplete/demandeur/',                 views.autocomplete_demandeur,      name='autocomplete_demandeur'),
    path('demandeur/creer-ajax/',                   views.creer_demandeur_ajax,        name='creer_demandeur_ajax'),
    path('api/vehicules/',                          views.api_vehicules,               name='api_vehicules'),
    path('api/entrees_vehicule/',                   views.api_entrees_vehicule,        name='api_entrees_vehicule'),

    # ── Notifications ────────────────────────────────────────────
    path('notifs/json/',                            views.notifs_json,                 name='notifs_json_rec'),
    path('notifs/lues/',                            views.marquer_lues,                name='marquer_lues_rec'),

    # ── Bases — Véhicules ────────────────────────────────────────
    path('vehicules/',                              views.rec_vehicules,               name='rec_vehicules'),
    path('vehicules/<uuid:vehicule_id>/modifier/',  views.rec_modifier_vehicule,       name='rec_modifier_vehicule'),
    path('vehicules/<uuid:vehicule_id>/mouvements/', views.rec_mouvements_vehicule,    name='rec_mouvements_vehicule'),
    path('vehicules/export-pdf/',                   views.export_vehicules_pdf,        name='export_vehicules_pdf'),
    path(
            "entrees/<uuid:entree_id>/modifier-motif/",
            views.modifier_motif_reception,
            name="modifier_motif_reception"
        ),


    path('reception/<uuid:rec_id>/creer-or/',
         views_or.creer_or_depuis_fiche_technique, name='creer_or_depuis_fiche_technique'),

    path('fiches-techniques/<uuid:fiche_id>/pdf/', views_or.pdf_fiche_technique, name='pdf_fiche_technique'),
    path('fiches-controle/<uuid:fiche_id>/pdf/', views_or.pdf_fiche_controle, name='pdf_fiche_controle'),

    # ── Bases — Clients ──────────────────────────────────────────
    path('clients/',                                views.rec_clients,                 name='rec_clients'),
    path('clients/<uuid:client_id>/',               views.rec_detail_client,           name='rec_detail_client'),


    path('clients/<uuid:client_id>/creer/',     views.creer_centre,     name='creer_centre'),
    path('clients/<uuid:centre_id>/modifier/',     views.modifier_centre,     name='modifier_centre'),
    path('clients/<uuid:centre_id>/supp/',     views.supprimer_centre,     name='supprimer_centre'),

    path('clients/<uuid:client_id>/modifier/',      views.rec_modifier_client,         name='rec_modifier_client'),
    path('client/export-pdf/',                      views.export_client_pdf,           name='export_client_pdf'),

    # ── Bases — Conducteurs ──────────────────────────────────────
    path('conducteurs/',                            views.rec_conducteurs,             name='rec_conducteurs'),
]