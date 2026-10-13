"""
Vues Réception — sans devis, sans facture
"""

import os

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.core.files.storage import default_storage
from django.db.models import Count
from django.utils import timezone
from datetime import date, timedelta
import datetime
from decimal import Decimal
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models.functions import Coalesce
from django.db.models import F
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse, request
from django.views.decorators.http import require_POST
from apps.accounts.views_user_stats import format_duree
from apps.atelier.views import _entree_from_or, enrich_taches_duree
from apps.guerite.models import BonSortie, EnregistrementEntree
from apps.notifications.hook import notifier_bon_sortie_cree
from apps.reception.pdf_bon_liste import generer_pdf_liste_bons
from apps.reception.pdf_client_liste import generer_pdf_liste_clients
from apps.reception.pdf_vehicules_pdf import generer_pdf_liste_vehicules
from .models import Reception, StatutVehicule, RapportReception, TransfertAtelier, Notification
from .forms import ReceptionForm, RapportReceptionForm, TransfertAtelierForm, BonSortieForm, ORReceptionForm
from apps.accounts.choices import  MotifEntree, StatutReception, TypeBon
from apps.atelier.models import FicheTechnique, OrdreReparation, StatutOR,  FicheControle, Tache, StatutTache
from apps.vehicules.models import Client, Conducteur, Vehicule
from apps.accounts.decorators import guerite_required, receptionniste_required
from apps.accounts.models import Demandeur, Role, User
from apps.audit.service import log_action
from apps.audit.models import ActionType
from apps.documents.pdf_generator import generer_pdf_bon_sortie
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
from datetime import datetime
import base64
import uuid
from django.db.models import Count, Q, F, FloatField, Case, When, Value
from django.db.models.functions import Coalesce, Cast
# ─── Utilitaire notif ────────────────────────────────────────────────────────
def _notifier(type_notif, titre, message, reception=None):
    from apps.accounts.models import User
    for user in User.objects.filter(role=Role.RECEPTIONNISTE, is_active=True):
        Notification.objects.create(
            type_notif=type_notif, titre=titre, message=message,
            reception=reception, destinataire=user
        )


def get_entrees_presentes_filtrees(request):
    """Retourne le queryset filtré (sans pagination) — utile pour exports."""
    qs = (
        EnregistrementEntree.objects
        .select_related("vehicule", "vehicule__client", "conducteur", "conducteur__client")
        .filter(date_sortie__isnull=True)
        .order_by("-date_entree")
    )

    q = request.GET.get("q")
    motif = request.GET.get("motif")
    date_debut = request.GET.get("date_debut", "").strip()
    date_fin = request.GET.get("date_fin", "").strip()
    duree_valeur = request.GET.get("duree_valeur", "").strip()
    duree_unite = request.GET.get("duree_unite", "h").strip() or "h"

    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
            | Q(vehicule__client__telephone__icontains=q)
            | Q(conducteur__nom__icontains=q)
        )

    if motif:
        qs = qs.filter(motif=motif)

    if date_debut:
        dt = datetime.strptime(date_debut, "%Y-%m-%d")
        qs = qs.filter(date_entree__gte=timezone.make_aware(dt))

    if date_fin:
        dt = datetime.strptime(date_fin, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
        qs = qs.filter(date_entree__lte=timezone.make_aware(dt))

    if duree_valeur != "":
        try:
            n = int(duree_valeur)
            if duree_unite == "h":
                unite_delta = timedelta(hours=1)
            elif duree_unite == "m":
                unite_delta = timedelta(days=30)
            else:
                unite_delta = timedelta(days=1)

            if n == 0:
                n = 1

            if n > 0:
                seuil = timezone.now() - (unite_delta * n)
                qs = qs.filter(date_entree__lt=seuil)
        except (ValueError, TypeError):
            pass

    return qs


def paginate_queryset(request, qs, per_page=25):
    """Pagination réutilisable."""
    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)
    return page

 
