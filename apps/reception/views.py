"""
Vues Réception — sans devis, sans facture
"""

from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
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
from apps.notifications.hook import notifier_bon_sortie_cree
from .models import Reception, StatutVehicule, RapportReception, TransfertAtelier, Notification
from .forms import ReceptionForm, RapportReceptionForm, TransfertAtelierForm, BonSortieForm, ORReceptionForm
from apps.guerite.models import EnregistrementEntree, BonSortie, StatutEntree, MotifEntree, StatutViewHinstorisue, TypeBon
from apps.atelier.models import FicheTechnique, OrdreReparation, StatutOR, TypeOR, FicheControle, Tache, StatutTache
from apps.vehicules.models import Client, Vehicule
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

# ─── Utilitaire notif ────────────────────────────────────────────────────────
def _notifier(type_notif, titre, message, reception=None):
    from apps.accounts.models import User
    for user in User.objects.filter(role=Role.RECEPTIONNISTE, is_active=True):
        Notification.objects.create(
            type_notif=type_notif, titre=titre, message=message,
            reception=reception, destinataire=user
        )


def get_entrees_presentes_filtrees(request):
    qs = (
        EnregistrementEntree.objects
        .select_related("vehicule", "vehicule__client", "conducteur", "conducteur__client")
        .filter(date_sortie__isnull=True)
        .order_by("-date_entree")
    )

    q            = request.GET.get("q")
    motif        = request.GET.get("motif")
    date_debut   = request.GET.get("date_debut", "").strip()
    date_fin     = request.GET.get("date_fin", "").strip()
    duree_valeur = request.GET.get("duree_valeur", "").strip()
    duree_unite  = request.GET.get("duree_unite", "h").strip() or "h"

    # ── Recherche libre ──────────────────────────
    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
            | Q(vehicule__client__telephone__icontains=q)
            | Q(conducteur__nom__icontains=q)
        )

    # ── Motif ────────────────────────────────────
    if motif:
        qs = qs.filter(motif=motif)

    # ── Dates ────────────────────────────────────
    if date_debut:
        dt = datetime.strptime(date_debut, "%Y-%m-%d")
        qs = qs.filter(date_entree__gte=timezone.make_aware(dt))

    if date_fin:
        dt = datetime.strptime(date_fin, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59
        )
        qs = qs.filter(date_entree__lte=timezone.make_aware(dt))

    # ── Durée de séjour (moins de n unités) ──────
    if duree_valeur != "":
        try:
            n = int(duree_valeur)

            if duree_unite == "h":
                unite_delta = timedelta(hours=1)
            elif duree_unite == "m":
                unite_delta = timedelta(days=30)
            else:  # "j"
                unite_delta = timedelta(days=1)

            if n == 0:
                # 0 → moins de 1 unité
                n = 1

            if n > 0:
                delta = unite_delta * n
                seuil = timezone.now() - delta
                # date_entree > seuil  ⇒  séjour < n unités
                qs = qs.filter(date_entree__gt=seuil)

        except (ValueError, TypeError):
            pass

    return qs

 
