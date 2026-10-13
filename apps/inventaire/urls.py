from django.urls import path
from . import views

urlpatterns = [
    # Guérite
    path('', views.accueil, name='inventaire_accueil'),
    path('demarrer/', views.demarrer, name='inventaire_demarrer'),
    path('<uuid:inv_id>/', views.detail, name='inventaire_detail'),
    path('<uuid:inv_id>/marquer/', views.marquer, name='inventaire_marquer'),
    path('<uuid:inv_id>/plaque/', views.verifier_plaque, name='inventaire_verifier_plaque'),
    path('<uuid:inv_id>/faire-entrer/', views.ajouter_entree, name='inventaire_ajouter_entree'),
    path('<uuid:inv_id>/mouvement/<uuid:mv_id>/supprimer/', views.supprimer_mouvement, name='inventaire_supprimer_mouvement'),
    path('<uuid:inv_id>/valider/', views.soumettre, name='inventaire_soumettre'),
    # Administration
    path('admin/inventaire/', views.admin_liste, name='inventaire_admin_liste'),
    path('admin/inventaire/<uuid:inv_id>/', views.admin_detail, name='inventaire_admin_detail'),
    path('admin/inventaire/<uuid:inv_id>/valider/', views.admin_valider, name='inventaire_admin_valider'),
    path('admin/inventaire/<uuid:inv_id>/revoquer/', views.admin_revoquer, name='inventaire_admin_revoquer'),
]