# ─── DASHBOARD ───────────────────────────────────────────────────────────────
@receptionniste_required
def dashboard(request):
    today = timezone.localdate()

    # ── Entrées guérite pour réparation, en cours ──
    entreesReparation = (
        EnregistrementEntree.objects
        .filter(motif=MotifEntree.REPARATION, statut=StatutVehicule.EN_COURS)
        .select_related('vehicule', 'vehicule__client')
        .order_by('-date_entree')
    )

    # ── Réceptions actives (pas encore sorties) ──
    receptions = (
        Reception.objects
        .exclude(statut=StatutVehicule.SORTI)
        .select_related('vehicule', 'vehicule__client')
        .prefetch_related('transferts__atelier')
        .order_by('-created_at')
    )

    # ── Notifications non lues ──
    notifs = (
        Notification.objects
        .filter(destinataire=request.user, lue=False)
        .select_related('reception')[:9]
    )

    # ── OR actifs ──
  
    or_actifs = (
        OrdreReparation.objects
        .filter(
            statut__in=[StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT],
            reception__in=receptions,
        )
        .select_related('vehicule', 'reception')
        .prefetch_related('ateliers', 'taches')
        .annotate(
            nb_taches=Count('taches', distinct=True),
            nb_validees=Count(
                'taches',
                filter=Q(taches__statut=StatutTache.VALIDEE),
                distinct=True,
            ),
        ).annotate(
            # ratio 0..1 (0 si aucune tâche)
            progression=Case(
                When(nb_taches=0, then=Value(0.0)),
                default=Cast(F('nb_validees'), FloatField())
                         / Cast(F('nb_taches'), FloatField()),
                output_field=FloatField(),
            ),
            # terminé à 100 % (et au moins 1 tâche)
            est_complet=Case(
                When(nb_taches__gt=0, nb_validees=F('nb_taches'), then=Value(1)),
                default=Value(0),
            ),
        )
        # 1) complets d'abord, 2) meilleure progression, 3) plus de tâches validées, 4) plus récent
        .order_by('-est_complet', '-progression', '-nb_validees', '-date_creation')[:6]
    )

    # ── Entrées / sorties du jour ──
    entrees_today = EnregistrementEntree.objects.filter(date_entree__date=today)
    sorties_today = EnregistrementEntree.objects.filter(date_sortie__date=today)

    # ══════════════════════════════════════════════════════════════
    #  FICHES EN ATTENTE DE CRÉATION D'OR
    #  → Réceptions SANS OR + avec FicheControle signée par le client
    # ══════════════════════════════════════════════════════════════
    base_attente_or = (
        Reception.objects
        .exclude(statut=StatutVehicule.SORTI)
        .filter(ordre_reparation__isnull=True)                    # pas d'OR
        .filter(entree__fiche_controle__isnull=False)             # fiche existe
        .filter(
            Q(entree__fiche_controle__signature_client_avant__isnull=False)
            & ~Q(entree__fiche_controle__signature_client_avant='')
        )                                                         # client signé
    )

    fiches_attente_or = (
        base_attente_or
        .select_related(
            'vehicule', 'vehicule__client',
            'entree',
            'entree__fiche_controle',
        )
        .order_by('-created_at')[:7]
    )

    nb_attente_or = base_attente_or.count()

    # ── Entrées récentes ──
    entrees_recentes = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
        .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
        .order_by(F('date_tri').desc())[:7]
    )

    # ── Véhicules présents sans réception ──
    vehicules_presents = (
        EnregistrementEntree.objects
        .filter(date_sortie__isnull=True)
        .filter(bon_sortie__isnull=True)
        .filter(reception__isnull=True)
        .select_related('vehicule', 'vehicule__client', 'conducteur')
        .order_by('-date_entree')[:7]
    )

    ctx = {
        # Compteurs
        'nb_entrees_today':    entrees_today.count(),
        'nb_sorties_today':    sorties_today.count(),
        'nb_attente_or':       nb_attente_or,

        # Listes
        'receptions':          receptions,
        'notifs':              notifs,
        'nb_notifs':           notifs.count(),
        'or_actifs':           or_actifs,
        'vehicules_presents':  vehicules_presents,
        'entrees_recentes':    entrees_recentes,
        'fiches_attente_or':   fiches_attente_or,

        # KPI
        'nb_a_traiter':        entreesReparation.filter(reception__isnull=True).count(),
        'nb_en_atelier':       receptions.filter(statut=StatutVehicule.RAPPORT_FAIT).count(),
        'nb_presents':         receptions.filter(statut=StatutVehicule.FICHE_CONTROLE).count(),
        'nb_termines':         receptions.filter(statut=StatutVehicule.TRAVAUX_TERMINES).count(),

        # Helpers
        'today':               today,
        'entreesNbr':          get_entrees_presentes_filtrees(request),
    }

    return render(request, 'reception/dashboard.html', ctx)


# ─── NOTIFICATIONS ──────────────────────────────────────────────────────────── 
@receptionniste_required
def notifs_json(request):
    notifs = list(Notification.objects.filter(
        destinataire=request.user, lue=False
    ).values('id', 'type_notif', 'titre', 'message', 'created_at', 'reception_id'))
    return JsonResponse({'notifs': notifs, 'count': len(notifs)})


@receptionniste_required
def marquer_lues(request):
    Notification.objects.filter(destinataire=request.user, lue=False).update(lue=True)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})
    return redirect('dashboard_reception')


# ─── RÉCEPTIONS ──────────────────────────────────────────────────────────────
@receptionniste_required
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
    page_obj = paginate_queryset(request, qs, per_page=25)
    return render(request, 'reception/liste_receptions.html', {
        'receptions': page_obj,
        'page_obj': page_obj,
        'statuts':    StatutReception.choices,
        'statut_filter': statut,
    })




@receptionniste_required
def creer_reception(request):
    entree_id = request.GET.get('entree_id')
    entree = None
    if entree_id:
        entree = get_object_or_404(
            EnregistrementEntree,
            id=entree_id,
            motif=MotifEntree.REPARATION,

        )
        if hasattr(entree, 'reception'):
            messages.warning(request, "Cette entrée a déjà une réception.")
            return redirect('detail_reception', rec_id=entree.reception.id)

    if request.method == 'POST':
        entree_id_post   = (request.POST.get('entree_id') or
                            request.POST.get('entree_select', '')).strip()
        vehicule_id_post = request.POST.get('vehicule_id', '').strip()
        decision         = request.POST.get('decision', 'VERS_ATELIER')
        observations     = request.POST.get('observations', '').strip()

        error    = None
        vehicule = None

        if not vehicule_id_post and not entree_id_post:
            error = "Sélectionnez un véhicule ou une entrée guérite."
        elif not observations:
            error = "Les observations sont obligatoires."
        else:
            if entree_id_post:
                try:
                    ent = EnregistrementEntree.objects.get(id=entree_id_post)
                    vehicule = ent.vehicule
                    entree   = ent
                except EnregistrementEntree.DoesNotExist:
                    error = "Entrée introuvable."
            elif vehicule_id_post:
                try:
                    vehicule = Vehicule.objects.get(id=vehicule_id_post)
                except Vehicule.DoesNotExist:
                    error = "Véhicule introuvable."

        if error:
            return render(request, 'reception/creer_reception.html', {
                'entree': entree, 'error': error,
            })

        # Créer la réception
        rec = Reception.objects.create(
            entree         = entree,
            vehicule       = vehicule,
            statut         = StatutVehicule.RAPPORT_FAIT,
            receptionniste = request.user,
            observations   = observations,
        )

        # ── Statut de l'entrée → RAPPORT_FAIT ──
        if entree:
            entree.statut = StatutVehicule.RAPPORT_FAIT
            entree.save(update_fields=['statut'])

        log_action(request, ActionType.CREATION, 'RECEPTION', rec, {'decision': decision})
        messages.success(request, f"Réception {rec.numero} créée.")

        if decision == 'SORTIE_DIRECTE':
            return redirect('creer_bon_sortie_rec', rec_id=entree.id)

        return redirect('detail_reception', rec_id=rec.id)

    return render(request, 'reception/creer_reception.html', {'entree': entree})





