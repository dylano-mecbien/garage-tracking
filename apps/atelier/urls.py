from django.urls import path

from apps.atelier import views_fiches, views_lecture
from . import views

urlpatterns = [
    # ── Responsable atelier ──────────────────────────────────
    path('dashboard/',                       views.dashboard_atelier,      name='dashboard_atelier'),
    path('or/',                    views.liste_or_atelier,       name='liste_or_atelier'),
    path('or/<uuid:or_id>/',       views.detail_or_atelier,      name='detail_or_atelier'),
    path('atelier/<uuid:rec_id>/',      views.detail_reception,            name='detail_reception_atelier'),
    path('liste/',                                  views.liste_receptions,            name='liste_receptions_atelier'),



    path('or/<uuid:or_id>/taches/',           views.creer_modifier_tache, name='creer_modifier_tache'),
    path('tache/<uuid:tache_id>/supprimer/',  views.supprimer_tache,       name='supprimer_tache'),
    path('tache/<uuid:tache_id>/cloture-directe/', views.cloture_directe_tache, name='cloture_directe_tache'),

    path('or/<uuid:or_id>/cloture/',     views.cloture_or_atelier,     name='cloture_or_atelier'),
    path('or/<uuid:or_id>/reouverture/', views.reouverture_or_atelier, name='reouverture_or_atelier'),

    path('techniciens/',                 views.liste_techniciens,  name='liste_techniciens'),
    path('techniciens/<uuid:tech_id>/',  views.detail_technicien,  name='detail_technicien'),

    # ── Technicien ───────────────────────────────────────────
    path('technicien/',                                views.dashboard_technicien,    name='dashboard_technicien'),
    path('technicien/taches/',                         views.mes_taches,              name='mes_taches'),
    path('technicien/tache/<uuid:tache_id>/',          views.detail_tache,            name='detail_tache'),
    path('technicien/tache/<uuid:tache_id>/demarrer/', views.demarrer_tache,          name='demarrer_tache'),
    path('technicien/tache/<uuid:tache_id>/cr/',       views.soumettre_compte_rendu,  name='soumettre_compte_rendu'),

    # Visualisation (lecture seule)
    path('reception/<uuid:rec_id>/fiche-controle/voir/',
         views_lecture.voir_fiche_controle, name='voir_fiche_controle'),
         
    path('reception/<uuid:rec_id>/fiche-technique/voir/',
         views_lecture.voir_fiche_technique, name='voir_fiche_technique'),


    # Fiches (3 pages chacune) — atelier
    path('reception/<uuid:rec_id>/fiche-controle/page/<int:step>/',
         views_fiches.creer_fiche_controle_etape, name='creer_fiche_controle_etape'),
    path('reception/<uuid:rec_id>/fiche-technique/page/<int:step>/',
         views_fiches.creer_fiche_technique_etape, name='creer_fiche_technique_etape'),

    # Réceptionniste
    path('reception/<uuid:rec_id>/valider-reception/',
         views_fiches.signer_fiche_controle, name='signer_fiche_controle'),

    # OR reçu par l'atelier → tâches
    path('or/<uuid:or_id>/taches/creer/', views.creer_tache, name='creer_tache'),
    path('tache/<uuid:tache_id>/valider/',    views.valider_tache_chef,    name='valider_tache_chef'),


]
