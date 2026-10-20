"""
Dashboard admin + gestion des utilisateurs + logs d'audit.
"""
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.atelier.models import Atelier, OrdreReparation
from apps.audit.models import ActionType, AuditLog
from apps.audit.service import log_action
from apps.guerite.models import EnregistrementEntree, StatutVehicule
from apps.reception.views import paginate_queryset
from apps.vehicules.models import Client, Vehicule

from ..decorators import admin_required
from ..forms import UserCreateForm, UserEditForm
from ..models import LoginAttempt, Role, User
from ._utils import DEFAULT_PASSWORD, STATUTS_OR_ACTIFS


@admin_required
def admin_dashboard(request):
    today = timezone.localdate()
 
    mouvements = EnregistrementEntree.objects.aggregate(
        nb_entrees_today=Count('id', filter=Q(date_entree__date=today)),
        nb_sorties_today=Count('id', filter=Q(date_sortie__date=today)),
        vehicules_en_cours=Count('id', filter=Q(date_sortie__isnull=True)),
    )

    return render(request, 'admin_custom/dashboard.html', {
        'today': today,
        'total_users': User.objects.filter(is_active=True).count(),
        'users_par_role': User.objects.values('role').annotate(total=Count('id')).order_by('role'),
        'connexions_recentes': LoginAttempt.objects.filter(success=True).order_by('-timestamp')[:10],
        'echecs_recents': LoginAttempt.objects.filter(success=False).order_by('-timestamp')[:5],
        **mouvements,
        'total_vehicules': Vehicule.objects.count(),
        'total_clients': Client.objects.count(),
        'or_en_cours': OrdreReparation.objects.filter(statut__in=STATUTS_OR_ACTIFS).count(),
        'ateliers': Atelier.objects.filter(is_active=True).annotate(
            nb_or=Count('ordres_reparation',
                        filter=Q(ordres_reparation__statut__in=STATUTS_OR_ACTIFS))
        ),
    })

@admin_required
def liste_utilisateurs(request):
    role_filter = request.GET.get('role', '').strip()
    statut_filter = request.GET.get('statut', '').strip()
    q = request.GET.get('q', '').strip()

    users = User.objects.select_related('atelier').order_by('role', 'nom')
    if role_filter:
        users = users.filter(role=role_filter)
    if statut_filter in ('actif', 'inactif'):
        users = users.filter(is_active=(statut_filter == 'actif'))
    if q:
        users = users.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(email__icontains=q)
            | Q(matricule__icontains=q) | Q(telephone__icontains=q)
        )

    return render(request, 'admin_custom/utilisateurs/liste.html', {
        'users': users,
        'roles': Role.choices,
        'role_filter': role_filter,
        'statut_filter': statut_filter,
        'q': q,
    })


@admin_required
def creer_utilisateur(request):
    form = UserCreateForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.set_password(DEFAULT_PASSWORD)
        user.pass_default = True  # explicite : changement forcé à la 1re connexion
        user.save()
        log_action(request, ActionType.CREATION, 'USERS', user, {'role': user.role})
        messages.success(request, f"Utilisateur {user.full_name} créé. "
                                  f"Mot de passe par défaut : {DEFAULT_PASSWORD}")
        return redirect('liste_utilisateurs')
    return render(request, 'admin_custom/utilisateurs/form.html',
                  {'form': form, 'titre': 'Créer utilisateur'})


@admin_required
def editer_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    form = UserEditForm(request.POST or None, request.FILES or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        log_action(request, ActionType.MODIFICATION, 'USERS', user)
        messages.success(request, f"Utilisateur {user.full_name} mis à jour.")
        return redirect('liste_utilisateurs')
    return render(request, 'admin_custom/utilisateurs/form.html', {
        'form': form, 'titre': 'Modifier utilisateur', 'user_edit': user,
    })


@admin_required
@require_POST
def reset_password_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.set_password(request.POST.get('new_password') or DEFAULT_PASSWORD)
    user.failed_login_count = 0
    user.locked_until = None
    user.pass_default = True  # CORRIGÉ : l'utilisateur doit changer ce mot de passe
    user.save()
    log_action(request, ActionType.MODIFICATION, 'USERS', user, {'action': 'reset_mdp'})
    messages.success(request, f"Mot de passe réinitialisé pour {user.full_name}.")
    return redirect('liste_utilisateurs')


@admin_required
@require_POST
def toggle_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect('detail_utilisateur', user_id=user_id)

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    log_action(request, ActionType.MODIFICATION, 'USERS', user, {'is_active': user.is_active})
    messages.success(request, f"Compte {user.full_name} {'activé' if user.is_active else 'désactivé'}.")
    return redirect('detail_utilisateur', user_id=user_id)


@admin_required
def audit_logs_view(request):
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')
    page_obj = paginate_queryset(request, logs, per_page=50)
    return render(request, 'admin_custom/audit_logs.html', {'logs': page_obj, 'page_obj': page_obj})