# ─── Autocomplete véhicules ───────────────────────────────────────────────────
@guerite_required
def api_vehicules(request):
    from apps.vehicules.models import Vehicule
 
    q        = request.GET.get('q', '').strip()
    en_cours = request.GET.get('en_cours', '')
 
    qs = Vehicule.objects.select_related('client').filter(is_active=True)
    if q:
        qs = qs.filter(
            Q(immatriculation__icontains=q) |
            Q(marque__icontains=q) |
            Q(modele__icontains=q) |
            Q(client__nom__icontains=q) |
            Q(client__prenom__icontains=q) |
            Q(client__telephone__icontains=q)
        )
 
    results = []
    for v in qs[:12]:
        entree_active = v.entrees.filter(statut='EN_COURS').order_by('-date_entree').first()
        # Si filtre en_cours, on saute les véhicules sans entrée active
        if en_cours == '1' and not entree_active:
            continue
        results.append({
            'id':             str(v.id),
            'immatriculation': v.immatriculation,
            'marque':         v.marque,
            'modele':         v.modele,
            'annee':          v.annee,
            'couleur':        v.couleur or '',
            'client':         str(v.client),
            'telephone':      v.client.telephone,
            'en_cours':       bool(entree_active),
            'date_entree':    entree_active.date_entree.strftime('%d/%m/%Y %H:%M') if entree_active else '',
        })
 
    return JsonResponse({'results': results})
 



# ─── Entrées en cours pour un véhicule ───────────────────────────────────────
@guerite_required
def api_entrees_vehicule(request):
    from .models import EnregistrementEntree
 
    vehicule_id = request.GET.get('vehicule_id', '').strip()
    if not vehicule_id:
        return JsonResponse({'entrees': []})
 
    entrees = EnregistrementEntree.objects.filter(
        vehicule_id=vehicule_id,
        statut='EN_COURS',
        motif='REPARATION',
        reception__isnull=True,   # Pas encore réceptionnées
    ).order_by('-date_entree')
 
    results = [{
        'id':          str(e.id),
        'numero':      e.numero,
        'motif':       e.get_motif_display(),
        'date_entree': e.date_entree.strftime('%d/%m/%Y %H:%M'),
    } for e in entrees]
 
    return JsonResponse({'entrees': results})
 



@guerite_required 
def historique_entrees(request):
    qs = get_filtered_entrees(request)
    page_obj = paginate_queryset(request, qs, per_page=25)

    return render(request, 'reception/historique.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'statuts': StatutVehicule.choices,
        'motifs': MotifEntree.choices,
    })

def get_filtered_entrees(request):
      
    entrees = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
        .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
        .order_by(F('date_tri').desc())
        )

    statut = request.GET.get('statut')
    motif = request.GET.get('motif')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    q = request.GET.get('q', '')

    if statut == 'SORTI':
        entrees = entrees.filter(statut='SORTI')
    if statut == 'PRESENT':
        entrees = entrees.exclude(statut='SORTI')
    if motif:
        entrees = entrees.filter(motif=motif)
    if date_debut:
        entrees = entrees.filter(date_entree__date__gte=date_debut)
    if date_fin:
        entrees = entrees.filter(date_entree__date__lte=date_fin)
    if q:
        entrees = entrees.filter(
            Q(vehicule__immatriculation__icontains=q) |
            Q(numero__icontains=q) |
            Q(vehicule__client__nom__icontains=q)
        )
    return entrees  # retourne tout, pas de limite 100


@receptionniste_required
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
    signature_apres_faite = bool(
            fiche_controle
            and fiche_controle.signature_client_apres
            and str(fiche_controle.signature_client_apres).strip()
    )
    bon_sortie   = BonSortie.objects.filter(vehicule=rec.vehicule, reception=rec).first()
    
    return render(request, 'reception/detail_reception.html', {
        'rec': rec, 
        'or_list': or_list,
          'bon_sortie': bon_sortie,
        'fiche_technique': getattr(entree, 'fiche_technique', None) if entree else None,
        'a_fiche_controle': technicien_a_signe, 
        'client_a_signe': client_a_signe,
        'fiche_controle': fiche_controle,
        'signature_apres_faite':  signature_apres_faite, 

    })
 

@receptionniste_required
def detail_vehicule(request, vehicule_id):
    """Détails complets d'un véhicule vu depuis la réception"""
    v = get_object_or_404(Vehicule.objects.select_related('client'), id=vehicule_id)
    return render(request, 'reception/detail_vehicule.html', {
        'v':       v,
        'entrees': v.entrees.order_by('-date_entree')[:10],
        'or_list': v.ordres_reparation.order_by('-date_creation')[:10],
        'rec_list': v.receptions.order_by('-created_at')[:5],
    })
 
 
# ─── RAPPORT ─────────────────────────────────────────────────────────────────
@receptionniste_required
def creer_rapport(request, rec_id):
    rec = get_object_or_404(Reception, id=rec_id)
    if hasattr(rec, 'rapport'):
        messages.info(request, "Rapport déjà créé.")
        return redirect('choisir_ateliers', rec_id=rec.id)

    form = RapportReceptionForm()
    if request.method == 'POST':
        form = RapportReceptionForm(request.POST)
        if form.is_valid():
            rapport          = form.save(commit=False)
            rapport.reception = rec
            rapport.cree_par  = request.user
            rapport.save()
            rec.statut = StatutVehicule.RAPPORT_FAIT
            rec.save(update_fields=['statut'])
            log_action(request, ActionType.CREATION, 'RECEPTION', rapport)
            if rapport.decision == 'SORTIE_DIRECTE':
                messages.success(request, "Rapport créé — sortie directe. Créez le bon de sortie.")
                return redirect('creer_bon_sortie_rec', rec_id=rec.id)
            messages.success(request, "Rapport créé. Choisissez les ateliers.")
            return redirect('choisir_ateliers', rec_id=rec.id)

    return render(request, 'reception/creer_rapport.html', {'form': form, 'rec': rec})


