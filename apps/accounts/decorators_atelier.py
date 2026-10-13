"""Décorateurs du module atelier (à fusionner dans apps/accounts/decorators.py si tu préfères)."""
from functools import wraps
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login

from django.shortcuts import redirect
from apps.atelier.roles import ROLE_ADMIN, ROLE_RECEPTION, ROLE_RESP, ROLE_TECH


def _role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                messages.error(request, "Accès non autorisé pour votre rôle.")
                return redirect('index')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator

def lecture_fiches_required(view):
    """Lecture des fiches : réceptionniste, responsable d'atelier, technicien, admin."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if request.user.role not in (ROLE_RECEPTION, ROLE_RESP, ROLE_TECH, ROLE_ADMIN):
            messages.error(request, "Accès non autorisé pour votre rôle.")
            return redirect('/')
        return view(request, *args, **kwargs)
    return wrapper

resp_atelier_required   = _role_required(ROLE_RESP, ROLE_ADMIN)
technicien_required     = _role_required(ROLE_TECH, ROLE_RESP, ROLE_ADMIN)   # un responsable peut avoir des tâches
fiches_lecture_required = lecture_fiches_required
