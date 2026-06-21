"""
Vues Atelier - Responsable et Techniciens
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from .models import (OrdreReparation, Tache, CompteRenduIntervention, FicheControle,
                     FicheTechnique, Atelier, StatutOR, StatutTache, TypeOR)
from .forms import (OrdreReparationForm, TacheForm, CompteRenduForm,
                    FicheControleForm, FicheTechniqueForm, ORRetourForm, ReouvertureORForm)
from apps.accounts.decorators import resp_atelier_required, technicien_required, atelier_staff_required
from apps.accounts.models import User, Role
from apps.audit.service import log_action
from apps.audit.models import ActionType


# ─── RESPONSABLE ATELIER ────────────────────────────────────────────────

@resp_atelier_required
def dashboard_resp(request):
    atelier = request.user.atelier
    qs_or = OrdreReparation.objects.all()
    if atelier:
        qs_or = qs_or.filter(atelier=atelier)

    ctx = {
        'or_ouverts': qs_or.filter(statut=StatutOR.OUVERT).count(),
        'or_en_cours': qs_or.filter(statut=StatutOR.EN_COURS).count(),
        'or_clotures': qs_or.filter(statut=StatutOR.CLOTURE).count(),
        'or_reouvert': qs_or.filter(statut=StatutOR.REOUVERT).count(),
        'ordres_actifs': qs_or.filter(
            statut__in=[StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT]
        ).select_related('vehicule', 'vehicule__client', 'responsable_atelier').order_by('-date_creation')[:20],
        'taches_non_assignees': Tache.objects.filter(
            statut=StatutTache.A_FAIRE, technicien__isnull=True,
            ordre_reparation__atelier=atelier
        ).count() if atelier else 0,
        'techniciens': User.objects.filter(
            role=Role.TECHNICIEN,
            atelier=atelier,
            is_active=True
        ).annotate(
            taches_en_cours=Count('taches_assignees', filter=Q(taches_assignees__statut=StatutTache.EN_COURS)),
            taches_a_faire=Count('taches_assignees', filter=Q(taches_assignees__statut=StatutTache.A_FAIRE)),
        ) if atelier else [],
        'atelier': atelier,
    }
    return render(request, 'atelier/resp/dashboard.html', ctx)


@resp_atelier_required
def liste_or(request):
    atelier = request.user.atelier
    qs = OrdreReparation.objects.select_related(
        'vehicule', 'vehicule__client', 'atelier', 'responsable_atelier'
    )
    if atelier:
        qs = qs.filter(atelier=atelier)

    statut = request.GET.get('statut', '')
    type_or = request.GET.get('type_or', '')
    q = request.GET.get('q', '')
    if statut:
        qs = qs.filter(statut=statut)
    if type_or:
        qs = qs.filter(type_or=type_or)
    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(vehicule__immatriculation__icontains=q) |
            Q(vehicule__client__nom__icontains=q)
        )
    return render(request, 'atelier/resp/liste_or.html', {
        'ordres': qs.order_by('-date_creation')[:100],
        'statuts': StatutOR.choices,
        'types': TypeOR.choices,
        'statut_filter': statut,
    })


@resp_atelier_required
def creer_or(request):
    reception_id = request.GET.get('reception_id')
    from apps.reception.models import Reception, StatutReception
    reception = None
    if reception_id:
        reception = get_object_or_404(Reception, id=reception_id)

    form = OrdreReparationForm(initial={'atelier': request.user.atelier})
    if request.method == 'POST':
        form = OrdreReparationForm(request.POST)
        if form.is_valid():
            or_obj = form.save(commit=False)
            or_obj.vehicule = reception.vehicule if reception else get_object_or_404(
                __import__('apps.vehicules.models', fromlist=['Vehicule']).Vehicule,
                id=request.POST.get('vehicule_id')
            )
            or_obj.responsable_atelier = request.user
            or_obj.created_by = request.user
            if reception:
                or_obj.reception = reception
            or_obj.save()
            if reception:
                reception.statut = StatutReception.TRANSFERE_ATELIER
                reception.save(update_fields=['statut'])
            log_action(request, ActionType.CREATION, 'ATELIER', or_obj)
            messages.success(request, f"OR {or_obj.numero} créé.")
            return redirect('detail_or', or_id=or_obj.id)

    vehicules = __import__('apps.vehicules.models', fromlist=['Vehicule']).Vehicule.objects.all()[:50]
    return render(request, 'atelier/resp/creer_or.html', {
        'form': form, 'reception': reception, 'vehicules': vehicules
    })


@resp_atelier_required
def detail_or(request, or_id):
    or_obj = get_object_or_404(
        OrdreReparation.objects.select_related(
            'vehicule', 'vehicule__client', 'atelier', 'responsable_atelier',
            'reception', 'or_origine'
        ).prefetch_related('taches', 'taches__technicien', 'taches__comptes_rendus'),
        id=or_id
    )
    fiche_controle = getattr(or_obj, 'fiche_controle', None)
    fiche_technique = getattr(or_obj, 'fiche_technique', None)
    taches = or_obj.taches.all().order_by('priorite', 'created_at')

    ctx = {
        'or_obj': or_obj,
        'fiche_controle': fiche_controle,
        'fiche_technique': fiche_technique,
        'taches': taches,
        'taches_a_faire': taches.filter(statut=StatutTache.A_FAIRE).count(),
        'taches_en_cours': taches.filter(statut=StatutTache.EN_COURS).count(),
        'taches_terminees': taches.filter(statut=StatutTache.TERMINEE).count(),
        'duree_totale': taches.aggregate(total=Sum('duree_reelle_minutes'))['total'] or 0,
    }
    return render(request, 'atelier/resp/detail_or.html', ctx)


@resp_atelier_required
def creer_fiche_controle(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id)
    if hasattr(or_obj, 'fiche_controle'):
        return redirect('detail_or', or_id=or_id)

    form = FicheControleForm()
    if request.method == 'POST':
        form = FicheControleForm(request.POST)
        if form.is_valid():
            fc = form.save(commit=False)
            fc.ordre_reparation = or_obj
            fc.inspecte_par = request.user
            signature = request.POST.get('signature_data', '')
            fc.signature = signature
            fc.save()
            log_action(request, ActionType.CREATION, 'ATELIER', fc)
            messages.success(request, "Fiche de contrôle créée.")
            return redirect('detail_or', or_id=or_id)
    return render(request, 'atelier/resp/fiche_controle.html', {'form': form, 'or_obj': or_obj})


@resp_atelier_required
def creer_fiche_technique(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id)
    if hasattr(or_obj, 'fiche_technique'):
        return redirect('modifier_fiche_technique', or_id=or_id)

    form = FicheTechniqueForm()
    if request.method == 'POST':
        form = FicheTechniqueForm(request.POST)
        if form.is_valid(): 
            ft = form.save(commit=False)
            ft.ordre_reparation = or_obj
            ft.cree_par = request.user
            ft.save()
            log_action(request, ActionType.CREATION, 'ATELIER', ft)
            messages.success(request, "Fiche technique créée.")
            return redirect('detail_or', or_id=or_id)
    return render(request, 'atelier/resp/fiche_technique.html', {'form': form, 'or_obj': or_obj})


@resp_atelier_required
def ajouter_tache(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id)
    form = TacheForm(atelier=or_obj.atelier)
    if request.method == 'POST':
        form = TacheForm(atelier=or_obj.atelier, data=request.POST)
        if form.is_valid():
            tache = form.save(commit=False)
            tache.ordre_reparation = or_obj
            tache.save()
            if or_obj.statut == StatutOR.OUVERT:
                or_obj.statut = StatutOR.EN_COURS
                or_obj.date_debut = timezone.now()
                or_obj.save(update_fields=['statut', 'date_debut'])
            log_action(request, ActionType.CREATION, 'ATELIER', tache)
            messages.success(request, f"Tâche '{tache.libelle}' ajoutée.")
            return redirect('detail_or', or_id=or_id)
    return render(request, 'atelier/resp/ajouter_tache.html', {'form': form, 'or_obj': or_obj})


@resp_atelier_required
def assigner_technicien(request, tache_id):
    tache = get_object_or_404(Tache, id=tache_id)
    if request.method == 'POST':
        tech_id = request.POST.get('technicien_id')
        if tech_id:
            tech = get_object_or_404(User, id=tech_id, role=Role.TECHNICIEN)
            tache.technicien = tech
            tache.save(update_fields=['technicien'])
            messages.success(request, f"Tâche assignée à {tech.full_name}.")
        else:
            tache.technicien = None
            tache.save(update_fields=['technicien'])
    return redirect('detail_or', or_id=tache.ordre_reparation.id)


@resp_atelier_required
def cloture_or(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id)
    if request.method == 'POST':
        # Calculer durée totale
        total = or_obj.taches.aggregate(total=Sum('duree_reelle_minutes'))['total'] or 0
        or_obj.duree_totale_minutes = total
        or_obj.statut = StatutOR.CLOTURE
        or_obj.date_cloture = timezone.now()
        or_obj.save()
        # Mettre à jour réception si liée
        if or_obj.reception:
            from apps.reception.models import StatutReception
            or_obj.reception.statut = StatutReception.TRAVAUX_TERMINES
            or_obj.reception.save(update_fields=['statut'])
        log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {'statut': 'CLOTURE'})
        messages.success(request, f"OR {or_obj.numero} clôturé. Durée totale: {or_obj.duree_heures}.")
        return redirect('detail_or', or_id=or_id)
    return render(request, 'atelier/resp/confirmer_cloture.html', {'or_obj': or_obj})


@resp_atelier_required
def reouverture_or(request, or_id):
    or_obj = get_object_or_404(OrdreReparation, id=or_id, statut=StatutOR.CLOTURE)
    form = ReouvertureORForm()
    if request.method == 'POST':
        form = ReouvertureORForm(request.POST)
        if form.is_valid():
            or_obj.statut = StatutOR.REOUVERT
            or_obj.date_reouverture = timezone.now()
            or_obj.raison_reouverture = form.cleaned_data['raison']
            or_obj.save()
            log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', or_obj, {'statut': 'REOUVERT'})
            messages.success(request, f"OR {or_obj.numero} réouvert.")
            return redirect('detail_or', or_id=or_id)
    return render(request, 'atelier/resp/reouverture_or.html', {'form': form, 'or_obj': or_obj})


@resp_atelier_required
def creer_or_retour(request, or_origine_id):
    or_origine = get_object_or_404(OrdreReparation, id=or_origine_id, statut=StatutOR.CLOTURE)
    taches_precedentes = or_origine.taches.all()
    form = ORRetourForm(taches=taches_precedentes)

    if request.method == 'POST':
        form = ORRetourForm(taches=taches_precedentes, data=request.POST)
        if form.is_valid():
            or_retour = OrdreReparation.objects.create(
                type_or=TypeOR.RETOUR,
                vehicule=or_origine.vehicule,
                atelier=or_origine.atelier,
                responsable_atelier=request.user,
                or_origine=or_origine,
                motif_retour=form.cleaned_data['motif_retour'],
                created_by=request.user,
                reception=or_origine.reception,
            )
            # Copier fiche technique
            if hasattr(or_origine, 'fiche_technique'):
                ft = or_origine.fiche_technique
                FicheTechnique.objects.create(
                    ordre_reparation=or_retour,
                    diagnostic=ft.diagnostic,
                    pieces_recommandees=ft.pieces_recommandees,
                    main_oeuvre_estimee=ft.main_oeuvre_estimee,
                    pieces_estimees=ft.pieces_estimees,
                    temps_estime_heures=ft.temps_estime_heures,
                    observations=f"[COPIE depuis OR {or_origine.numero}] {ft.observations}",
                    cree_par=request.user,
                )
            # Copier tâches sélectionnées
            taches_ids = form.cleaned_data.get('taches_a_copier', [])
            for tache_id in taches_ids:
                tache_orig = get_object_or_404(Tache, id=tache_id)
                Tache.objects.create(
                    ordre_reparation=or_retour,
                    libelle=tache_orig.libelle,
                    description=tache_orig.description,
                    type_operation=tache_orig.type_operation,
                    priorite=tache_orig.priorite,
                    duree_estimee_minutes=tache_orig.duree_estimee_minutes,
                    est_copiee=True,
                    tache_origine=tache_orig,
                )
            log_action(request, ActionType.CREATION, 'ATELIER', or_retour,
                       {'type': 'RETOUR', 'or_origine': str(or_origine.numero)})
            messages.success(request, f"OR retour {or_retour.numero} créé.")
            return redirect('detail_or', or_id=or_retour.id)

    return render(request, 'atelier/resp/creer_or_retour.html', {
        'form': form, 'or_origine': or_origine, 'taches': taches_precedentes
    })


@resp_atelier_required
def kpi_atelier(request):
    atelier = request.user.atelier
    from datetime import timedelta
    from django.utils import timezone
    aujourd_hui = timezone.now()
    debut_mois = aujourd_hui.replace(day=1, hour=0, minute=0, second=0)

    qs = OrdreReparation.objects.all()
    if atelier:
        qs = qs.filter(atelier=atelier)

    ctx = {
        'nb_repare_mois': qs.filter(statut=StatutOR.CLOTURE, date_cloture__gte=debut_mois).count(),
        'nb_retours': qs.filter(type_or=TypeOR.RETOUR).count(),
        'duree_moy': qs.filter(statut=StatutOR.CLOTURE).aggregate(
            moy=Avg('duree_totale_minutes'))['moy'] or 0,
        'or_par_technicien': Tache.objects.filter(
            technicien__isnull=False,
            ordre_reparation__atelier=atelier,
        ).values('technicien__nom', 'technicien__prenom').annotate(
            total=Count('id'),
            minutes=Sum('duree_reelle_minutes'),
        ).order_by('-total')[:10] if atelier else [],
        'atelier': atelier,
    }
    return render(request, 'atelier/resp/kpi.html', ctx)


# ─── TECHNICIEN ────────────────────────────────────────────────────────

@technicien_required
def dashboard_technicien(request):
    mes_taches = Tache.objects.filter(
        technicien=request.user
    ).select_related('ordre_reparation', 'ordre_reparation__vehicule').order_by('statut', 'priorite')

    ctx = {
        'taches_a_faire': mes_taches.filter(statut=StatutTache.A_FAIRE),
        'taches_en_cours': mes_taches.filter(statut=StatutTache.EN_COURS),
        'taches_terminees': mes_taches.filter(statut=StatutTache.TERMINEE).order_by('-updated_at')[:5],
        'total_minutes_mois': mes_taches.filter(
            statut=StatutTache.TERMINEE,
            date_fin__month=timezone.now().month,
        ).aggregate(total=Sum('duree_reelle_minutes'))['total'] or 0,
    }
    return render(request, 'atelier/technicien/dashboard.html', ctx)


@technicien_required
def mes_taches(request):
    taches = Tache.objects.filter(
        technicien=request.user
    ).select_related('ordre_reparation', 'ordre_reparation__vehicule').order_by('statut', 'priorite')
    return render(request, 'atelier/technicien/mes_taches.html', {'taches': taches})


@technicien_required
def detail_tache(request, tache_id):
    tache = get_object_or_404(
        Tache.objects.select_related('ordre_reparation', 'ordre_reparation__vehicule', 'type_operation'),
        id=tache_id, technicien=request.user
    )
    comptes_rendus = tache.comptes_rendus.all().order_by('-date_saisie')
    return render(request, 'atelier/technicien/detail_tache.html', {
        'tache': tache, 'comptes_rendus': comptes_rendus
    })


@technicien_required
def demarrer_tache(request, tache_id):
    tache = get_object_or_404(Tache, id=tache_id, technicien=request.user)
    if tache.statut == StatutTache.A_FAIRE:
        tache.statut = StatutTache.EN_COURS
        tache.date_debut = timezone.now()
        tache.save(update_fields=['statut', 'date_debut'])
        messages.success(request, f"Tâche '{tache.libelle}' démarrée.")
    return redirect('detail_tache', tache_id=tache_id)


@technicien_required
def saisir_compte_rendu(request, tache_id):
    tache = get_object_or_404(Tache, id=tache_id, technicien=request.user)
    form = CompteRenduForm()

    if request.method == 'POST':
        form = CompteRenduForm(request.POST, request.FILES)
        if form.is_valid():
            cr = form.save(commit=False)
            cr.tache = tache
            cr.technicien = request.user
            cr.save()
            # Sauvegarder photos
            for photo_file in request.FILES.getlist('photos'):
                from .models import PhotoIntervention
                PhotoIntervention.objects.create(compte_rendu=cr, photo=photo_file)
            # Mettre à jour durée réelle tâche
            total_min = tache.comptes_rendus.aggregate(total=Sum('duree_minutes'))['total'] or 0
            tache.duree_reelle_minutes = total_min
            tache.save(update_fields=['duree_reelle_minutes'])
            log_action(request, ActionType.CREATION, 'ATELIER', cr)
            messages.success(request, "Compte rendu enregistré.")
            return redirect('detail_tache', tache_id=tache_id)

    return render(request, 'atelier/technicien/compte_rendu.html', {'form': form, 'tache': tache})


@technicien_required
def terminer_tache(request, tache_id):
    tache = get_object_or_404(Tache, id=tache_id, technicien=request.user)
    if request.method == 'POST':
        if not tache.comptes_rendus.exists():
            messages.error(request, "Vous devez saisir au moins un compte rendu avant de terminer.")
            return redirect('detail_tache', tache_id=tache_id)
        tache.statut = StatutTache.TERMINEE
        tache.date_fin = timezone.now()
        tache.save(update_fields=['statut', 'date_fin'])
        log_action(request, ActionType.CHANGEMENT_STATUT, 'ATELIER', tache, {'statut': 'TERMINEE'})
        messages.success(request, f"Tâche '{tache.libelle}' marquée comme terminée !")
    return redirect('mes_taches')
