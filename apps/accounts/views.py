"""
Vues Comptes - Connexion, déconnexion, gestion utilisateurs
"""
from datetime import date, timedelta
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
import json
from apps.notifications.hook import notifier_bon_sortie_cree
from apps.reception.forms import BonSortieForm
from apps.reception.models import Reception, StatutVehicule
from apps.reception.views import _gen_qr, get_entrees_presentes_filtrees, get_filtered_entrees
from .forms import ConnexionForm, UserCreateForm, UserEditForm, ChangePasswordForm
from .models import User, Role, LoginAttempt
from .decorators import admin_required
from apps.audit.service import log_action
from apps.audit.models import ActionType
from apps.vehicules.models import Vehicule, Client
from apps.atelier.models import OrdreReparation, Atelier
from apps.guerite.models import BonSortie, EnregistrementEntree, MotifEntree, StatutEntree, StatutViewHinstorisue, TypeBon
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
 
    return render(request, 'admin_custom/bons/bons_sortie_liste_admin.html', {
        'bons':    qs[:50],
        'stats':   stats,
        'filters': filters,
    })



 
@admin_required
def creer_bon_sortie_direct(request):
    """
    Créer un bon de sortie directement depuis la guérite,
    sans réception préalable.
    """
    # Récupérer tous les véhicules présents (non sortis) pour l'autocomplétion
    vehicules_presents = EnregistrementEntree.objects.exclude(
        statut=StatutEntree.SORTI
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
            statut=StatutEntree.SORTI
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
    rec = get_object_or_404(EnregistrementEntree, id=rec_id)
    rapport = getattr(rec, 'rapport', None)

    # Véhicules présents pour l'autocomplétion
    vehicules_presents = (
        EnregistrementEntree.objects
        .exclude(statut=StatutEntree.SORTI)
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
                if rec.vehicule:
                    bon.vehicule = rec.vehicule
                bon.save() 

                # 2) Lier l'entrée au bon
                #    ⚠️ On ne touche PAS au statut ici : SORTI sera appliqué par la guérite.
                rec.bon_sortie = bon
                rec.save(update_fields=['bon_sortie'])

                # 3) QR code + audit
                _gen_qr(bon)
                log_action(request, ActionType.CREATION, 'RECEPTION', bon)

            messages.success(request, f"Bon de sortie {bon.numero} créé.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)
    else:
        form = BonSortieForm()

    return render(request, 'reception/creer_bon_sortie.html', {
        'form': form,
        'reception': rec,
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
    entrees = get_filtered_entrees(request)
    return render(request, 'admin_custom/mouvements/historique_admin.html', {
        'entrees': entrees[:100],
        'statuts': StatutViewHinstorisue.choices,
        'motifs': MotifEntree.choices,
    })


@admin_required
def liste_receptions(request):
    qs = Reception.objects.select_related(
        'vehicule', 'vehicule__client', 'receptionniste'
    ).order_by('-created_at')
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
    return render(request, 'admin_custom/mouvements/liste_receptions_admin.html', {
        'receptions': qs[:100],
        'statuts':    StatutVehicule.choices,
        'statut_filter': statut,
    })


@admin_required
def liste_vehicules_presents(request):
    entrees = get_entrees_presentes_filtrees(request)
    return render(request, 'admin_custom/mouvements/vehicules_presents_admin.html', {'entrees': entrees, 'motifs': MotifEntree.choices})


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
    from apps.vehicules.models import Vehicule
 
    v = get_object_or_404(Vehicule, id=vehicule_id)
 
    carburants   = [
        ('NON_DEFINI','Non défini'),('ESSENCE','Essence'),('DIESEL','Diesel'),
        ('ELECTRIQUE','Électrique'),('HYBRIDE','Hybride'),('GPL','GPL'),
    ]
    transmissions = [
        ('NON_DEFINI','Non défini'),
        ('MANUELLE','Manuelle'),
        ('AUTOMATIQUE','Automatique'),
    ]
 
    if request.method == 'POST':
        v.immatriculation = request.POST.get('immatriculation', v.immatriculation).upper().strip()
        v.marque          = request.POST.get('marque', v.marque).strip()
        v.modele          = request.POST.get('modele', v.modele).strip()
        annee_raw         = request.POST.get('annee', '').strip()
        v.annee           = int(annee_raw) if annee_raw else None
        v.couleur         = request.POST.get('couleur', '').strip() or None
        v.type_carburant  = request.POST.get('type_carburant', v.type_carburant)
        v.transmission    = request.POST.get('transmission', v.transmission)
        puissance_raw     = request.POST.get('puissance', '').strip()
        v.puissance       = int(puissance_raw) if puissance_raw else None
        v.numero_chassis  = request.POST.get('numero_chassis', '').strip() or None
        v.num_assurance   = request.POST.get('num_assurance', '').strip()
        exp               = request.POST.get('expiry_assurance', '').strip()
        v.expiry_assurance = exp if exp else None
        visite            = request.POST.get('date_visite', '').strip()
        v.date_visite     = visite if visite else None
        v.notes           = request.POST.get('notes', '').strip()
 
        if request.FILES.get('photo'):
            v.photo = request.FILES['photo']
 
        v.save()
        log_action(request, ActionType.MODIFICATION, 'ADMIN', v)
        messages.success(request, f"Véhicule {v.immatriculation} mis à jour.")
        return redirect('admin_vehicules')
 
    return render(request, 'admin_custom/vehicules/modifier.html', {
        'v': v, 'carburants': carburants, 'transmissions': transmissions,
    })
 
 
# ════════════════════════════════════════════════════════
#  CLIENTS
# ════════════════════════════════════════════════════════
 
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
    from apps.vehicules.models import Client
 
    c = get_object_or_404(Client, id=client_id)
 
    if request.method == 'POST':
        c.nom        = request.POST.get('nom', c.nom).strip()
        c.prenom     = request.POST.get('prenom', c.prenom or '').strip()
        c.telephone  = request.POST.get('telephone', c.telephone).strip()
        c.telephone2 = request.POST.get('telephone2', c.telephone2 or '').strip()
        c.email      = request.POST.get('email', c.email or '').strip()
        c.adresse    = request.POST.get('adresse', c.adresse or '').strip()
        c.ville      = request.POST.get('ville', c.ville or '').strip()
        c.ninea      = request.POST.get('ninea', c.ninea or '').strip()
        c.save()
        log_action(request, ActionType.MODIFICATION, 'ADMIN', c)
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
 