"""
Force le changement de mot de passe tant que user.pass_default est True.

À ajouter dans settings.MIDDLEWARE, APRÈS AuthenticationMiddleware :
    'apps.accounts.middleware.ForcePasswordChangeMiddleware',
"""
from django.shortcuts import redirect
from django.urls import reverse

# Préfixes toujours accessibles (fichiers statiques, médias…)
CHEMINS_LIBRES = ('/static/', '/media/')






class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ✅ Vérification défensive
        user = getattr(request, 'user', None)

        if user and user.is_authenticated and getattr(user, 'pass_default', False):
            autorises = {
                reverse('profil'),
                reverse('deconnexion'),
                reverse('changer_langue'),
            }
            if request.path not in autorises and not request.path.startswith(CHEMINS_LIBRES):
                return redirect('profil')

        return self.get_response(request)