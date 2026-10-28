"""
Authentification, profil, langue, thème.
"""
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render

from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.reception.views._utils import save_signature_from_dataurl

from ..forms import ChangePasswordForm, ConnexionForm
from ..models import LoginAttempt
from ._utils import safe_referer


def _log_tentative(request, email, success):
    LoginAttempt.objects.create(
        email=email,
        ip_address=getattr(request, 'audit_ip', None),
        user_agent=getattr(request, 'audit_ua', ''),
        success=success,
    )


def index(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())
    return redirect('connexion')


def connexion(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())

    form = ConnexionForm(request=request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            user.last_login_ip = getattr(request, 'audit_ip', None)
            user.save(update_fields=['last_login_ip'])

            _log_tentative(request, user.email, True)
            log_action(request, ActionType.CONNEXION, 'AUTH', details={'email': user.email})
            messages.success(request, f"Bienvenue, {user.full_name} !")

            # Le middleware ForcePasswordChange gère aussi ce cas,
            # mais on redirige directement pour éviter un saut inutile.
            if user.pass_default:
                messages.warning(request, "Veuillez modifier votre mot de passe avant de continuer.")
                return redirect('profil')
            return redirect(user.get_dashboard_url())

        _log_tentative(request, request.POST.get('email', ''), False)

    return render(request, 'accounts/connexion.html', {'form': form})


@login_required
def deconnexion(request):
    log_action(request, ActionType.DECONNEXION, 'AUTH')
    logout(request)
    messages.info(request, "Vous avez été déconnecté.")
    return redirect('connexion')


@login_required
def dashboard_redirect(request):
    return redirect(request.user.get_dashboard_url())


@login_required
def profil(request):
    form = ChangePasswordForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = request.user
        user.set_password(form.cleaned_data['new_password1'])
        user.pass_default = False
        user.save()
        update_session_auth_hash(request, user)  # reste connecté après le changement
        log_action(request, ActionType.MODIFICATION, 'AUTH', user, {'action': 'changement_mdp'})
        messages.success(request, "Mot de passe modifié avec succès.")
        return redirect(user.get_dashboard_url())

    return render(request, 'accounts/profil.html', {
        'form': form,
        # Basé sur la BDD, plus sur la session : impossible à contourner en rechargeant
        'force_change_password': request.user.pass_default,
    })


@login_required
def profil_signature(request):
    if request.method != 'POST':
        return redirect('profil')

    data = request.POST.get('signature', '').strip()
    if not data or not data.startswith('data:image'):
        messages.error(request, "Signature invalide.")
        return redirect('profil')

    user = request.user
    if not save_signature_from_dataurl(user, data, 'signature'):
        messages.error(request, "Erreur lors de l'enregistrement de la signature.")
        return redirect('profil')

    user.save(update_fields=['signature'])  # si save_signature ne save pas
    log_action(request, ActionType.MODIFICATION, 'COMPTE', user, {'champ': 'signature'})
    messages.success(request, "Signature enregistrée.")
    return redirect('profil')



def changer_langue(request):
    """Change la langue (cookie + session)."""
    lang = request.POST.get('language') or request.GET.get('language', 'fr')
    if lang not in ('fr', 'en'):
        lang = 'fr'
    response = HttpResponseRedirect(safe_referer(request))
    response.set_cookie('django_language', lang, max_age=365 * 24 * 3600)
    request.session['django_language'] = lang
    return response


def changer_theme(request):
    """Bascule dark / light mode via session."""
    nouveau = 'dark' if request.session.get('theme', 'light') == 'light' else 'light'
    request.session['theme'] = nouveau
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'theme': nouveau})
    return HttpResponseRedirect(safe_referer(request))