# ─── TRANSFERT ATELIERS ───────────────────────────────────────────────────────
@receptionniste_required
def choisir_ateliers(request, rec_id):
    rec  = get_object_or_404(Reception, id=rec_id)
    form = TransfertAtelierForm()
    if request.method == 'POST':
        form = TransfertAtelierForm(request.POST)
        if form.is_valid():
            for atelier in form.cleaned_data['ateliers']:
                TransfertAtelier.objects.get_or_create(
                    reception=rec, atelier=atelier,
                    defaults={'motif': form.cleaned_data['motif'], 'effectue_par': request.user}
                )
            rec.statut = StatutVehicule.EN_ATELIER
            rec.save(update_fields=['statut'])
            noms = ', '.join(a.nom for a in form.cleaned_data['ateliers'])
            log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', rec, {'ateliers': noms})
            messages.success(request, f"Transféré vers : {noms}")
            return redirect('detail_reception', rec_id=rec.id)

    return render(request, 'reception/choisir_ateliers.html', {
        'form': form, 'rec': rec,
        'transferts': rec.transferts.select_related('atelier').order_by('-date_transfert')
    })

 
@receptionniste_required
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
    return render(request, 'reception/liste_or.html', {
         'ors': ors, 'statut': statut, 'q': q,
    })


@receptionniste_required
def detail_or_rec(request, or_id):
    or_obj = get_object_or_404(
        OrdreReparation.objects
        .select_related(
            'vehicule', 'vehicule__client',
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

    return render(request, 'reception/detail_or.html', {
        'or':              or_obj,
        'entree':          entree,
        'fiche_controle':  fiche_controle,
        'fiche_technique': fiche_technique,
        'taches':          taches,
        'nb_validees':     nb_validees,
    })



@receptionniste_required
def cloture_or(request, or_id):
    o = get_object_or_404(OrdreReparation, id=or_id)
    if request.method != 'POST':
        return redirect('detail_or_rec', or_id=or_id)

    now = timezone.now()
    a_valider = list(o.taches.exclude(statut=StatutTache.VALIDEE))

    for t in a_valider:
        t.date_debut = t.date_debut or now
        t.date_fin = t.date_fin or now
        t.duree_reelle_minutes = t.duree_reelle_minutes or t.duree_estimee_minutes or 0
        t.statut = StatutTache.VALIDEE
        t.valide_par = request.user
        t.date_validation = now
        if not t.commentaire_validation:
            t.commentaire_validation = "Validée automatiquement à la clôture de l'OR."
        t.save()

    total = o.taches.aggregate(t=Sum('duree_reelle_minutes'))['t'] or 0
    o.duree_totale_minutes = total
    o.statut = StatutOR.CLOTURE
    o.date_cloture = now
    o.save()

    if o.reception:
        o.reception.statut = StatutVehicule.TRAVAUX_TERMINES
        o.reception.save(update_fields=['statut'])
        _notifier(
            'OR_CLOTURE',
            f"OR {o.numero} clôturé",
            f"Travaux terminés sur {o.vehicule.immatriculation}.",
            o.reception,
        )

    log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', o, {
        'statut': 'CLOTURE',
        'nb_taches_auto_validees': len(a_valider),
    })
    messages.success(
        request,
        f"OR {o.numero} clôturé ({len(a_valider)} tâche(s) validée(s)).",
    )
    return redirect('detail_reception', rec_id=o.reception_id)


@receptionniste_required
def reouverture_or(request, or_id):
    o = get_object_or_404(OrdreReparation, id=or_id, statut=StatutOR.CLOTURE)
    if request.method == 'POST':
        o.statut              = StatutOR.REOUVERT
        o.date_reouverture    = timezone.now()
        o.raison_reouverture  = request.POST.get('raison', '')
        o.save()
        if o.reception:
            o.reception.statut = StatutVehicule.REPARATION_EN_COURS
            o.reception.save(update_fields=['statut'])
            _notifier('OR_REOUVERT', f"OR {o.numero} réouvert",
                      f"Réouverture sur {o.vehicule.immatriculation}.", o.reception)
        log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', o, {'statut': 'REOUVERT'})
        messages.success(request, f"OR {o.numero} réouvert.")
    return redirect('detail_reception', rec_id=o.reception_id)






@receptionniste_required
def detail_bon_sortie(request, bon_id):
    bon = get_object_or_404(
        BonSortie.objects.select_related('vehicule', 'vehicule__client', 'reception'),
        id=bon_id
    )
    return render(request, 'reception/detail_bon_sortie.html', {'bon': bon})

 

def pdf_bon_sortie(request, bon_id):
    bon = get_object_or_404(BonSortie, id=bon_id)
    pdf = generer_pdf_bon_sortie(bon)
    log_action(request, ActionType.TELECHARGEMENT, 'RECEPTION', bon)
    r = HttpResponse(pdf, content_type='application/pdf')
    r['Content-Disposition'] = f'attachment; filename="bon-sortie-{bon.numero}.pdf"'
    return r




@receptionniste_required
def export_bons_pdf(request):
    # Réutilise ta fonction de filtre existante si tu en as une
    qs = BonSortie.objects.select_related(
        'vehicule', 'cree_par', 'valide_par'
    ).order_by('-created_at')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(nom_demandeur__icontains=q) |
            Q(vehicule__immatriculation__icontains=q)
        )

    type_bon = request.GET.get('type', '').strip()
    if type_bon:
        qs = qs.filter(types=type_bon)

    etat = request.GET.get('etat', '').strip()
    if etat:
        qs = qs.filter(etats=etat)

    # Génère le PDF (ReportLab ou ta fonction existante)
    pdf_bytes = generer_pdf_liste_bons(qs)  # à créer / adapter

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="bons-sortie.pdf"'
    return response


