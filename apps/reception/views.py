"""
Vues Réception — sans devis, sans facture
"""
from decimal import Decimal
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse

from .models import Reception, StatutVehicule, RapportReception, TransfertAtelier, Notification
from .forms import ReceptionForm, RapportReceptionForm, TransfertAtelierForm, BonSortieForm, ORReceptionForm
from apps.guerite.models import EnregistrementEntree, BonSortie, StatutEntree, MotifEntree, StatutViewHinstorisue
from apps.atelier.models import FicheTechnique, OrdreReparation, StatutOR, TypeOR, FicheControle, Tache, StatutTache
from apps.vehicules.models import Vehicule
from apps.accounts.decorators import guerite_required, receptionniste_required
from apps.accounts.models import Role
from apps.audit.service import log_action
from apps.audit.models import ActionType
from apps.documents.pdf_generator import generer_pdf_bon_sortie
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile

# ─── Utilitaire notif ────────────────────────────────────────────────────────
def _notifier(type_notif, titre, message, reception=None):
    from apps.accounts.models import User
    for user in User.objects.filter(role=Role.RECEPTIONNISTE, is_active=True):
        Notification.objects.create(
            type_notif=type_notif, titre=titre, message=message,
            reception=reception, destinataire=user
        )


# ─── DASHBOARD ───────────────────────────────────────────────────────────────
@receptionniste_required
def dashboard(request):
    # Tous les véhicules présents pour réparation (guérite)
    entrees = EnregistrementEntree.objects.exclude(
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
    ).select_related('reception')[:20]

    # OR actifs liés aux réceptions
    or_actifs = OrdreReparation.objects.filter(
        statut__in=[StatutOR.OUVERT, StatutOR.EN_COURS, StatutOR.REOUVERT],
        reception__in=receptions
    ).select_related('vehicule', 'atelier').order_by('-date_creation')
    aujourd_hui = timezone.now().date()
    entrees_today = EnregistrementEntree.objects.filter(date_entree__date=aujourd_hui)


    ctx = {
        'entrees':            entrees,
        'entrees_sans_rec':   entrees.filter(reception__isnull=True),
        'receptions':         receptions,
        'notifs':             notifs,
        'nb_notifs':          notifs.count(),
        'or_actifs':          or_actifs,
        'vehicules_presents': EnregistrementEntree.objects.exclude(statut=StatutEntree.SORTI).select_related(
            'vehicule', 'vehicule__client', 'conducteur'
        ).order_by('-date_entree')[:20],
        'entrees_recentes':   entrees_today.select_related('vehicule', 'conducteur').order_by('-date_entree')[:10],

        # Compteurs KPI
        'nb_a_traiter':       entrees.filter(reception__isnull=True).count(),
        'nb_en_atelier':      receptions.filter(statut=StatutVehicule.EN_ATELIER).count(),
        'nb_presents':        receptions.filter(statut=StatutVehicule.PRESENT_ATELIER).count(),
        'nb_termines':        receptions.filter(statut=StatutVehicule.TRAVAUX_TERMINES).count(),

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
    entree_id = request.GET.get('entree_id')
    entree = None
    if entree_id:
        entree = get_object_or_404(
            EnregistrementEntree,
            id=entree_id, motif=MotifEntree.REPARATION, statut=StatutEntree.EN_COURS
        )
        if hasattr(entree, 'reception'):
            messages.warning(request, "Cette entrée a déjà une réception.")
            return redirect('detail_reception', rec_id=entree.reception.id)

    entrees_dispo = EnregistrementEntree.objects.filter(
        motif=MotifEntree.REPARATION,
        statut=StatutEntree.EN_COURS,
        reception__isnull=True
    ).select_related('vehicule', 'vehicule__client').order_by('-date_entree')

    # Initialisation du formulaire (peut rester vide)
    form = ReceptionForm()

    if request.method == 'POST':
        action = request.POST.get('action')  # 'controle' ou 'transfert'
        eid = request.POST.get('entree_id') or (str(entree.id) if entree else None)
        if not eid:
            messages.error(request, "Sélectionnez une entrée.")
            return redirect('creer_reception')

        ent = get_object_or_404(EnregistrementEntree, id=eid)

        if action == 'controle':
            # Récupération des champs du contrôle
            diagnostic = request.POST.get('diagnostic', '').strip()
            pieces_rec = request.POST.get('pieces_recommandees', '').strip()
            temps_estime = request.POST.get('temps_estime', '0')
            try:
                temps_estime = Decimal(temps_estime)
            except:
                temps_estime = Decimal('0')

            if not diagnostic:
                messages.error(request, "Le diagnostic est obligatoire pour créer un bon de sortie.")
                return redirect('creer_reception')
                    
            FicheTechnique.objects.create(
                diagnostic=diagnostic,
                entre_id= ent,
                pieces_recommandees=pieces_rec,
                temps_estime_heures=temps_estime,
                cree_par=request.user
            )
            messages.success(request, f"fiche technique créées. Vous pouvez maintenant créer le bon de sortie.")
            # Rediriger vers la création du bon de sortie (ou vers la fiche)
            return redirect('creer_bon_sortie_rec', rec_id=ent.id)

        elif action == 'transfert': 
            # Comportement actuel : simple création de réception
            form = ReceptionForm(request.POST)
            if form.is_valid():
                rec = form.save(commit=False)
                rec.entree = ent
                rec.vehicule = ent.vehicule
                rec.receptionniste = request.user
                rec.save()
                log_action(request, ActionType.CREATION, 'RECEPTION', rec)
                messages.success(request, f"Réception {rec.numero} créée et transférée à l'atelier.")
                return redirect('detail_reception', rec_id=rec.id)
            else:
                messages.error(request, "Erreur dans le formulaire. Vérifiez les champs.")

    return render(request, 'reception/creer_reception.html', {
        'form': form,
        'entree': entree,
        'entrees_dispo': entrees_dispo,
    })



@guerite_required 
def historique_entrees(request):
    entrees = get_filtered_entrees(request)
    return render(request, 'reception/historique.html', {
        'entrees': entrees[:100],
        'statuts': StatutViewHinstorisue.choices,
        'motifs': MotifEntree.choices,
    })

def get_filtered_entrees(request):
    entrees = EnregistrementEntree.objects.select_related(
        'vehicule', 'vehicule__client', 'conducteur', 'agent_entree'
    ).order_by('-date_entree')

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
    if request.method == 'POST':
        bon.signature_client = request.POST.get('signature_client', '')
        bon.est_valide       = True
        bon.valide_par       = request.user
        bon.date_validation  = timezone.now()
        bon.save()
        if bon.reception:
            bon.reception.statut = StatutVehicule.BON_SORTIE_FAIT
            bon.reception.save(update_fields=['statut'])
        messages.success(request, f"Bon {bon.numero} validé et signé.")
    return render(request, 'reception/detail_bon_sortie.html', {'bon': bon})

 
@receptionniste_required
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
    from django.db.models import Q, Count
    from django.utils import timezone
    from datetime import timedelta
 
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

    super_receptionniste = request.user.role == Role.SUPER_RECEPTIONNISTE

    return render(
        request,
        'reception/bons_sortie_detail.html',
        {
            'bon': bon,
            'super': super_receptionniste
        }
    )
 
# ─── VALIDER BON DE SORTIE ────────────────────────────────────────────────────
@guerite_required
def valider_bon_sortie_guerite(request, bon_id):
    bon = get_object_or_404(BonSortie, id=bon_id)
    if request.method == 'POST':
        bon.etats          = 'VALIDER'
        bon.est_valide     = True
        bon.valide_par     = request.user
        bon.date_validation = timezone.now()
        bon.save()
        log_action(request, ActionType.CHANGEMENT_STATUT, 'GUERITE', bon, {'etat': 'VALIDER'})
        messages.success(request, f"Bon {bon.numero} validé.")
    return redirect('liste_bons_sortie')
 
 
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
 

# ─── CRÉER BON DIRECT (sans réception) ───────────────────────────────────────




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

            bon = form.save(commit=False)
            bon.cree_par = request.user
            bon.types = 'VEHICULE'

            if rec.vehicule:
                bon.vehicule = rec.vehicule
            bon.save()

            _gen_qr(bon)

            rec.statut = StatutVehicule.BON_SORTIE_FAIT
            rec.save(update_fields=['statut'])

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

        if rec is not None:
            rec.statut = StatutVehicule.BON_SORTIE_FAIT
            rec.save(update_fields=['statut'])

        # Création du bon de sortie
        bon = BonSortie.objects.create(
            types='VEHICULE',
            vehicule=vehicule,
            nom_demandeur=nom_demandeur,
            observations=observations,
            cree_par=request.user,
            # Si d'autres champs existent (Origine_demande, etc.), les ajouter ici
        )

        # Cohérence avec creer_bon_sortie : génération du QR code
        _gen_qr(bon)

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
    entrees = EnregistrementEntree.objects.exclude(
        statut=StatutEntree.SORTI          # exclut les sortis → reste les présents
    ).select_related('vehicule', 'vehicule__client', 'conducteur').order_by('-date_entree')
    return render(request, 'reception/vehicules_presents_rec.html', {'entrees': entrees})

 
@guerite_required
def creer_bon_sortie_divers(request):
    """Page dédiée à la création d'un bon de sortie divers (version ultra simplifiée)."""
    from apps.accounts.models import User
    from django.utils import timezone

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
            log_action(request, ActionType.CREATION, 'GUERITE', bon, {'type': 'DIVERS'})
            messages.success(request, f"Bon de sortie {bon.numero} créé avec succès.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    return render(request, 'reception/creer_divers.html', {
        'employes': employes,
    })