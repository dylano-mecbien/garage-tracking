"""
Vues Comptes - Connexion, déconnexion, gestion utilisateurs
"""
from datetime import date, timedelta
from django.core.paginator import Paginator
import os
from django.core.files.storage import default_storage
from django.http import JsonResponse, request
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.core.files.base import ContentFile
import json
from apps.accounts.choices import StatutReception, StatutTache
from apps.accounts.views_user_stats import format_duree
from apps.atelier.views import _entree_from_or
from apps.atelier.views import enrich_taches_duree
from apps.guerite.forms import ClientForm, VehiculeForm
from apps.guerite.views import PHOTO_FIELDS
from apps.notifications.hook import notifier_bon_sortie_cree
from apps.reception.forms import BonSortieForm
from apps.reception.models import Reception
from apps.reception.views import _gen_qr, get_entrees_presentes_filtrees, get_filtered_entrees, paginate_queryset
from .forms import ConnexionForm, UserCreateForm, UserEditForm, ChangePasswordForm
from .models import User, Role, LoginAttempt
from .decorators import admin_required, receptionniste_required
from apps.audit.service import log_action
from apps.audit.models import ActionType
from apps.vehicules.models import Marque, Vehicule, Client
from apps.atelier.models import OrdreReparation, Atelier
from apps.guerite.models import BonSortie, EnregistrementEntree, MotifEntree, StatutVehicule, TypeBon
from django.core.serializers.json import DjangoJSONEncoder

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
            
            # ⬇️ Détecter la première connexion AVANT login() 
            is_first_login = (user.pass_default)
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

            request.user.pass_default = False


            request.user.save()
            messages.success(request, "Mot de passe modifié avec succès.")
            # Rediriger vers la page de connexion (ou dashboard) après changement
            return redirect('connexion')
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
        'today' : timezone.now().date(),
        'total_users': User.objects.filter(is_active=True).count(),
        'users_par_role': User.objects.values('role').annotate(total=Count('id')).order_by('role'),
        'connexions_recentes': LoginAttempt.objects.filter(success=True).select_related().order_by('-timestamp')[:10],
        'echecs_recents': LoginAttempt.objects.filter(success=False).order_by('-timestamp')[:5],
    }

    aujourd_hui = timezone.now().date()
    entrees_today = EnregistrementEntree.objects.filter(date_entree__date=aujourd_hui)
    sorties_today = EnregistrementEntree.objects.filter(
                  date_sortie__date=aujourd_hui
              )
    stats['nb_entrees_today'] = entrees_today.count()
    stats['nb_sorties_today'] = sorties_today.count()
    stats['total_vehicules'] = Vehicule.objects.count()
    stats['total_clients'] = Client.objects.count()
    stats['vehicules_en_cours'] = EnregistrementEntree.objects.filter(statut=StatutVehicule.EN_COURS).count()
    stats['or_en_cours'] = OrdreReparation.objects.filter(statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']).count()
    stats['ateliers'] = Atelier.objects.filter(is_active=True).annotate(
        nb_or=Count('ordres_reparation', filter=Q(ordres_reparation__statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']))
    )
    return render(request, 'admin_custom/dashboard.html', stats)


@admin_required
def liste_utilisateurs(request):
    role_filter = request.GET.get('role', '').strip()
    statut_filter = request.GET.get('statut', '').strip()
    q = request.GET.get('q', '').strip()

    users = User.objects.select_related('atelier').order_by('role', 'nom')

    if role_filter:
        users = users.filter(role=role_filter)

    if statut_filter == 'actif':
        users = users.filter(is_active=True)
    elif statut_filter == 'inactif':
        users = users.filter(is_active=False)

    if q:
        users = users.filter(
            Q(nom__icontains=q)
            | Q(prenom__icontains=q)
            | Q(email__icontains=q)
            | Q(matricule__icontains=q)
            | Q(telephone__icontains=q)
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
    form = UserCreateForm()
    if request.method == 'POST':
        form = UserCreateForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            # Définir un mot de passe par défaut (ex: "garage2026")
            user.set_password('garage2026')
            
            user.save()
            log_action(request, ActionType.CREATION, 'USERS', user, {'role': user.role})
            messages.success(request, f"Utilisateur {user.full_name} créé avec succès. Mot de passe par défaut : garage2026")
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
        new_password = request.POST.get('new_password', 'garage2026')
        user.set_password(new_password)
        user.failed_login_count = 0
        user.locked_until = None
        
        user.pass_default = False
        user.save()
        messages.success(request, f"Mot de passe réinitialisé pour {user.full_name}.")
    return redirect('liste_utilisateurs')


@admin_required
def toggle_utilisateur(request, user_id):
    user = get_object_or_404(User, id=user_id)
    id_user=  user_id
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    etat = "activé" if user.is_active else "désactivé"
    messages.success(request, f"Compte {user.full_name} {etat}.")
    return redirect('detail_utilisateur', user_id=id_user)


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


# ─── LISTE BONS DE SORTIE ────────────────────────────────────────────────────
@admin_required
def liste_bons_sortie(request):
  
 
    qs = BonSortie.objects.select_related(
        'vehicule', 'vehicule__client', 'cree_par', 'valide_par'
    ).order_by('-created_at')
 
    # ── Filtres ──
    q       = request.GET.get('q', '').strip()
    type_   = request.GET.get('type', '')
    etat    = request.GET.get('etat', '')
    periode = request.GET.get('periode', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin   = request.GET.get('date_fin', '')
    sort    = request.GET.get('sort', 'date')
 
    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(nom_demandeur__icontains=q) |
            Q(vehicule__immatriculation__icontains=q) |
            Q(Origine_demande__icontains=q) |
            Q(observations__icontains=q)
        )
    if type_:
        qs = qs.filter(types=type_)
    if etat:
        qs = qs.filter(etats=etat)
 
    now = timezone.now()
    if periode == 'today':
        qs = qs.filter(created_at__date=now.date())
    elif periode == 'week':
        qs = qs.filter(created_at__gte=now - timedelta(days=7))
    elif periode == 'month':
        qs = qs.filter(created_at__year=now.year, created_at__month=now.month)
    elif periode == 'custom':
        if date_debut:
            qs = qs.filter(created_at__date__gte=date_debut)
        if date_fin:
            qs = qs.filter(created_at__date__lte=date_fin)
 
    if sort == 'numero':
        qs = qs.order_by('numero')
 
    # ── Stats ──
    all_bons = BonSortie.objects.all()
    stats = {
        'total':      all_bons.count(),
        'valides':    all_bons.filter(etats='VALIDER').count(),
        'en_attente': all_bons.exclude(etats='VALIDER').count(),
        'vehicules':  all_bons.filter(types='VEHICULE').count(),
        'divers':     all_bons.filter(types='DIVERS').count(),
    }
 
    filters = {
        'q': q, 'type': type_, 'etat': etat,
        'periode': periode, 'date_debut': date_debut,
        'date_fin': date_fin, 'sort': sort,
    }
    page_obj = paginate_queryset(request, qs, per_page=25)

    return render(request, 'admin_custom/bons/bons_sortie_liste_admin.html', {
        'bons':    page_obj,
        'page_obj': page_obj,
        'stats':   stats,
        'filters': filters,
    })




@admin_required
def liste_or(request):
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()
    qs = (
        OrdreReparation.objects
  
        .select_related('vehicule', 'vehicule__client')
        .prefetch_related('taches')
    )
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(numero__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )
    ors = list(qs.order_by('statut', '-urgence', 'date_creation'))
    return render(request, 'admin_custom/mouvements/liste_or.html', {
         'ors': ors, 'statut': statut, 'q': q,
    })



@admin_required
def detail_or_admin(request, or_id):
    or_obj = get_object_or_404(
        OrdreReparation.objects
        .select_related(
            'vehicule',
            'vehicule__client',
            'reception',
            'created_by',
        )
        .prefetch_related(
            'ateliers',
            'taches__atelier',
            'taches__techniciens',
            'taches__valide_par',
            'taches__created_by',
            'taches__comptes_rendus',
            'taches__comptes_rendus__technicien',
        ),
        id=or_id,
    )

    entree = _entree_from_or(or_obj)
    fiche_controle  = getattr(entree, 'fiche_controle',  None) if entree else None
    fiche_technique = getattr(entree, 'fiche_technique', None) if entree else None

    # ── Toutes les tâches (tous ateliers) ──
    taches = list(
        or_obj.taches
        .select_related('atelier', 'valide_par', 'created_by')
        .prefetch_related('techniciens', 'comptes_rendus', 'comptes_rendus__technicien')
        .order_by('atelier__nom', 'created_at')
    )

    # ── Enrichissement des durées (évite les N+1) ──
    enrich_taches_duree(taches)

    nb_validees = sum(1 for t in taches if t.statut == StatutTache.VALIDEE)

    return render(request, 'admin_custom/mouvements/detail_or.html', {
        'or':              or_obj,
        'entree':          entree,
        'fiche_controle':  fiche_controle,
        'fiche_technique': fiche_technique,
        'taches':          taches,
        'nb_validees':     nb_validees,
    })


@admin_required
def creer_bon_sortie_direct(request):
    """
    Créer un bon de sortie directement depuis la guérite,
    sans réception préalable.
    """
    # Récupérer tous les véhicules présents (non sortis) pour l'autocomplétion
    vehicules_presents = EnregistrementEntree.objects.exclude(
        statut=StatutVehicule.SORTI
    ).select_related('vehicule', 'conducteur', 'vehicule__client')

    vehicles_data = []
    for entree in vehicules_presents:
        v = entree.vehicule
        vehicles_data.append({
            'id': v.id,
            'immatriculation': v.immatriculation,
            'conducteur_nom': f"{entree.conducteur.nom} {entree.conducteur.prenom}".strip() if entree.conducteur else '',
            'client_nom': v.client.nom if v.client else '',
        })

    # Gestion du POST
    if request.method == 'POST':
        vehicule_id = request.POST.get('vehicule_id')
        nom_demandeur = request.POST.get('nom_demandeur', '').strip()
        observations = request.POST.get('observations', '').strip()

        # Validation
        if not vehicule_id:
            messages.error(request, "Veuillez sélectionner un véhicule.")
            return render(request, 'admin_custom/bons/creer_bon_sortie_admin.html', {
                'vehicles_data': vehicles_data,
                'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
                'form': BonSortieForm(),
                'reception': None,
            })

        try:
            vehicule = Vehicule.objects.get(id=vehicule_id)
        except Vehicule.DoesNotExist:
            messages.error(request, "Véhicule introuvable.")
            return render(request, 'admin_custom/bons/creer_bon_sortie_admin.html', {
                'vehicles_data': vehicles_data,
                'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
                'form': BonSortieForm(),
                'reception': None,
            })

        # BUG CORRIGÉ : `rec` n'existait pas dans cette vue (copié de creer_bon_sortie).
        # On récupère l'enregistrement d'entrée actif lié à ce véhicule, s'il existe,
        # pour pouvoir mettre à jour son statut.
        rec = EnregistrementEntree.objects.filter(
            vehicule=vehicule
        ).exclude(
            statut=StatutVehicule.SORTI
        ).order_by('-id').first()

        

        # Création du bon de sortie
        bon = BonSortie.objects.create(
            types='VEHICULE',
            vehicule=vehicule,
            nom_demandeur=nom_demandeur,
            observations=observations,
            cree_par=request.user,
            # Si d'autres champs existent (Origine_demande, etc.), les ajouter ici
        )

        if rec is not None:
            rec.bon_sortie = bon
            rec.save(update_fields=['bon_sortie'])

        # Cohérence avec creer_bon_sortie : génération du QR code
        _gen_qr(bon)

        log_action(request, ActionType.CREATION, 'GUERITE', bon)
        messages.success(request, f"Bon de sortie {bon.numero} créé.")
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    # GET : afficher le formulaire
    form = BonSortieForm()
    return render(request, 'admin_custom/bons/creer_bon_sortie_admin.html', {
        'vehicles_data': vehicles_data,
        'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
        'form': form,
        'reception': None,  # pas de réception pré-sélectionnée
    })

@admin_required
def detail_entree(request, entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree'),
        id=entree_id
    )
    return render(request, 'admin_custom/mouvements/Entre_detail.html', {'entree': entree})

 
from django.db import transaction

# ─── BON DE SORTIE ────────────────────────────────────────────────────────────
@admin_required
def creer_bon_sortie(request, rec_id):
    Enreg = get_object_or_404(EnregistrementEntree, id=rec_id)
    rapport = getattr(Enreg, 'rapport', None)

    # Véhicules présents pour l'autocomplétion
    vehicules_presents = (
        EnregistrementEntree.objects
        .exclude(statut=StatutVehicule.SORTI)
        .select_related('vehicule', 'vehicule__client', 'conducteur')
    )

    vehicles_data = []
    for entree in vehicules_presents:
        v = entree.vehicule
        vehicles_data.append({
            'id': v.id,
            'immatriculation': v.immatriculation,
            'conducteur_nom': (
                f"{entree.conducteur.nom} {entree.conducteur.prenom}".strip()
                if entree.conducteur else ''
            ),
            'client_nom': v.client.nom if v.client else '',
        })

    if request.method == 'POST':
        form = BonSortieForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # 1) Créer le bon
                bon = form.save(commit=False)
                bon.cree_par = request.user
                bon.types = TypeBon.VEHICULE
                if Enreg.vehicule:
                    bon.vehicule = Enreg.vehicule
                bon.save() 

                # 2) Lier l'entrée au bon
                #    ⚠️ On ne touche PAS au statut ici : SORTI sera appliqué par la guérite.
                Enreg.bon_sortie = bon
                Enreg.save(update_fields=['bon_sortie'])

                # 3) QR code + audit
                _gen_qr(bon)
                log_action(request, ActionType.CREATION, 'RECEPTION', bon)

            messages.success(request, f"Bon de sortie {bon.numero} créé.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)
    else:
        form = BonSortieForm()

    return render(request, 'admin_custom/bons/creer_bon_sortie.html', {
        'form': form,
        'reception': Enreg,
        'vehicles_data': vehicles_data,
        'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
        'sortie_directe': bool(rapport and rapport.decision == 'SORTIE_DIRECTE'),
    })


@admin_required
def creer_bon_sortie_divers(request):
    """Page dédiée à la création d'un bon de sortie divers (version ultra simplifiée)."""
 
    employes = User.objects.filter(is_active=True).order_by('role', 'nom') 


    if request.method == 'POST':
        nom_demandeur = request.POST.get('nom_demandeur', '').strip()
        observations  = request.POST.get('observations', '').strip()

        if not nom_demandeur:
            messages.error(request, "Veuillez sélectionner un demandeur.")
        elif not observations:
            messages.error(request, "Veuillez saisir au moins une ligne (article) dans les observations.")
        else:
            bon = BonSortie.objects.create(
                types           = 'DIVERS',
                nom_demandeur   = nom_demandeur,
                Origine_demande = 'DIVERS',   # valeur par défaut
                observations    = observations,
                cree_par        = request.user,
            )
            
            est_super_ou_admin = request.user.role in (Role.SUPER_RECEPTIONNISTE, Role.ADMIN)
            if not est_super_ou_admin:
                notifier_bon_sortie_cree(bon)
            log_action(request, ActionType.CREATION, 'GUERITE', bon, {'type': 'DIVERS'})
            messages.success(request, f"Bon de sortie {bon.numero} créé avec succès.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    return render(request, 'admin_custom/bons/creer_divers_admin.html') 



@admin_required 
def historique_entrees(request):
    qs = get_filtered_entrees(request)
    page_obj = paginate_queryset(request, qs, per_page=25)
    return render(request, 'admin_custom/mouvements/historique_admin.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'statuts': StatutVehicule.choices,
        'motifs': MotifEntree.choices,
    })




@admin_required
def liste_receptions(request):
    qs = (
        Reception.objects
        .select_related(
            'vehicule', 'vehicule__client', 'receptionniste',
        )
        # Pour OR : OneToOne (select_related)
        .select_related('ordre_reparation')
        # Pour ateliers : M2M (prefetch_related, via OR)
        .prefetch_related('ordre_reparation__ateliers')
        .order_by('-created_at')
    )

    statut = request.GET.get('statut', '')
    q      = request.GET.get('q', '')

    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q) |
            Q(numero__icontains=q) |
            Q(vehicule__client__nom__icontains=q)
        )

    page_obj = paginate_queryset(request, qs, per_page=25)

    return render(request, 'admin_custom/mouvements/liste_receptions_admin.html', {
        'receptions':    page_obj,
        'page_obj':      page_obj,
        'statuts':       StatutReception.choices,
        'statut_filter': statut,
    })



@admin_required
def detail_reception(request, rec_id):
    rec = get_object_or_404(
        Reception.objects.select_related(
            'vehicule', 'vehicule__client', 'entree', 'receptionniste'
        ).prefetch_related('transferts__atelier'),
        id=rec_id
    )

    or_list = (
    OrdreReparation.objects
    .filter(reception=rec)
    .prefetch_related('ateliers', 'taches')   # M2M en prefetch
    .order_by('-date_creation')
)
    entree = getattr(rec, 'entree', None)
    fiche_controle = getattr(entree, 'fiche_controle', None) if entree else None

    technicien_a_signe = bool(
            fiche_controle
            and fiche_controle.signature_technicien
            and str(fiche_controle.signature_technicien).strip()
        )
    client_a_signe = bool(
            fiche_controle and fiche_controle.signature_client_avant
        )
    bon_sortie   = BonSortie.objects.filter(vehicule=rec.vehicule, reception=rec).first()
    
    return render(request, 'admin_custom/mouvements/detail_rec_admin.html', {
        'rec': rec, 
        'or_list': or_list,
          'bon_sortie': bon_sortie,
        'fiche_technique': getattr(entree, 'fiche_technique', None) if entree else None,
        'a_fiche_controle': technicien_a_signe, 
        'client_a_signe': client_a_signe,
        'fiche_controle': fiche_controle, 
    })

def liste_vehicules_presents(request):
    qs = get_entrees_presentes_filtrees(request)
    page_obj = paginate_queryset(request, qs, per_page=25)

    return render(request, 'admin_custom/mouvements/vehicules_presents_admin.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'motifs': MotifEntree.choices,  # adapte
    })


@admin_required
def admin_creer_vehicule(request):
    """Version améliorée avec type propriétaire et photos multiples."""
    client_id = request.GET.get('client_id')
    client_preselect = None
    if client_id:
        try:
            c = Client.objects.get(id=client_id)
            client_preselect = str(c)
        except Client.DoesNotExist:
            client_id = None
 
    form = VehiculeForm(initial={'client': client_id} if client_id else {})
 
    if request.method == 'POST':
        form = VehiculeForm(request.POST, request.FILES)
        # Validation manuelle du client (sélectionné via AJAX)
        client_id_post = request.POST.get('client')
        if not client_id_post:
            form.add_error('client', 'Veuillez sélectionner un propriétaire.')
 
        if form.is_valid():
            vehicule = form.save(commit=False)
            vehicule.created_by = request.user

            # Récupération ou création de la marque
            marque_nom = form.cleaned_data['marque'].strip()
            marque, _ = Marque.objects.get_or_create(nom=marque_nom)
            
            # Récupération ou création du modèle (lié à cette marque)
            modele_nom = form.cleaned_data['modele'].strip()



            # Immatriculation en majuscules 
            vehicule.immatriculation = vehicule.immatriculation.upper()
            vehicule.save()
 
        
            photos_paths = []
            for i in range(3):
                 photo_file = request.FILES.get(f'photo_{i}')
                 if photo_file:
                      ext = os.path.splitext(photo_file.name)[1]
                      immat_clean = vehicule.immatriculation.replace(' ', '').replace('-', '').upper()
                      filename = f"vehicules/photos/{immat_clean}_{i}{ext}"
                      saved_path = default_storage.save(filename, ContentFile(photo_file.read())) 
                      photos_paths.append(saved_path)

                      if photos_paths:
                         vehicule.photos = ';'.join(photos_paths)
                         vehicule.photo = photos_paths[0]
                         vehicule.save(update_fields=['photos', 'photo'])
               
            log_action(request, ActionType.CREATION, 'GUERITE', vehicule)
            messages.success(request, f"Véhicule {vehicule.immatriculation} créé.")
            return redirect(f"/admin/admin-garage/vehicule/{vehicule.id}")
        
    return render(request, 'admin_custom/vehicules/creer_vehicule.html', { 
        'form':             form,
        'client_id':        client_id,
        'client_preselect': client_preselect,
    })



@admin_required
def modifier_motif_admin(request, entree_id):
    entree = get_object_or_404(EnregistrementEntree, pk=entree_id)

    if request.method == "POST":
        motif = request.POST.get("motif")

        if motif in ["REPARATION", "VISITE" , "STATIONNEMENT", "INTERNE"]:
            entree.motif = motif
            entree.save()

            messages.success(
                request,
                f"Motif modifié : {entree.get_motif_display()}"
            )
            
    log_action(
        request,
        ActionType.MODIFICATION,
        'ADMIN',
        entree,
        {'motif': entree.motif}
    )
    return redirect("detail_entree_admin", entree_id=entree.id)

@admin_required
def admin_vehicules(request):
    from apps.vehicules.models import Vehicule
 
    q           = request.GET.get('q', '').strip()
    carburant   = request.GET.get('carburant', '')
    type_client = request.GET.get('type_client', '')
    assurance   = request.GET.get('assurance', '')
    presence    = request.GET.get('presence', 'tous')
 
    qs = Vehicule.objects.select_related('client').filter(is_active=True)
 
    if q:
        qs = qs.filter(
            Q(immatriculation__icontains=q) |
            Q(marque__icontains=q) |
            Q(modele__icontains=q) |
            Q(numero_chassis__icontains=q) |
            Q(client__nom__icontains=q) |
            Q(client__prenom__icontains=q) |
            Q(client__telephone__icontains=q)
        )
    if carburant:
        qs = qs.filter(type_carburant=carburant)
    if type_client:
        qs = qs.filter(client__type_client=type_client)
    if assurance == 'expiree':
        qs = qs.filter(expiry_assurance__lt=date.today())
    elif assurance == 'valide':
        qs = qs.filter(expiry_assurance__gte=date.today())
 
    # Filtre présence avant list()
    if presence == 'presents':
        # véhicules avec au moins une entrée non SORTI
        qs = qs.filter(entrees__statut__in=['EN_COURS']).distinct()
    elif presence == 'atelier':
        qs = qs.filter(
            ordres_reparation__statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']
        ).distinct()
    elif presence == 'libres':

        qs = qs.exclude(
            entrees__statut__in=['EN_COURS']
        ).distinct()
 
    vehicules = list(qs[:100])
 
    # Stats globales (sur tous, pas filtrés)
    all_v = Vehicule.objects.filter(is_active=True)
    nb_presents = all_v.filter(entrees__statut__in=['EN_COURS']).distinct().count()
    nb_atelier  = all_v.filter(
        ordres_reparation__statut__in=['OUVERT','EN_COURS','REOUVERT']
    ).distinct().count()
 
    stats = {
        'total':       all_v.count(),
        'presents':    nb_presents,
        'en_atelier':  nb_atelier,
        'libres':      all_v.count() - nb_presents,
        'entreprises': all_v.filter(client__type_client='ENTREPRISE').count(),
    }
 
    return render(request, 'admin_custom/vehicules/liste.html', {
        'vehicules':       vehicules,
        'nb_presents':     nb_presents,
        'stats':           stats,
        'filtre_presence': presence,
        'filters': {
            'q': q, 'carburant': carburant,
            'type_client': type_client, 'assurance': assurance,
        },
        # Choix pour le template modifier
        'carburants': [
            ('NON_DEFINI','Non défini'),('ESSENCE','Essence'),
            ('DIESEL','Diesel'),('ELECTRIQUE','Électrique'),
            ('HYBRIDE','Hybride'),('GPL','GPL'),
        ],
    })
 
 
@admin_required
def admin_mouvements_vehicule(request, vehicule_id):
    """AJAX — mouvements d'un véhicule."""
    v = get_object_or_404(Vehicule, id=vehicule_id)
 
    # statut_presence via le modèle
    statut = v.statut_presence
 
    entrees = EnregistrementEntree.objects.filter(
        vehicule=v
    ).order_by('-date_entree')[:20]
 
    mouvements = []
    for e in entrees:
        try:
            rec = e.reception.numero
        except Exception:
            rec = None
        mouvements.append({
            'numero':      e.numero,
            'motif':       e.get_motif_display(),
            'statut':      e.statut,
            'date_entree': e.date_entree.strftime('%d/%m/%Y %H:%M'),
            'date_sortie': e.date_sortie.strftime('%d/%m/%Y %H:%M') if e.date_sortie else None,
            'duree':       None,
            'reception':   rec,
        })
 
    total       = entrees.count()
    reparations = EnregistrementEntree.objects.filter(
        vehicule=v, motif='REPARATION'
    ).count()
 
    return JsonResponse({
        'mouvements': mouvements,
        'statut_presence': statut,
        'stats': {'total_passages': total, 'reparations': reparations},
    })

@admin_required
def admin_modifier_vehicule(request, vehicule_id):
    v = get_object_or_404(Vehicule, id=vehicule_id)

    carburants = [
        ('NON_DEFINI', 'Non défini'),
        ('ESSENCE', 'Essence'),
        ('DIESEL', 'Diesel'),
        ('ELECTRIQUE', 'Électrique'),
        ('HYBRIDE', 'Hybride'),
        ('GPL', 'GPL'),
    ]
    transmissions = [
        ('NON_DEFINI', 'Non défini'),
        ('MANUELLE', 'Manuelle'),
        ('AUTOMATIQUE', 'Automatique'),
    ]

    def get_photo_urls(vehicule):
        urls = []
        if vehicule.photos:
            for path in vehicule.photos.split(';'):
                path = path.strip()
                if path:
                    try:
                        urls.append(default_storage.url(path))
                    except Exception:
                        urls.append('')
        while len(urls) < 3:
            urls.append('')
        return urls

    def render_form():
        return render(request, 'admin_custom/vehicules/modifier.html', {
            'v': v,
            'carburants': carburants,
            'transmissions': transmissions,
            'photo_urls_json': json.dumps(get_photo_urls(v)),
        })

    if request.method == 'POST':
        v.immatriculation = request.POST.get('immatriculation', v.immatriculation).upper().strip()
        v.marque = request.POST.get('marque', v.marque).strip()
        v.modele = request.POST.get('modele', v.modele).strip()

        annee_raw = request.POST.get('annee', '').strip()
        v.annee = int(annee_raw) if annee_raw else None

        v.couleur = request.POST.get('couleur', '').strip() or None
        v.type_carburant = request.POST.get('type_carburant', v.type_carburant)
        v.transmission = request.POST.get('transmission', v.transmission)

        puissance_raw = request.POST.get('puissance', '').strip()
        v.puissance = int(puissance_raw) if puissance_raw else None

        v.numero_chassis = request.POST.get('numero_chassis', '').strip() or None
        v.num_assurance = request.POST.get('num_assurance', '').strip()

        exp = request.POST.get('expiry_assurance', '').strip()
        v.expiry_assurance = exp if exp else None

        visite = request.POST.get('date_visite', '').strip()
        v.date_visite = visite if visite else None

        v.notes = request.POST.get('notes', '').strip()

        # ── Propriétaire ──
        client_id = request.POST.get('client', '').strip()
        if not client_id:
            messages.error(request, "Veuillez sélectionner un propriétaire.")
            return render_form()

        client = Client.objects.filter(id=client_id).first()
        if not client:
            messages.error(request, "Propriétaire introuvable.")
            return render_form()
        v.client = client

        # ── Photos ──
        existing = []
        if v.photos:
            existing = [p.strip() for p in v.photos.split(';') if p.strip()]
        while len(existing) < 3:
            existing.append('')

        # Suppression
        for i in range(3):
            if request.POST.get(f'remove_photo_{i}') == '1':
                path = existing[i]
                if path and default_storage.exists(path):
                    default_storage.delete(path)
                existing[i] = ''

        # Upload / remplacement
        for i in range(3):
            uploaded = request.FILES.get(f'photo_{i}')
            if uploaded:
                if existing[i] and default_storage.exists(existing[i]):
                    default_storage.delete(existing[i])

                ext = os.path.splitext(uploaded.name)[1]
                immat_clean = v.immatriculation.replace(' ', '').replace('-', '').upper()
                filename = f"vehicules/photos/{immat_clean}_{i}{ext}"
                saved_path = default_storage.save(filename, ContentFile(uploaded.read()))
                existing[i] = saved_path

        photos_paths = [p for p in existing if p]
        if photos_paths:
            v.photos = ';'.join(photos_paths)
            v.photo = photos_paths[0]
        else:
            v.photos = ''
            v.photo = None

        v.save()
        log_action(request, ActionType.MODIFICATION, 'ADMIN', v)
        messages.success(request, f"Véhicule {v.immatriculation} mis à jour.")
        return redirect('admin_vehicules')

    return render_form()

 
# ════════════════════════════════════════════════════════
#  CLIENTS
# ════════════════════════════════════════════════════════
 


@admin_required 
def admin_creer_client(request):
    form = ClientForm()
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            log_action(request, ActionType.CREATION, 'GUERITE', client)
            messages.success(request, f"Client {client} créé.")
            return redirect('admin_clients')

        
    return render(request, 'admin_custom/clients/creer_client.html', {'form': form})

 
@admin_required
def admin_clients(request):
    from apps.vehicules.models import Client
    from apps.guerite.models import EnregistrementEntree
 
    q             = request.GET.get('q', '').strip()
    filtre_type   = request.GET.get('type', 'tous')
    ville         = request.GET.get('ville', '')
    avec_vehicule = request.GET.get('avec_vehicule', '')
 
    qs = Client.objects.prefetch_related(
        'vehicules', 'vehicules__entrees', 'vehicules__ordres_reparation'
    ).filter(is_active=True)
 
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) |
            Q(telephone__icontains=q) | Q(email__icontains=q) |
            Q(ninea__icontains=q) | Q(ville__icontains=q) |
            Q(numero_client__icontains=q)
        )
    if filtre_type and filtre_type != 'tous':
        qs = qs.filter(type_client=filtre_type)
    if ville:
        qs = qs.filter(ville=ville)
    if avec_vehicule == '1':
        qs = qs.filter(vehicules__isnull=False).distinct()
    elif avec_vehicule == '0':
        qs = qs.filter(vehicules__isnull=True)
 
    clients_list = []
    for c in qs[:100]:
        c.nb_passages = EnregistrementEntree.objects.filter(
            vehicule__client=c
        ).count()
        # Enrichir chaque véhicule avec statut_presence
        for v in c.vehicules.all():
            pass  # en_local et en_atelier sont des @property
        clients_list.append(c)
 
    all_c = Client.objects.filter(is_active=True)
    stats = {
        'total':          all_c.count(),
        'particuliers':   all_c.filter(type_client='PARTICULIER').count(),
        'entreprises':    all_c.filter(type_client='ENTREPRISE').count(),
        'total_vehicules': all_c.aggregate(n=Count('vehicules'))['n'],
    }
 
    villes = Client.objects.filter(is_active=True).exclude(
        ville__isnull=True
    ).exclude(ville='').values_list('ville', flat=True).distinct().order_by('ville')
 
    return render(request, 'admin_custom/clients/liste.html', {
        'clients':     clients_list,
        'stats':       stats,
        'villes':      villes,
        'filtre_type': filtre_type,
        'filters':     {'q': q, 'ville': ville, 'avec_vehicule': avec_vehicule},
    })
 
 
