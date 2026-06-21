"""
Vues Comptes - Connexion, déconnexion, gestion utilisateurs
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from .forms import ConnexionForm, UserCreateForm, UserEditForm, ChangePasswordForm
from .models import User, Role, LoginAttempt
from .decorators import admin_required
from apps.audit.service import log_action
from apps.audit.models import ActionType


def index(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())
    return redirect('connexion')


def connexion(request):
    if request.user.is_authenticated:
        return redirect(request.user.get_dashboard_url())

    form = ConnexionForm(request=request)
    if request.method == 'POST':
        form = ConnexionForm(request=request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            # ⬇️ Détecter la première connexion AVANT login() (last_login est None)
            is_first_login = (user.last_login is None)
            if is_first_login:
                request.session['force_change_password'] = True   # flag pour le profil

            # Connexion (Django mettra à jour last_login automatiquement)
            login(request, user)

            # Enregistrer IP
            user.last_login_ip = getattr(request, 'audit_ip', None)
            user.save(update_fields=['last_login_ip'])

            # Logs
            LoginAttempt.objects.create(
                email=user.email,
                ip_address=getattr(request, 'audit_ip', None),
                user_agent=getattr(request, 'audit_ua', ''),
                success=True,
            )
            log_action(request, ActionType.CONNEXION, 'AUTH', details={'email': user.email})
            messages.success(request, f"Bienvenue, {user.full_name} !")

            # Redirection selon première connexion
            if is_first_login:
                messages.warning(request, "Veuillez modifier votre mot de passe avant de continuer.")
                return redirect('profil')
            else:
                return redirect(user.get_dashboard_url())
        else:
            # Échec de connexion
            email = request.POST.get('email', '')
            LoginAttempt.objects.create(
                email=email,
                ip_address=getattr(request, 'audit_ip', None),
                user_agent=getattr(request, 'audit_ua', ''),
                success=False,
            )

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
    # Lire le flag de première connexion
    force_change = request.session.pop('force_change_password', False)  # le supprime après lecture

    if request.method == 'POST':
        form = ChangePasswordForm(request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password1'])
            request.user.save()
            messages.success(request, "Mot de passe modifié avec succès.")
            # Rediriger vers la page de connexion (ou dashboard) après changement
            
    else:
        form = ChangePasswordForm()

    return render(request, 'accounts/profil.html', {
        'form': form,
        'force_change_password': force_change,
    })


# ─── Admin: Gestion des utilisateurs ───────────────────────────────────────

@admin_required
def admin_dashboard(request):
    stats = {
        'total_users': User.objects.filter(is_active=True).count(),
        'users_par_role': User.objects.values('role').annotate(total=Count('id')).order_by('role'),
        'connexions_recentes': LoginAttempt.objects.filter(success=True).select_related().order_by('-timestamp')[:10],
        'echecs_recents': LoginAttempt.objects.filter(success=False).order_by('-timestamp')[:5],
    }
    from apps.vehicules.models import Vehicule, Client
    from apps.atelier.models import OrdreReparation, Atelier
    from apps.guerite.models import EnregistrementEntree, StatutEntree
    stats['total_vehicules'] = Vehicule.objects.count()
    stats['total_clients'] = Client.objects.count()
    stats['vehicules_en_cours'] = EnregistrementEntree.objects.filter(statut=StatutEntree.EN_COURS).count()
    stats['or_en_cours'] = OrdreReparation.objects.filter(statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']).count()
    stats['ateliers'] = Atelier.objects.filter(is_active=True).annotate(
        nb_or=Count('ordres_reparation', filter=Q(ordres_reparation__statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']))
    )
    return render(request, 'admin_custom/dashboard.html', stats)


@admin_required
def liste_utilisateurs(request):
    role_filter = request.GET.get('role', '')
    users = User.objects.all().order_by('role', 'nom')
    if role_filter:
        users = users.filter(role=role_filter)
    return render(request, 'admin_custom/utilisateurs/liste.html', {
        'users': users,
        'roles': Role.choices,
        'role_filter': role_filter,
    })




@admin_required
def creer_utilisateur(request):
    form = UserCreateForm()
    if request.method == 'POST':
        form = UserCreateForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            # Définir un mot de passe par défaut (ex: "Garage2026")
            user.set_password('Garage2026')
            user.save()
            log_action(request, ActionType.CREATION, 'USERS', user, {'role': user.role})
            messages.success(request, f"Utilisateur {user.full_name} créé avec succès. Mot de passe par défaut : Garage2026")
            return redirect('liste_utilisateurs')
    return render(request, 'admin_custom/utilisateurs/form.html', {'form': form, 'titre': 'Créer utilisateur'})


@admin_required
def editer_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = UserEditForm(instance=user)
    if request.method == 'POST':
        form = UserEditForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            log_action(request, ActionType.MODIFICATION, 'USERS', user)
            messages.success(request, f"Utilisateur {user.full_name} mis à jour.")
            return redirect('liste_utilisateurs')
    return render(request, 'admin_custom/utilisateurs/form.html', {
        'form': form, 'titre': 'Modifier utilisateur', 'user_edit': user
    })


@admin_required
def reset_password_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        new_password = request.POST.get('new_password', 'Garage2026')
        user.set_password(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        user.save()
        messages.success(request, f"Mot de passe réinitialisé pour {user.full_name}.")
    return redirect('liste_utilisateurs')


@admin_required
def toggle_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    etat = "activé" if user.is_active else "désactivé"
    messages.success(request, f"Compte {user.full_name} {etat}.")
    return redirect('liste_utilisateurs')


@admin_required
def audit_logs_view(request):
    from apps.audit.models import AuditLog
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:500]
    return render(request, 'admin_custom/audit_logs.html', {'logs': logs})


# ─── Changement de langue ────────────────────────────────────────────────

def changer_langue(request):
    """Change la langue via cookie Django i18n."""
    from django.utils import translation
    from django.http import HttpResponseRedirect
    lang = request.POST.get('language') or request.GET.get('language', 'fr')
    if lang not in ('fr', 'en'):
        lang = 'fr'
    translation.activate(lang)
    response = HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
    response.set_cookie('django_language', lang, max_age=365 * 24 * 3600)
    request.session['django_language'] = lang
    return response


# ─── Changement de thème ─────────────────────────────────────────────────

def changer_theme(request):
    """Bascule dark / light mode via session."""
    from django.http import JsonResponse, HttpResponseRedirect
    current = request.session.get('theme', 'light')
    new_theme = 'dark' if current == 'light' else 'light'
    request.session['theme'] = new_theme
    # Répondre JSON si appel AJAX, sinon rediriger
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'theme': new_theme})
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
