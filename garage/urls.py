from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Garage Suivi API",
        default_version='v1',
        description="API complète de gestion de garage automobile",
        contact=openapi.Contact(email="admin@garage.cm"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Auth & Dashboard
    path('auth/', include('apps.accounts.urls')),
    path('dashboard/', include('apps.accounts.urls_dashboard')),

    # Métier
    path('admin/', include('apps.accounts.urls_dashboard')),
    path('guerite/', include('apps.guerite.urls')),
    path('reception/', include('apps.reception.urls')),
    path('atelier/', include('apps.atelier.urls')),
    path('vehicules/', include('apps.vehicules.urls')),
    path('documents/', include('apps.documents.urls')),
    path('audit/', include('apps.audit.urls')),
    path('admin-garage/notifications/', include('apps.notifications.urls')),
    # API REST
    path('api/v1/', include([
        path('auth/', include('apps.accounts.api_urls')),
        path('vehicules/', include('apps.vehicules.api_urls')),
        path('guerite/', include('apps.guerite.api_urls')),
        path('reception/', include('apps.reception.api_urls')),
        path('atelier/', include('apps.atelier.api_urls')),
    ])),

    # Swagger
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='redoc'),

    # Redirect racine
    path('', include('apps.accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

