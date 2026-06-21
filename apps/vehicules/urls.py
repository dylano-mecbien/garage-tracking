from django.urls import path
from . import views
urlpatterns = [
    path('', views.liste_vehicules, name='liste_vehicules'),
    path('<uuid:vehicule_id>/', views.detail_vehicule, name='detail_vehicule'),
]