# ─── DASHBOARD ───────────────────────────────────────────────────────────────
@receptionniste_required 
def dashboard(request):
    # Tous les véhicules présents pour réparation (guérite)
    entreesReparation = EnregistrementEntree.objects.exclude(
    motif=MotifEntree.VISITE
    ).exclude(
    statut=StatutEntree.SORTI
    ).select_related('vehicule', 'vehicule__client').order_by('-date_entree')

    # Réceptions actives (pas encore sorties)
    receptions = Reception.objects.exclude(
        statut__in=[StatutVehicule.SORTI]
    ).select_related('vehicule', 'vehicule__client').prefetch_related(
        'transferts__atelier'
    ).order_by('-created_at')

    # Notifications non lues
    notifs = Notification.objects.filter(
        destinataire=request.user, lue=False
    ).select_related('reception')[:15]

    # OR actifs liés aux réceptions
    or_actifs = OrdreReparation.objects.filter(
        statut__in=[StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT],
        reception__in=receptions
    ).select_related('vehicule', 'atelier').order_by('-date_creation')
    aujourd_hui = timezone.now().date()
    entrees_today = EnregistrementEntree.objects.filter(date_entree__date=aujourd_hui)
    sortie_today = EnregistrementEntree.objects.filter(date_sortie__date=aujourd_hui)
    entrees = (
           EnregistrementEntree.objects
           .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
           .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
           .order_by(F('date_tri').desc())
           )
    ctx = {
        'nb_entrees_today': entrees_today.count(),
        'nb_sorties_today': sortie_today.count(),
        'entrees':            entreesReparation[:5],
        'entrees_sans_rec':   entreesReparation.filter(reception__isnull=True),
        'receptions':         receptions,
        'notifs':             notifs,
        'nb_notifs':          notifs.count(),
        'or_actifs':          or_actifs,
        'vehicules_presents': EnregistrementEntree.objects.exclude(statut=StatutEntree.SORTI).select_related(
            'vehicule', 'vehicule__client', 'conducteur'
        ).order_by('-date_entree')[:7],
        'entrees_recentes':   entrees[:9],

        # Compteurs KPI
        'nb_a_traiter':       entreesReparation.filter(reception__isnull=True).count(),
        'nb_en_atelier':      receptions.filter(statut=StatutVehicule.EN_ATELIER).count(),
        'nb_presents':        receptions.filter(statut=StatutVehicule.PRESENT_ATELIER).count(),
        'nb_termines':        receptions.filter(statut=StatutVehicule.TRAVAUX_TERMINES).count(),
        'entreesNbr' : get_entrees_presentes_filtrees(request),

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
    return render(request, 'reception/liste_receptions.html', {
        'receptions': qs[:100],
        'statuts':    StatutVehicule.choices,
        'statut_filter': statut,
    })






@receptionniste_required
def creer_reception(request):
    from apps.guerite.models import EnregistrementEntree, StatutEntree, MotifEntree
    from apps.vehicules.models import Vehicule
 
    entree_id = request.GET.get('entree_id')
    entree = None
    if entree_id:
        entree = get_object_or_404(
            EnregistrementEntree,
            id=entree_id,
            motif=MotifEntree.REPARATION,
            statut=StatutEntree.EN_COURS,
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
 
        error = None
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
 
        rec = Reception.objects.create(
            entree         = entree,
            vehicule       = vehicule,
            statut         = StatutVehicule.RAPPORT_FAIT,
            receptionniste = request.user,
            observations   = observations,
        )
        log_action(request, ActionType.CREATION, 'RECEPTION', rec, {'decision': decision})
        messages.success(request, f"Réception {rec.numero} créée.")
 
        if decision == 'SORTIE_DIRECTE':
            messages.info(request, "Sortie directe — créez le bon de sortie.")
            return redirect('creer_bon_sortie_rec', rec_id=rec.id)
 
        return redirect('creer_or_rec', rec_id=rec.id)
 
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
    entrees = get_filtered_entrees(request)
    return render(request, 'reception/historique.html', {
        'entrees': entrees[:100],
        'statuts': StatutViewHinstorisue.choices,
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
    rapport      = getattr(rec, 'rapport', None)
    or_list      = OrdreReparation.objects.filter(reception=rec).select_related(
        'atelier'
    ).prefetch_related('taches').order_by('-date_creation')
    bon_sortie   = BonSortie.objects.filter(vehicule=rec.vehicule, reception=rec).first()
    fiche_controle = None
    for o in or_list:
        fc = getattr(o, 'fiche_controle', None)
        if fc:
            fiche_controle = fc
            break

    return render(request, 'reception/detail_reception.html', {
        'rec': rec, 'rapport': rapport,
        'or_list': or_list, 'bon_sortie': bon_sortie,
        'fiche_controle': fiche_controle,
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


# ─── OR depuis RÉCEPTION ──────────────────────────────────────────────────────
@receptionniste_required
def creer_or(request, rec_id):
    rec  = get_object_or_404(Reception, id=rec_id)
    form = ORReceptionForm()
    if request.method == 'POST':
        form = ORReceptionForm(request.POST)
        if form.is_valid():
            o                      = form.save(commit=False)
            o.vehicule             = rec.vehicule
            o.reception            = rec
            o.responsable_atelier  = request.user
            o.created_by           = request.user
            o.save()
            if rec.statut == StatutVehicule.EN_COURS:
                rec.statut = StatutVehicule.EN_ATELIER
                rec.save(update_fields=['statut'])
            log_action(request, ActionType.CREATION, 'RECEPTION', o)
            messages.success(request, f"OR {o.numero} créé.")
            return redirect('detail_reception', rec_id=rec.id)
    return render(request, 'reception/creer_or.html', {'form': form, 'rec': rec})


@receptionniste_required
def cloture_or(request, or_id):
    o = get_object_or_404(OrdreReparation, id=or_id)
    if request.method == 'POST':
        total = o.taches.aggregate(t=Sum('duree_reelle_minutes'))['t'] or 0
        o.duree_totale_minutes = total
        o.statut               = StatutOR.CLOTURE
        o.date_cloture         = timezone.now()
        o.save()
        if o.reception:
            o.reception.statut = StatutVehicule.TRAVAUX_TERMINES
            o.reception.save(update_fields=['statut'])
            _notifier('OR_CLOTURE',
                      f"OR {o.numero} clôturé",
                      f"Travaux terminés sur {o.vehicule.immatriculation}.",
                      o.reception)
        log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', o, {'statut': 'CLOTURE'})
        messages.success(request, f"OR {o.numero} clôturé.")
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
            o.reception.statut = StatutVehicule.TRAVAUX_EN_COURS
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
 
    return render(request, 'reception/bons_sortie_liste.html', {
        'bons':    qs[:50],
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
    rec = get_object_or_404(
        EnregistrementEntree,
        id=rec_id
    )
    rapport = getattr(rec, 'rapport', None)

    vehicules_presents = EnregistrementEntree.objects.exclude(
        statut=StatutEntree.SORTI   # adapte selon ton modèle
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

    if request.method == 'POST':
        form = BonSortieForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                bon = form.save(commit=False)
                bon.cree_par = request.user
                bon.types = TypeBon.VEHICULE
                if rec.vehicule:
                    bon.vehicule = rec.vehicule
                bon.save()


            bon.save()

            _gen_qr(bon)
            rec.bon_sortie = bon
            rec.save(update_fields=['bon_sortie'])


            est_admin = request.user.role == Role.ADMIN
            if not est_admin:
                notifier_bon_sortie_cree(bon)
            log_action(
                request,
                ActionType.CREATION,
                'RECEPTION',
                bon
            )

            messages.success(
                request,
                f"Bon de sortie {bon.numero} créé."
            )

            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    else:
        form = BonSortieForm()
    return render(request, 'reception/creer_bon_sortie.html', {
        'form': form,
        'rec': rec,
        'reception': rec,
        'vehicles_data': vehicles_data,
        'vehicles_json': json.dumps(vehicles_data, cls=DjangoJSONEncoder),
        'sortie_directe': (
            rapport and rapport.decision == 'SORTIE_DIRECTE'
        ),
    })


def autocomplete_vehicules_presents(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    # BUG CORRIGÉ : on filtre sur l'immatriculation (filter, pas exclude)
    # et on exclut séparément les véhicules déjà sortis.
   
    entrees = EnregistrementEntree.objects.filter(
        vehicule__immatriculation__icontains=q,
        motif=MotifEntree.REPARATION
    ).exclude(
        statut__in=[StatutEntree.SORTI, StatutVehicule.BON_SORTIE_FAIT]
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



@guerite_required
def liste_vehicules_presents(request):
    entrees = get_entrees_presentes_filtrees(request)
    return render(request, 'reception/vehicules_presents_rec.html', {'entrees': entrees, 'motifs': MotifEntree.choices})


 
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