@admin_required
def admin_detail_client(request, client_id):
    from apps.vehicules.models import Client
    from apps.guerite.models import EnregistrementEntree
 
    c = get_object_or_404(
        Client.objects.prefetch_related(
            'vehicules', 'vehicules__entrees', 'vehicules__ordres_reparation'
        ),
        id=client_id
    )
    entrees = EnregistrementEntree.objects.filter(
        vehicule__client=c
    ).select_related('vehicule').order_by('-date_entree')[:30]
 
    return render(request, 'admin_custom/clients/detail.html', {
        'client': c, 'entrees': entrees,
    })
 
 
@admin_required
def admin_modifier_client(request, client_id):
    c = get_object_or_404(Client, id=client_id)

    if request.method == 'POST':
        c.type_client = request.POST.get('type_client', c.type_client)

        if c.type_client == 'ENTREPRISE':
            c.nom = (request.POST.get('nom_entreprise') or request.POST.get('nom') or c.nom).strip()
            c.prenom = ''  # jamais None
            c.ninea = request.POST.get('ninea', '').strip() or ''
            c.telephone = (
                request.POST.get('telephone_entreprise')
                or request.POST.get('telephone')
                or ''
            ).strip()
            c.nom_correspondant = request.POST.get('nom_correspondant', '').strip() or ''
            c.telephone2 = ''
        else:
            c.nom = request.POST.get('nom', c.nom).strip()
            # Important : '' au lieu de None
            c.prenom = request.POST.get('prenom', '').strip() or ''
            c.ninea = ''
            c.telephone = request.POST.get('telephone', '').strip() or ''
            c.telephone2 = request.POST.get('telephone2', '').strip() or ''

        c.email = request.POST.get('email', '').strip() or ''
        c.ville = request.POST.get('ville', '').strip() or ''
        c.adresse = request.POST.get('adresse', '').strip() or ''

        c.save()
        messages.success(request, f"Client {c} mis à jour.")
        return redirect('admin_clients')

    return render(request, 'admin_custom/clients/modifier.html', {'c': c})
 


