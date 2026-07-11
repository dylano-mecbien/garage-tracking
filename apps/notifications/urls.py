from django.urls import path
from . import views

urlpatterns = [
    path('destinataires/',  views.destinataires_email,   name='destinataires_email'),
    path('test-email/',     views.test_email_bon_sortie, name='test_email_bon_sortie'),
]