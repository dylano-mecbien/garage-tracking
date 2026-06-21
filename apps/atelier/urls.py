from django.urls import path
from . import views

urlpatterns = [
    # Responsable Atelier
    path('dashboard/', views.dashboard_resp, name='dashboard_atelier'),
    path('or/liste/', views.liste_or, name='liste_or'),
    path('or/creer/', views.creer_or, name='creer_or'),
    path('or/<uuid:or_id>/', views.detail_or, name='detail_or'),
    path('or/<uuid:or_id>/fiche-controle/', views.creer_fiche_controle, name='creer_fiche_controle'),
    path('or/<uuid:or_id>/fiche-technique/', views.creer_fiche_technique, name='creer_fiche_technique'),
    path('or/<uuid:or_id>/tache/ajouter/', views.ajouter_tache, name='ajouter_tache'),
    path('or/<uuid:or_id>/cloture/', views.cloture_or, name='cloture_or'),
    path('or/<uuid:or_id>/reouverture/', views.reouverture_or, name='reouverture_or'),
    path('or/<uuid:or_origine_id>/retour/creer/', views.creer_or_retour, name='creer_or_retour'),
    path('tache/<uuid:tache_id>/assigner/', views.assigner_technicien, name='assigner_technicien'),
    path('kpi/', views.kpi_atelier, name='kpi_atelier'),

    # Technicien
    path('technicien/dashboard/', views.dashboard_technicien, name='dashboard_technicien'),
    path('technicien/mes-taches/', views.mes_taches, name='mes_taches'),
    path('technicien/tache/<uuid:tache_id>/', views.detail_tache, name='detail_tache'),
    path('technicien/tache/<uuid:tache_id>/demarrer/', views.demarrer_tache, name='demarrer_tache'),
    path('technicien/tache/<uuid:tache_id>/compte-rendu/', views.saisir_compte_rendu, name='saisir_compte_rendu'),
    path('technicien/tache/<uuid:tache_id>/terminer/', views.terminer_tache, name='terminer_tache'),
]