@admin_required
def detail_vehicule(request, vehicule_id):
    """Détails complets d'un véhicule vu depuis la réception"""
    v = get_object_or_404(Vehicule.objects.select_related('client'), id=vehicule_id)
    return render(request, 'admin_custom/vehicules/detail.html', {
        'v':       v,
        'entrees': v.entrees.order_by('-date_entree')[:10],
        'or_list': v.ordres_reparation.order_by('-date_creation')[:10],
        'rec_list': v.receptions.order_by('-created_at')[:5],
    })




@admin_required
def admin_ateliers(request):

    # ── POST : créer / modifier / supprimer ──────────────────────
    if request.method == 'POST':
        action     = request.POST.get('action', '')
        atelier_id = request.POST.get('atelier_id', '').strip()

        # ── CRÉER ────────────────────────────────────────────────
        if action == 'creer':
            nom      = request.POST.get('nom', '').strip()

            if not nom:
                messages.error(request, "Le nom de l'atelier est obligatoire.")
                return redirect('admin_ateliers')

            # ── Génération du code ───
            code = request.POST.get('code', '').strip().upper()
            if not code:
                dernier = Atelier.objects.order_by('-code').first()
                if dernier and dernier.code.startswith('ATL-'):
                    try:
                        num = int(dernier.code.split('-')[1]) + 1
                    except (ValueError, IndexError):
                        num = Atelier.objects.count() + 1
                else:
                    num = Atelier.objects.count() + 1
                code = f"ATL-{num:03d}"

            if Atelier.objects.filter(code=code).exists():
                messages.error(request, f"Le code « {code} » existe déjà.")
                return redirect('admin_ateliers')

            chef_id = request.POST.get('chef_id', '').strip()
            chef    = User.objects.filter(id=chef_id).first() if chef_id else None

            a = Atelier.objects.create(
                code         = code,
                nom          = nom,
                localisation = request.POST.get('localisation', '').strip(),
                description  = request.POST.get('description', '').strip(),
                responsable  = chef,
                is_active    = 'is_active' in request.POST,
            )
            log_action(request, ActionType.CREATION, 'ADMIN', a)
            messages.success(request, f"✅ Atelier « {a.nom} » créé.")

        # ── MODIFIER ─────────────────────────────────────────────
        elif action == 'modifier' and atelier_id:
            a   = get_object_or_404(Atelier, id=atelier_id)
            nom = request.POST.get('nom', '').strip()

            if not nom:
                messages.error(request, "Le nom est obligatoire.")
                return redirect('admin_ateliers')

            chef_id      = request.POST.get('chef_id', '').strip()
            chef         = User.objects.filter(id=chef_id).first() if chef_id else None

            a.nom          = nom
            a.localisation = request.POST.get('localisation', '').strip()
            a.description  = request.POST.get('description', '').strip()
            a.responsable  = chef
            a.is_active    = 'is_active' in request.POST
            a.save()

            log_action(request, ActionType.MODIFICATION, 'ADMIN', a)
            messages.success(request, f"✅ Atelier « {a.nom} » mis à jour.")

        # ── SUPPRIMER ─────────────────────────────────────────────
        elif action == 'supprimer' and atelier_id:
            a = get_object_or_404(Atelier, id=atelier_id)

            nb_actifs = a.ordres_reparation.filter(
                statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']
            ).count()

            if nb_actifs > 0:
                messages.error(
                    request,
                    f"Impossible : l'atelier « {a.nom} » a {nb_actifs} OR actif(s). "
                    "Clôturez-les d'abord."
                )
                return redirect('admin_ateliers')

            nom = a.nom
            log_action(
                request,
                ActionType.SUPPRESSION,
                'ADMIN',
                details={'atelier': nom, 'id': str(a.id)},
            )
            a.delete()
            messages.success(request, f"✅ Atelier « {nom} » supprimé.")

        return redirect('admin_ateliers')

    # ── GET : liste ───────────────────────────────────────────────
    ateliers = list(
    Atelier.objects
    .select_related('responsable')
    .annotate(
        nb_or_en_cours=Count(
            'ordres_reparation',
            filter=Q(ordres_reparation__statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']),
            distinct=True,
        ),
        nb_or_total=Count('ordres_reparation', distinct=True),
        # ✅ Utilisateurs assignés à cet atelier via User.atelier
        nb_techniciens=Count('employes', distinct=True),
    )
    .order_by('is_active', 'nom')
    )

    # Chefs disponibles = utilisateurs avec rôle RESP_ATELIER
    chefs_disponibles = (
        User.objects
        .filter(role=Role.RESP_ATELIER, is_active=True)
        .order_by('nom', 'prenom')
    )

    stats = {
        'total':       len(ateliers),
        'actifs':      sum(1 for a in ateliers if a.is_active),
        'inactifs':    sum(1 for a in ateliers if not a.is_active),
        'nb_techniciens': sum(a.nb_techniciens for a in ateliers),
        'or_en_cours': sum(a.nb_or_en_cours for a in ateliers),
    }

    return render(request, 'admin_custom/ateliers/liste.html', {
        'ateliers':          ateliers,
        'stats':             stats,
        'chefs_disponibles': chefs_disponibles,
    })