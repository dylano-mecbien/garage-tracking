"""
Settings PRODUCTION — Garage Suivi
Hérite de base.py et surcharge les paramètres sensibles.
"""
from .base import *
from decouple import config, Csv

# ─── Sécurité de base ──────────────────────────────────────────────────────
DEBUG = False

SECRET_KEY = config('SECRET_KEY')  # OBLIGATOIRE — pas de valeur par défaut en prod

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())
# Exemple .env : ALLOWED_HOSTS=garage.votredomaine.com,www.garage.votredomaine.com

CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', cast=Csv(), default='')
# Exemple .env : CSRF_TRUSTED_ORIGINS=https://garage.votredomaine.com

# ─── HTTPS / SSL ────────────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SECURE_HSTS_SECONDS = 31536000  # 1 an
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# ─── Base de données ────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,  # connexions persistantes
        'OPTIONS': {
            'connect_timeout': 10,
        },
    }
}

# ─── Static / Media ──────────────────────────────────────────────────────────

STATIC_ROOT = '/app/staticfiles'
MEDIA_ROOT = '/app/media'

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─── Email réel (alertes erreurs, notifications) ────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

# Notifier les admins en cas d'erreur 500
ADMINS = [('Admin Garage', config('ADMIN_EMAIL', default=''))]
SERVER_EMAIL = config('DEFAULT_FROM_EMAIL', default='no-reply@garage.cm')

# ─── Logging production ──────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/app/logs/django.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 Mo
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file', 'mail_admins'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}


# ─── Sentry (optionnel mais recommandé) ──────────────────────────────────────
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.2,
        send_default_pii=False,
        environment='production',
    )

# ─── Cache / Sessions via Redis (déjà dans base.py mais on confirme prod) ───
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_COOKIE_AGE = 28800  # 8h

# ─── CORS strict en prod ─────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = config('CORS_ORIGINS', cast=Csv(), default='')
CORS_ALLOW_ALL_ORIGINS = False

