from django.urls import path
from . import views
urlpatterns = [
    path('logs/', views.audit_logs, name='audit_logs_module'),
]