# ─── Helper QR ────────────────────────────────────────────────────────────────
def _gen_qr(bon):
    try:
        
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(f"GARAGE|{bon.numero}|{bon.vehicule.immatriculation}")
        qr.make(fit=True)
        buf = BytesIO()
        qr.make_image().save(buf, 'PNG')
        bon.qr_code.save(f"qr-{bon.numero}.png", ContentFile(buf.getvalue()), save=True)
    except Exception:
        pass



# ─── LISTE BONS DE SORTIE ────────────────────────────────────────────────────
@guerite_required
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

    return render(request, 'reception/bons_sortie_liste.html', {
        'bons':    page_obj,
        'page_obj': page_obj,
        'stats':   stats,
        'filters': filters,
    })
 
# ─── DETAIL BON DE SORTIE (guérite) ──────────────────────────────────────────
@guerite_required
def detail_bon_sortie_guerite(request, bon_id):
    bon = get_object_or_404(
        BonSortie.objects.select_related(
            'vehicule',
            'vehicule__client',
            'cree_par',
            'valide_par',
            'reception'
        ),
        id=bon_id
    )

    super_receptionniste = request.user.role in (Role.SUPER_RECEPTIONNISTE, Role.ADMIN)

    return render(
        request,
        'reception/bons_sortie_detail.html',
        {
            'bon': bon,
            'super': super_receptionniste
        }
    )



def save_signature_from_dataurl(instance, data_url, field_name='signature'):
    """Convertit un dataURL canvas en fichier image et le sauvegarde."""
    if not data_url or not data_url.startswith('data:image'):
        return False
    try:
        format, imgstr = data_url.split(';base64,')
        ext = format.split('/')[-1]
        filename = f"sig_{uuid.uuid4().hex[:10]}.{ext}"
        data = ContentFile(base64.b64decode(imgstr), name=filename)
        getattr(instance, field_name).save(filename, data, save=False)
        return True
    except Exception as e:
        print("Erreur signature :", e)
        return False
 
    
 
# ─── VALIDER BON DE SORTIE ────────────────────────────────────────────────────
@guerite_required
def valider_bon_sortie_divers(request, bon_id):
    bon = get_object_or_404(BonSortie, id=bon_id)

    if request.method == 'POST':
        # Cas 1 : l'admin a déjà une signature stockée
        if request.user.signature:
            bon.signature_admin = request.user.signature
            bon.etats = 'VALIDER'
            bon.est_valide = True
            bon.valide_par = request.user
            bon.date_validation = timezone.now()
            bon.save()

            log_action(request, ActionType.CHANGEMENT_STATUT, 'GUERITE', bon, {'etat': 'VALIDER'})
            messages.success(request, f"Bon {bon.numero} validé avec votre signature.")
            if request.user.role == Role.ADMIN:
                return redirect('liste_bons_admin')
            else:
                return redirect('liste_bons_sortie')

        # Cas 2 : pas encore de signature → on récupère celle du canvas
        signature_data = request.POST.get('signature_admin')

        if not signature_data:
            messages.error(request, "Vous devez signer avant de valider.")
            return redirect(request.path)

        # On enregistre la signature sur l'utilisateur (pour les prochaines fois)
        if not save_signature_from_dataurl(request.user, signature_data, 'signature'):
            messages.error(request, "Erreur lors de l'enregistrement de la signature.")
            return redirect(request.path)
        request.user.save()

        # On met aussi la signature sur le bon
        bon.signature_admin = request.user.signature
        bon.etats = 'VALIDER'
        bon.est_valide = True
        bon.valide_par = request.user
        bon.date_validation = timezone.now()
        bon.save()

        log_action(request, ActionType.CHANGEMENT_STATUT, 'GUERITE', bon, {'etat': 'VALIDER'})
        messages.success(request, f"Bon {bon.numero} validé. Votre signature a été enregistrée.")
        if request.user.role == Role.ADMIN:
            return redirect('liste_bons_admin')
        else:
            return redirect('liste_bons_sortie')

    return redirect('detail_bon_sortie_guerite', bon_id=bon.id)
  

# ─── VALIDER BON DE SORTIE ────────────────────────────────────────────────────
@guerite_required
def valider_bon_sortie_vehicule(request, bon_id):
    bon = get_object_or_404(BonSortie, id=bon_id)

    if request.method == 'POST':
        # Cas 1 : l'admin a déjà une signature stockée
        if request.user.signature:
            bon.signature_admin = request.user.signature   # on récupère juste le lien
            bon.etats = 'APPROBATION'
            bon.approuve_par = request.user
            bon.date_approbation = timezone.now()
            bon.save()

            log_action(request, ActionType.CHANGEMENT_STATUT, 'ADMIN', bon, {'etat': 'APPROBATION'})
            messages.success(request, f"Bon {bon.numero} approuvé avec votre signature.")
            if request.user.role == Role.ADMIN:
                return redirect('liste_bons_admin')
            else:
                return redirect('liste_bons_sortie') # adapte l’URL

        # Cas 2 : l'admin n'a pas encore de signature → il doit en fournir une
        signature_data = request.POST.get('signature_admin')
        if not signature_data:
            messages.error(request, "Vous devez signer avant de valider.")
            return redirect(request.path)

        # On sauvegarde la signature sur l'utilisateur (pour les prochaines fois)
        if not save_signature_from_dataurl(request.user, signature_data, 'signature'):
            messages.error(request, "Erreur lors de l'enregistrement de la signature.")
            return redirect(request.path)
        request.user.save()

        # On met aussi la signature sur le bon
        bon.signature_admin = request.user.signature
        bon.etats = 'APPROBATION'
        bon.approuve_par = request.user
        bon.date_approbation = timezone.now()
        bon.save()

        log_action(request, ActionType.CHANGEMENT_STATUT, 'ADMIN', bon, {'etat': 'APPROBATION'})
        messages.success(request, f"Bon {bon.numero} approuvé. Votre signature a été enregistrée.")
        if request.user.role == Role.ADMIN:
            return redirect('liste_bons_admin')
        else:
            return redirect('liste_bons_sortie')

    return redirect('detail_bon_sortie_guerite', bon_id=bon.id)


 
 # ─── PDF BON DE SORTIE (guérite) ─────────────────────────────────────────────
