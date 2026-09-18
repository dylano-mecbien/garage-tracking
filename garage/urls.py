from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


# ─────────────────────────────────────────────
# URLs principales
# ─────────────────────────────────────────────
urlpatterns = [
    # Admin Django
    path("django-admin/", admin.site.urls),

    # Auth & Dashboard
    path("auth/",      include("apps.accounts.urls")),
    path("dashboard/", include("apps.accounts.urls_dashboard")),

    # Modules métier
    path('admin/', include('apps.accounts.urls_dashboard')),

    path("guerite/",       include("apps.guerite.urls")),
    path("reception/",     include("apps.reception.urls")),
    path("atelier/",       include("apps.atelier.urls")),
    path("vehicules/",     include("apps.vehicules.urls")),
    path("documents/",     include("apps.documents.urls")),
    path("audit/",         include("apps.audit.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path('admin-garage/notifications/', include('apps.notifications.urls')),
    # API REST

     path('api/v1/', include([
        path('auth/', include('apps.accounts.api_urls')),
        path('vehicules/', include('apps.vehicules.api_urls')),
        path('guerite/', include('apps.guerite.api_urls')),
        path('reception/', include('apps.reception.api_urls')),
        path('atelier/', include('apps.atelier.api_urls')),
    ])),

    # Documentation API (drf-spectacular)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),   name="redoc"),

    
    # Racine (à garder en dernier)
    path("", include("apps.accounts.urls")),
]


# ─────────────────────────────────────────────
# Médias & statiques (dev uniquement)

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
