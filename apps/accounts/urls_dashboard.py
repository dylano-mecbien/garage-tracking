from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_redirect, name='dashboard'),
    # Admin
    path('admin-garage/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-garage/utilisateurs/', views.liste_utilisateurs, name='liste_utilisateurs'),
    path('admin-garage/utilisateurs/creer/', views.creer_utilisateur, name='creer_utilisateur'),
    path('admin-garage/utilisateurs/<uuid:user_id>/editer/', views.editer_utilisateur, name='editer_utilisateur'),
    path('admin-garage/utilisateurs/<uuid:user_id>/reset-password/', views.reset_password_utilisateur, name='reset_password_utilisateur'),
    path('admin-garage/utilisateurs/<uuid:user_id>/toggle/', views.toggle_utilisateur, name='toggle_utilisateur'),
    path('admin-garage/audit/', views.audit_logs_view, name='audit_logs'),
]
