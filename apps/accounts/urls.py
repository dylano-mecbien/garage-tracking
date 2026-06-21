from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('connexion/', views.connexion, name='connexion'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('profil/', views.profil, name='profil'),
    path('langue/', views.changer_langue, name='changer_langue'),
    path('theme/', views.changer_theme, name='changer_theme'),
]
