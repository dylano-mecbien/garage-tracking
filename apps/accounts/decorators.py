"""
Décorateurs et permissions par rôle
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import Role


def role_required(*roles):
    """Décorateur : restreint l'accès à certains rôles."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(request, "Accès non autorisé pour votre rôle.")
                return redirect(request.user.get_dashboard_url())
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def admin_required(view_func):
    return role_required(Role.ADMIN)(view_func)


def guerite_required(view_func):
    return role_required(Role.GUERITE, Role.ADMIN, Role.RECEPTIONNISTE, Role.SUPER_RECEPTIONNISTE)(view_func)


def receptionniste_required(view_func):
    return role_required(Role.RECEPTIONNISTE, Role.ADMIN, Role.SUPER_RECEPTIONNISTE)(view_func)


def resp_atelier_required(view_func):
    return role_required(Role.RESP_ATELIER, Role.ADMIN)(view_func)


def technicien_required(view_func):
    return role_required(Role.TECHNICIEN, Role.RESP_ATELIER, Role.ADMIN)(view_func)


def atelier_staff_required(view_func):
    return role_required(Role.TECHNICIEN, Role.RESP_ATELIER, Role.ADMIN)(view_func)