@guerite_required
def pdf_bon_sortie_guerite(request, bon_id):
    from django.http import HttpResponse
    bon = get_object_or_404(BonSortie, id=bon_id)
    try:
        pdf = generer_pdf_bon_sortie(bon)
        log_action(request, ActionType.TELECHARGEMENT, 'GUERITE', bon)
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="bon-sortie-{bon.numero}.pdf"'
        return resp
    except Exception as e:
        messages.error(request, f"Erreur génération PDF: {e}")
        return redirect('detail_bon_sortie_guerite', bon_id=bon_id)
 


# ─── BON DE SORTIE ────────────────────────────────────────────────────────────
@receptionniste_required
def creer_bon_sortie(request, rec_id):
    Enreg = get_object_or_404(EnregistrementEntree, id=rec_id)
    rapport = getattr(Enreg, 'rapport', None)

    # La réception associée (si elle existe)
    reception = getattr(Enreg, 'reception', None)

    vehicules_presents = (
        EnregistrementEntree.objects
        .exclude(statut=StatutVehicule.SORTI)
        .select_related('vehicule', 'conducteur', 'vehicule__client')
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

                # 2) Lier le bon à l'entrée + passer l'entrée en SORTI
                Enreg.bon_sortie = bon
                Enreg.save(update_fields=['bon_sortie'])


                # 3) Faire passer la réception associée en SORTI (si elle existe)
                if reception is not None:
                    reception.statut = StatutVehicule.BON_SORTIE_FAIT   # ← adapte la constante
                    reception.date_sortie = timezone.now()    # si le champ existe
                    reception.save(update_fields=['statut'])

                # 4) QR code
                _gen_qr(bon)

            # 5) Notification + audit (hors transaction, non bloquant)
            est_admin = request.user.role == Role.ADMIN
            if not est_admin:
                notifier_bon_sortie_cree(bon)

            log_action(request, ActionType.CREATION, 'RECEPTION', bon)

            messages.success(request, f"Bon de sortie {bon.numero} créé.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)
    else:
        form = BonSortieForm()

    return render(request, 'reception/creer_bon_sortie.html', {
        'form': form,
        'rec': Enreg,
        'reception': Enreg,
        'vehicles_data': vehicles_data,
        'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
        'sortie_directe': bool(rapport and rapport.decision == 'SORTIE_DIRECTE'),
    })



@receptionniste_required
def modifier_motif_reception(request, entree_id):
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
    return redirect("detail_entree_rec", entree_id=entree.id)


def autocomplete_vehicules_presents(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    # BUG CORRIGÉ : on filtre sur l'immatriculation (filter, pas exclude)
    # et on exclut séparément les véhicules déjà sortis.
   
    entrees = EnregistrementEntree.objects.filter(
        vehicule__immatriculation__icontains=q,
    ).exclude(
        motif=MotifEntree.VISITE
    ).exclude(
        bon_sortie__isnull=False
    ).select_related('vehicule', 'vehicule__client', 'conducteur')[:15]

    results = []
    for e in entrees:
        v = e.vehicule
        results.append({
            'id': v.id,
            'immatriculation': v.immatriculation,
            'client_nom': v.client.nom if v.client else '',
            'conducteur_nom': f"{e.conducteur.nom} {e.conducteur.prenom}".strip() if e.conducteur else '',
        })
    return JsonResponse({'results': results})




def autocomplete_vehicules_reception(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    # Entrées encore présentes, motif réparation, sans réception
    entrees = (
        EnregistrementEntree.objects
        .filter(
            date_sortie__isnull=True,
            motif=MotifEntree.REPARATION,
        )
        .filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__marque__icontains=q)
            | Q(vehicule__modele__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )
        .filter(reception__isnull=True)  # pas encore de réception
        .select_related('vehicule', 'vehicule__client', 'conducteur')
        .order_by('-date_entree')[:15]
    )

    results = []
    for e in entrees:
        v = e.vehicule
        client = v.client
        results.append({
            'id': str(v.id),
            'entree_id': str(e.id),
            'immatriculation': v.immatriculation,
            'marque': v.marque or '',
            'modele': v.modele or '',
            'annee': v.annee or '',
            'client': str(client) if client else '—',
            'telephone': getattr(client, 'telephone', '') or '',
            'en_cours': True,
            'date_entree': e.date_entree.strftime('%d/%m/%Y %H:%M') if e.date_entree else '',
        })

    return JsonResponse({'results': results})

@guerite_required
def detail_entree(request, entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree'),
        id=entree_id
    )
    return render(request, 'reception/Entre_detail_rec.html', {'entree': entree})
 

@guerite_required
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
            return render(request, 'reception/creer_bon_sortie.html', {
                'vehicles_data': vehicles_data,
                'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
                'form': BonSortieForm(),
                'reception': None,
            })

        try:
            vehicule = Vehicule.objects.get(id=vehicule_id)
        except Vehicule.DoesNotExist:
            messages.error(request, "Véhicule introuvable.")
            return render(request, 'reception/creer_bon_sortie.html', {
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
        est_admin = request.user.role == Role.ADMIN
        if not est_admin:
            notifier_bon_sortie_cree(bon)
        log_action(request, ActionType.CREATION, 'GUERITE', bon)
        messages.success(request, f"Bon de sortie {bon.numero} créé.")
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    # GET : afficher le formulaire
    form = BonSortieForm()
    return render(request, 'reception/creer_bon_sortie.html', {
        'vehicles_data': vehicles_data,
        'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
        'form': form,
        'reception': None,  # pas de réception pré-sélectionnée
    })


def liste_vehicules_presents(request):
    qs = get_entrees_presentes_filtrees(request)
    page_obj = paginate_queryset(request, qs, per_page=25)

    return render(request, 'reception/vehicules_presents_rec.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'motifs': MotifEntree.choices,  # adapte
    })


 
@guerite_required
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
            
            est_admin = request.user.role == Role.ADMIN
            if not est_admin:
                notifier_bon_sortie_cree(bon)
            log_action(request, ActionType.CREATION, 'GUERITE', bon, {'type': 'DIVERS'})
            messages.success(request, f"Bon de sortie {bon.numero} créé avec succès.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    return render(request, 'reception/creer_divers.html') 





@guerite_required
def autocomplete_demandeur(request):
    """
    Recherche fusionnée dans 3 sources : Client, User (employés) et
    Demandeur. Renvoie une liste unifiée avec un champ `source` pour
    distinguer l'origine de chaque résultat, et un `exact_match`
    global pour savoir si le texte tapé correspond déjà à un nom
    existant (sert à afficher ou non le bouton "Créer").
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': [], 'exact_match': False})

    results = []

    # ── 1. Clients ──
    clients = Client.objects.filter(
        models.Q(nom__icontains=q) | models.Q(telephone__icontains=q)
    )[:8]
    for c in clients:
        results.append({
            'source': 'CLIENT',
            'id': str(c.id),
            'nom': c.nom,
            'numero': getattr(c, 'telephone', '') or '',
            'detail': 'Client',
        })

    # ── 2. Employés (User actifs) ──
    employes = User.objects.filter(is_active=True).filter(
        models.Q(nom__icontains=q) | models.Q(prenom__icontains=q) | models.Q(matricule__icontains=q)
    )[:8]
    for e in employes:
        results.append({
            'source': 'EMPLOYE',
            'id': str(e.id),
            'nom': e.full_name if hasattr(e, 'full_name') else f"{e.prenom} {e.nom}",
            'numero': getattr(e, 'telephone', '') or getattr(e, 'matricule', '') or '',
            'detail': e.get_role_display() if hasattr(e, 'get_role_display') else 'Employé',
        })

    # ── 3. Demandeurs déjà créés ──
    demandeurs = Demandeur.objects.filter(
        models.Q(nom__icontains=q) | models.Q(numero__icontains=q)
    )[:8]
    for d in demandeurs:
        results.append({
            'source': 'DEMANDEUR',
            'id': str(d.id),
            'nom': d.nom,
            'numero': d.numero,
            'detail': d.description or 'Demandeur',
        })

    qNorm = q.strip().lower()
    exact_match = any(r['nom'].strip().lower() == qNorm for r in results)

    return JsonResponse({'results': results[:15], 'exact_match': exact_match})


@guerite_required
@require_POST
def creer_demandeur_ajax(request):
    """
    Crée réellement un nouveau Demandeur en base à partir du nom tapé
    dans l'autocomplétion, lorsqu'aucune correspondance n'a été
    trouvée parmi Client / Employé / Demandeur.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'error': "Requête invalide."}, status=400)

    nom = (data.get('nom') or '').strip()
    numero = (data.get('numero') or '').strip()
    description = (data.get('description') or '').strip()

    if not nom:
        return JsonResponse({'success': False, 'error': "Le nom est obligatoire."}, status=400)
    if not numero:
        return JsonResponse({'success': False, 'error': "Le numéro est obligatoire."}, status=400)

    if Demandeur.objects.filter(numero=numero).exists():
        return JsonResponse({'success': False, 'error': "Ce numéro est déjà associé à un demandeur existant."}, status=400)

    demandeur = Demandeur.objects.create(
        nom=nom,
        numero=numero,
        description=description,
    )

    return JsonResponse({
        'success': True,
        'id': str(demandeur.id),
        'nom': demandeur.nom,
        'numero': demandeur.numero,
        'detail': demandeur.description or 'Demandeur',
    })




@receptionniste_required
def rec_conducteurs(request):

    q         = request.GET.get('q', '').strip()
    categorie = request.GET.get('categorie', '')

    if request.method == 'POST':
        action  = request.POST.get('action')
        cond_id = request.POST.get('cond_id', '').strip()
        if action == 'creer':
            nom, prenom, tel = request.POST.get('nom','').strip(), request.POST.get('prenom','').strip(), request.POST.get('telephone','').strip()
            if not all([nom, prenom, tel]):
                messages.error(request, "Nom, prénom et téléphone sont obligatoires.")
            elif Conducteur.objects.filter(telephone=tel).exists():
                messages.error(request, f"Un conducteur avec le téléphone {tel} existe déjà.")
            else:
                c = Conducteur.objects.create(
                    nom=nom, prenom=prenom, telephone=tel,
                    telephone2=request.POST.get('telephone2','').strip(),
                    cni=request.POST.get('cni','').strip(),
                    permis=request.POST.get('permis','').strip(),
                    categorie_permis=request.POST.get('categorie_permis','').strip(),
                    created_by=request.user,
                )
                log_action(request, ActionType.CREATION, 'ADMIN', c)
                messages.success(request, f"Conducteur {c.prenom} {c.nom} créé.")
        elif action == 'modifier' and cond_id:
            c   = get_object_or_404(Conducteur, id=cond_id)
            nom = request.POST.get('nom','').strip()
            tel = request.POST.get('telephone','').strip()
            if not nom or not tel:
                messages.error(request, "Nom et téléphone sont obligatoires.")
            else:
                c.nom=nom; c.prenom=request.POST.get('prenom','').strip()
                c.telephone=tel; c.telephone2=request.POST.get('telephone2','').strip()
                c.cni=request.POST.get('cni','').strip()
                c.permis=request.POST.get('permis','').strip()
                c.categorie_permis=request.POST.get('categorie_permis','').strip()
                c.save()
                log_action(request, ActionType.MODIFICATION, 'ADMIN', c)
                messages.success(request, f"Conducteur {c.prenom} {c.nom} mis à jour.")
        return redirect('rec_conducteurs')

    qs = Conducteur.objects.all()
    if q:
        qs = qs.filter(Q(nom__icontains=q)|Q(prenom__icontains=q)|Q(telephone__icontains=q)|Q(cni__icontains=q)|Q(permis__icontains=q))
    if categorie:
        qs = qs.filter(categorie_permis__icontains=categorie)

    conducteurs = []
    for c in qs[:100]:
        c.nb_passages     = EnregistrementEntree.objects.filter(conducteur=c).count()
        c.dernier_passage = EnregistrementEntree.objects.filter(conducteur=c).select_related('vehicule').order_by('-date_entree').first()
        conducteurs.append(c)

    categories = list(Conducteur.objects.exclude(categorie_permis='').exclude(categorie_permis__isnull=True)
        .values_list('categorie_permis', flat=True).distinct().order_by('categorie_permis'))

    return render(request, 'reception/conducteurs.html', {
        'conducteurs': conducteurs, 'nb_total': Conducteur.objects.count(),
        'categories': categories, 'filters': {'q': q, 'categorie': categorie},
    })





@receptionniste_required
def rec_vehicules(request):
 
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
 
    return render(request, 'reception/vehicules/liste.html', {
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
 
 
@receptionniste_required
def rec_mouvements_vehicule(request, vehicule_id):
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

@receptionniste_required
def rec_modifier_vehicule(request, vehicule_id):
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
        return render(request, 'reception/vehicules/modifier.html', {
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
        log_action(request, ActionType.MODIFICATION, 'RECEPTIONNISTE', v)
        messages.success(request, f"Véhicule {v.immatriculation} mis à jour.")
        return redirect('rec_vehicules')

    return render_form()




 
 # ════════════════════════════════════════════════════════
 #  CLIENTS
 # ════════════════════════════════════════════════════════
  
@receptionniste_required
def rec_clients(request):
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
  
     return render(request, 'reception/clients/liste.html', {
         'clients':     clients_list,
         'stats':       stats,
         'villes':      villes,
         'filtre_type': filtre_type,
         'filters':     {'q': q, 'ville': ville, 'avec_vehicule': avec_vehicule},
     })
  
  
@receptionniste_required
def rec_detail_client(request, client_id):

  
     c = get_object_or_404(
         Client.objects.prefetch_related(
             'vehicules', 'vehicules__entrees', 'vehicules__ordres_reparation'
         ),
         id=client_id
     )
     entrees = EnregistrementEntree.objects.filter(
         vehicule__client=c
     ).select_related('vehicule').order_by('-date_entree')[:30]
  
     return render(request, 'reception/clients/detail.html', {
         'client': c, 'entrees': entrees,
     })
  
  
@receptionniste_required
def rec_modifier_client(request, client_id):
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
         log_action(request, ActionType.MODIFICATION, 'RECEPTION', c)
         messages.success(request, f"Client {c} mis à jour.")
         return redirect('rec_clients')
  
     return render(request, 'reception/clients/modifier.html', {'c': c})
  



@receptionniste_required
def export_client_pdf(request):
    qs = Client.objects.annotate(
        nb_vehicules=Count('vehicules', distinct=True),
        nb_passages=Count('vehicules__entrees', distinct=True),
    ).order_by('nom')

    # ── Filtres (mêmes que la liste) ──
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) |
            Q(prenom__icontains=q) |
            Q(telephone__icontains=q) |
            Q(email__icontains=q) |
            Q(ninea__icontains=q) |
            Q(ville__icontains=q) |
            Q(numero_client__icontains=q)
        )

    type_client = request.GET.get('type', '').strip()
    if type_client and type_client != 'tous':
        qs = qs.filter(type_client=type_client)

    ville = request.GET.get('ville', '').strip()
    if ville:
        qs = qs.filter(ville=ville)

    avec_vehicule = request.GET.get('avec_vehicule', '').strip()
    if avec_vehicule == '1':
        qs = qs.filter(nb_vehicules__gt=0)
    elif avec_vehicule == '0':
        qs = qs.filter(nb_vehicules=0)

    pdf_bytes = generer_pdf_liste_clients(qs)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="clients.pdf"'
    return response



@receptionniste_required
def export_vehicules_pdf(request):
    from django.utils import timezone
    today = timezone.localdate()

    qs = (
        Vehicule.objects
        .select_related('client')
        .annotate(nb_passages=Count('entrees'))
        .order_by('immatriculation')
    )

    # ── Recherche ──
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(immatriculation__icontains=q) |
            Q(marque__icontains=q) |
            Q(modele__icontains=q) |
            Q(numero_chassis__icontains=q) |
            Q(client__nom__icontains=q) |
            Q(client__telephone__icontains=q)
        )

    # ── Présence ──
    presence = request.GET.get('presence', '').strip()
    if presence == 'presents':
        qs = qs.filter(en_local=True)
    elif presence == 'atelier':
        qs = qs.filter(en_atelier=True)
    elif presence == 'libres':
        qs = qs.filter(en_local=False, en_atelier=False)

    # ── Carburant ──
    carburant = request.GET.get('carburant', '').strip()
    if carburant:
        qs = qs.filter(type_carburant=carburant)

    # ── Type propriétaire ──
    type_client = request.GET.get('type_client', '').strip()
    if type_client:
        qs = qs.filter(client__type_client=type_client)

    # ── Assurance ──
    assurance = request.GET.get('assurance', '').strip()
    if assurance == 'expiree':
        qs = qs.filter(expiry_assurance__lt=today)
    elif assurance == 'valide':
        qs = qs.filter(expiry_assurance__gte=today)

    pdf_bytes = generer_pdf_liste_vehicules(qs, today)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="vehicules.pdf"'
    return response