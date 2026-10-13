"""Décorateurs propres à l'app inventaire (aucune dépendance à tes decorators.py).
⚠️ Si les valeurs de User.role diffèrent, change-les ici."""
from functools import wraps
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

ROLE_ADMIN = 'ADMIN'
ROLE_GUERITE = 'GUERITE'


def _role_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **k):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                messages.error(request, "Accès non autorisé pour votre rôle.")
                return redirect('/')
            return view(request, *a, **k)
        return wrapper
    return deco


guerite_required = _role_required(ROLE_GUERITE, ROLE_ADMIN)
admin_only = _role_required(ROLE_ADMIN)
