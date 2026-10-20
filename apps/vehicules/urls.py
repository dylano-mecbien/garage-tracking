from django.urls import path

from apps.accounts.views.vehicules import photo_vehicule
from . import views
urlpatterns = [
    path('', views.liste_vehicules, name='liste_vehicules'),
    path('<uuid:vehicule_id>/', views.detail_vehicule, name='detail_vehicule'),
    path('<uuid:vehicule_id>/', photo_vehicule, name='photo_vehicule'),
]
