"""
Vues Guérite - Entrées/Sorties véhicules
"""
import base64
import json
import os
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import log, timezone
from django.db.models import  F, Count, When
from django.views.decorators.http import require_POST
import os
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.db.models.functions import Coalesce
from apps import reception
from apps.accounts.choices import StatutVehicule,  EtatBon, StatutVehicule, MotifEntree
from apps.notifications.hook import notifier_sortie_vehicule
from .models import EnregistrementEntree, BonSortie
from .forms import RechercheVehiculeForm, VehiculeForm, ClientForm, ConducteurForm, EntreeForm, SortieForm
from apps.vehicules.models import Marque, Modele, Vehicule, Client, Conducteur
from apps.accounts.decorators import guerite_required 
from apps.audit.service import log_action
from apps.audit.models import ActionType
from itertools import chain
from ..reception.views import dashboard as reception_dashboard, save_signature_from_dataurl
from django.http import Http404, JsonResponse

from django.http import HttpResponse
from django.db.models import Case, IntegerField, Q, Value
import datetime
from datetime import datetime


 
@guerite_required
def dashboard(request):
    # 👉 si réceptionniste → appeler autre view
    if request.user.role == 'RECEPTIONNISTE':
        return reception_dashboard(request)

    aujourd_hui = timezone.now().date()
    entrees_today = EnregistrementEntree.objects.filter(
        date_entree__date=aujourd_hui
    )
    sorties_today = EnregistrementEntree.objects.filter(
            date_sortie__date=aujourd_hui
        )
    LIMITE = 7
    # Requête avec tri prioritaire (Bon de sortie fait OU Visite) + limite à 7
    vehicules_presents = (
    EnregistrementEntree.objects
    .exclude(statut=StatutVehicule.SORTI)
    .annotate(
        priorite=Case(
            When(
                Q(bon_sortie__etats='APPROBATION') | Q(motif=MotifEntree.VISITE),
                then=Value(0),
            ),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    .select_related(
        'vehicule', 'vehicule__client', 
        'conducteur', 'conducteur__client',
    )
    .order_by('priorite', '-date_entree')[:LIMITE]
    ) 

    entrees = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
        .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
        .order_by(F('date_tri').desc())
    )
    ctx = {
        'nb_entrees_today': entrees_today.count(),
        'nb_sorties_today': sorties_today.count(),
        'entrees' : get_entrees_presentes_filtrees(request),
        'vehicules_presents': vehicules_presents,
        'entrees_recentes': entrees[:9],
    }

    return render(request, 'guerite/dashboard.html', ctx)


@guerite_required
def recherche_vehicule(request):
    form = RechercheVehiculeForm(request.GET or None)
 
    vehicules = []
    query = request.GET.get('q', '').strip()

    if query:
        vehicules = Vehicule.objects.filter(
            Q(immatriculation__icontains=query) |
            Q(marque__icontains=query) |
            Q(modele__icontains=query) |
            Q(client__nom__icontains=query) |
            Q(client__prenom__icontains=query) |
            Q(numero_chassis__icontains=query)
        ).select_related('client').order_by('immatriculation')[:20]

# .exclude(
            # 👉 EXCLURE ceux qui sont EN_COURS
           #  entrees__statut=StatutVehicule.EN_COURS  )

    return render(request, 'guerite/recherche_vehicule.html', {
        'form': form,
        'vehicules': vehicules,
        'query': query
    })


@guerite_required
def nouvelle_entree(request):
    """Étape 1: choisir un véhicule existant ou en créer un."""
    vehicule_id = request.GET.get('vehicule_id')
    vehicule = None
    if vehicule_id:
        vehicule = get_object_or_404(Vehicule, id=vehicule_id)
    return render(request, 'guerite/entree/choix.html', {'vehicule': vehicule})



PHOTO_FIELDS = ['photo1', 'photo2', 'photo3']  # ⚠️ adapte si tes champs s'appellent autrement

@guerite_required
def modifier_vehicule(request, vehicule_id=None):
    """
    Sans vehicule_id  -> affiche uniquement l'étape 1 (recherche par matricule).
    Avec vehicule_id  -> affiche le formulaire prérempli, et traite le POST.
    """
    vehicule = None
    if vehicule_id:
        vehicule = get_object_or_404(Vehicule, pk=vehicule_id)

    def get_photo_urls(v):
        urls = []
        if v and v.photos:
            for path in v.photos.split(';'):
                path = path.strip()
                if path:
                    try:
                        urls.append(default_storage.url(path))
                    except Exception:
                        urls.append('')
        while len(urls) < 3:
            urls.append('')
        return urls

    if request.method == 'POST':
        if not vehicule:
            return redirect('modifier_vehicule_recherche')

        form = VehiculeForm(request.POST, request.FILES, instance=vehicule)
        if form.is_valid():
            v = form.save(commit=False)

            client_id = request.POST.get('client')
            if client_id:
                v.client_id = client_id

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
            log_action(request, ActionType.MODIFICATION, 'GUERITE', v)
            messages.success(request, f"Véhicule {v.immatriculation} mis à jour avec succès.")
            return redirect('modifier_vehicule', vehicule_id=v.id)
    else:
        form = VehiculeForm(instance=vehicule) if vehicule else VehiculeForm()

    return render(request, 'guerite/modifier_vehicule.html', {
        'form': form,
        'vehicule': vehicule,
        'photo_urls': get_photo_urls(vehicule),
    })


def modifier_vehicule_recherche(request):
    """Vue "étape 1 seule" — pratique pour le lien '🔎 Changer de véhicule'."""
    return render(request, 'guerite/modifier_vehicule.html', {
        'form': VehiculeForm(),
        'vehicule': None,
    })


def autocomplete_vehicules(request):
    """Recherche de véhicules par immatriculation, pour l'étape 1 du formulaire."""
    q = request.GET.get('q', '').strip()
    results = []
    if len(q) >= 2:
        qs = (
            Vehicule.objects
            .filter(immatriculation__icontains=q)
            .select_related('client')
            .order_by('immatriculation')[:10]
        )
        results = [
            {
                'id': v.id,
                'immatriculation': v.immatriculation,
                'marque': v.marque,
                'modele': v.modele,
                'client': str(v.client) if v.client else '',
            }
            for v in qs
        ]
    return JsonResponse({'results': results})


# ─── AJAX: Autocomplete conducteurs ──────────────────────────────────────────



def autocomplete_inventaires(request):
    """
    Autocomplete des chauffeurs / conducteurs.
    Recherche sur nom, prenom, téléphone, société.
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    qs = (
        Conducteur.objects
        .filter(
            Q(nom__icontains=q) |
            Q(prenom__icontains=q) |
            Q(telephone__icontains=q)
        )
        .order_by('nom', 'prenom')[:15]
    )

    results = []
    for c in qs:
        label = f"{c.prenom} {c.nom}".strip() or str(c)
        results.append({
            'id':        str(c.id),
            'nom':       c.nom or '',
            'prenom':    c.prenom or '',
            'label':     label,
            'telephone': getattr(c, 'telephone', '') or '',
        })

    return JsonResponse({'results': results})

@login_required
def autocomplete_conducteurs(request):
    q = request.GET.get('q', '').strip()
    results = []

    # 1. Recherche prioritaire dans la table Conducteur
    qs_conducteurs = Conducteur.objects.all()
    if q:
        qs_conducteurs = qs_conducteurs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) |
            Q(telephone__icontains=q) | Q(cni__icontains=q) |
            Q(permis__icontains=q)
        )

    for c in qs_conducteurs[:10]:
        nom = f"{c.prenom} {c.nom}".strip()
        detail_parts = []
        if c.telephone:
            detail_parts.append(c.telephone)
        if c.permis:
            detail_parts.append(f"Permis: {c.permis}")
        if c.categorie_permis:
            detail_parts.append(f"Cat. {c.categorie_permis}")

        results.append({
            'id': str(c.id),
            'nom': nom,
            'detail': ' — '.join(detail_parts),
            'is_client': False,
        })

    # 2. Si moins de 10 résultats, recherche complémentaire dans les Clients Particuliers
    limit_restante = 10 - len(results)
    if limit_restante > 0:
        # Ajustez 'type_client' ou 'type' selon le champ exact de votre modèle Client
        qs_clients = Client.objects.filter(is_active=True, type_client='PARTICULIER')

        if q:
            qs_clients = qs_clients.filter(
                Q(nom__icontains=q) | Q(prenom__icontains=q) |
                Q(telephone__icontains=q) 
            )

        for client in qs_clients[:limit_restante]:
            nom = f"{getattr(client, 'prenom', '')} {getattr(client, 'nom', '')}".strip()
            detail_parts = ["Client Particulier (À créer)"]
            
            if getattr(client, 'telephone', None):
                detail_parts.append(client.telephone)

            results.append({
                'id': f"client_{client.id}",  # Identifiant distinct pour le frontend
                'client_id': client.id,
                'nom': nom,
                'prenom': getattr(client, 'prenom', ''),
                'nom_famille': getattr(client, 'nom', ''),
                'telephone': getattr(client, 'telephone', ''),
                'cni': getattr(client, 'cni', ''),
                'detail': ' — '.join(detail_parts),
                'is_client': True,  # Flag indiquant au JS qu'il faut créer un conducteur
            })

    return JsonResponse({'results': results})


def autocomplete_clients(request):
    """Retourne la liste des clients filtrés pour l'autocomplete."""

    q    = request.GET.get('q', '').strip()
    type_client = request.GET.get('type', '')
    qs = Client.objects.filter(is_active=True)
    if type_client in ('PARTICULIER', 'ENTREPRISE'):
        qs = qs.filter(type_client=type_client)
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) 

        )
    results = []
    for c in qs[:10]:
        if c.type_client == 'PARTICULIER':
            detail = f"{c.telephone} — {c.ville or 'Particulier'}"
            nom = f"{c.prenom} {c.nom}".strip() if c.prenom else c.nom
        else:
            detail = f"{c.telephone} — Entreprise{' | ' + c.ninea if c.ninea else ''}"
            nom = c.nom
        results.append({'id': str(c.id), 'nom': nom, 'detail': detail})
    from django.http import JsonResponse
    return JsonResponse({'results': results})




@guerite_required 
def creer_client(request):
    form = ClientForm()
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            log_action(request, ActionType.CREATION, 'GUERITE', client)
            messages.success(request, f"Client {client} créé.")

        
    return render(request, 'guerite/entree/creer_client.html', {'form': form})



def creer_client_ajax(request):
    """Créer un client via appel AJAX depuis le formulaire véhicule."""
 
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})
 
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Données invalides'})
 
    type_client = data.get('type_client', 'PARTICULIER')
    nom         = data.get('nom', '').strip()
    telephone   = data.get('telephone', '').strip()
 
    if not nom or not telephone:
        return JsonResponse({'success': False, 'error': 'Nom et téléphone obligatoires'})
 
    if Client.objects.filter(telephone=telephone).exists():
        existing = Client.objects.get(telephone=telephone)
        return JsonResponse({
            'success': True,
            'id': str(existing.id),
            'nom': str(existing),
            'detail': f"{existing.telephone} — {existing.ville or ''}",
        })
 
    client = Client.objects.create(
        type_client = type_client,
        nom         = nom,
        prenom      = data.get('prenom', ''),
        nom_correspondant= data.get('nom_correspondant', ''),
        telephone   = telephone,
        telephone2  = data.get('telephone2', ''),
        email       = data.get('email', ''),
        adresse     = data.get('adresse', ''),
        ville       = data.get('ville', ''),
        ninea       = data.get('ninea', ''),
        created_by  = request.user,
    )
    log_action(request, ActionType.CREATION, 'GUERITE', client)
    return JsonResponse({
        'success': True,
        'id':     str(client.id),
        'nom':    str(client),
        'detail': f"{client.telephone} — {client.ville or type_client}",
    })




def autocomplete_marques(request):
    term = request.GET.get('q', '').strip()
    if len(term) < 2:
        return JsonResponse({'results': []})
    marques = Marque.objects.filter(nom__icontains=term)[:15]
    results = [{'id': m.id, 'nom': m.nom} for m in marques]
    return JsonResponse({'results': results})



def autocomplete_modeles(request):
    q = request.GET.get('q', '')
    marque = request.GET.get('marque', '')
    modeles = Modele.objects.filter(nom__icontains=q)
    if marque:
        modeles = modeles.filter(marque__nom__icontains=marque)
    modeles = modeles[:10]
    results = [{'nom': m.nom} for m in modeles]
    return JsonResponse({'results': results})



@login_required
@require_POST
def creer_conducteur_ajax(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données invalides.'}, status=400)

    nom = data.get('nom', '').strip()
    prenom = data.get('prenom', '').strip()
    telephone = data.get('telephone', '').strip()
    telephone2 = data.get('telephone2', '').strip()
    cni = data.get('cni', '').strip()
    permis = data.get('permis', '').strip()
    categorie_permis = data.get('categorie_permis', '').strip()
    client_id = data.get('client_id')

    if not nom or not telephone:
        return JsonResponse({'success': False, 'error': 'Le nom et le téléphone sont obligatoires.'})

    client = None
    if client_id:
        client = get_object_or_404(Client, id=client_id)

    conducteur = Conducteur.objects.create(
        nom=nom,
        prenom=prenom,
        telephone=telephone,
        telephone2=telephone2,
        cni=cni,
        permis=permis,
        categorie_permis=categorie_permis,
        client=client,
        created_by=request.user,
    )

    nom_complet = f"{conducteur.prenom} {conducteur.nom}".strip()
    detail_parts = []
    if conducteur.telephone:
        detail_parts.append(conducteur.telephone)
    if conducteur.permis:
        detail_parts.append(f"Permis: {conducteur.permis}")

    return JsonResponse({
        'success': True,
        'id': str(conducteur.id),
        'nom': nom_complet,
        'detail': ' — '.join(detail_parts),
    })


@guerite_required
def creer_conducteur(request):
    form = ConducteurForm()
    if request.method == 'POST':
        form = ConducteurForm(request.POST)
        if form.is_valid():
            conducteur = form.save(commit=False)
            conducteur.created_by = request.user
            conducteur.save()
            log_action(request, ActionType.CREATION, 'GUERITE', conducteur)
            messages.success(request, f"Conducteur {conducteur} créé.")
            return redirect(request.GET.get('next', 'nouvelle_entree'))
    return render(request, 'guerite/entree/creer_conducteur.html', {'form': form})


@guerite_required 
def creer_vehicule(request):
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

            modele, _ = Modele.objects.get_or_create(
                nom=modele_nom,
                marque=marque
            )

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
            return redirect(f"/guerite/entree/enregistrer/?vehicule_id={vehicule.id}")
        
    return render(request, 'guerite/entree/creer_vehicule.html', { 
        'form':             form,
        'client_id':        client_id,
        'client_preselect': client_preselect,
    })


@guerite_required
def enregistrer_entree(request):
    vehicule_id = request.GET.get('vehicule_id')
    vehicule = None
    if vehicule_id:
        vehicule = get_object_or_404(Vehicule, id=vehicule_id)

    initial = {'vehicule': vehicule} if vehicule else {}
    form = EntreeForm(initial=initial)

    if request.method == 'POST':
        form = EntreeForm(request.POST)
        if form.is_valid():
            entree = form.save(commit=False)
            entree.agent_entree = request.user
            entree.save()
            log_action(request, ActionType.CREATION, 'GUERITE', entree, {'motif': entree.motif})
            messages.success(request, f"Entrée {entree.numero} enregistrée avec succès !")
            return redirect('detail_entree', entree_id=entree.id)

    conducteurs = sorted(
    chain(
        Conducteur.objects.all(),
        Client.objects.all()
    ),
    key=lambda x: x.nom
)
    return render(request, 'guerite/entree/enregistrer.html', {
        'form': form, 'vehicule': vehicule, 'conducteurs': conducteurs
    })


@guerite_required
def detail_entree(request, entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree'),
        id=entree_id
    )
    return render(request, 'guerite/entree/detail.html', {'entree': entree})
 

@guerite_required
def modifier_motif_entree(request, entree_id):
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
        'GUERITE',
        entree,
        {'motif': entree.motif}
    )
    return redirect("detail_entree", entree_id=entree.id)




def get_entree_non_sortie(entree_id):
    entree = get_object_or_404(EnregistrementEntree, id=entree_id)
    if entree.statut == StatutVehicule.SORTI:
        raise Http404("Entrée déjà sortie")
    return entree

# Utilisation




@guerite_required
def enregistrer_sortie(request, entree_id):
    entree = get_entree_non_sortie(entree_id)
    reception = getattr(entree, 'reception', None)
    bon_sortie = None

    # Bon de sortie approuvé (hors visite)
    if entree.motif != MotifEntree.VISITE:
        bons = BonSortie.objects.filter(
            vehicule=entree.vehicule,
            etats=EtatBon.APPROBATION,
            est_valide=False,
        )
        if bons.exists():
            bon_sortie = bons.latest('created_at')

    form = SortieForm()

    if request.method == 'POST':
        form = SortieForm(request.POST)

        # Réparation / autre : un bon approuvé est obligatoire
        if entree.motif != MotifEntree.VISITE and not bon_sortie:
            messages.error(
                request,
                "Aucun bon de sortie valide trouvé. Contactez la réception.",
            )
            return render(request, 'guerite/sortie/enregistrer.html', {
                'entree': entree,
                'form': form,
                'bon_sortie': bon_sortie,
            })

        signature_data = request.POST.get('signature_client')

        if not signature_data:
            messages.error(request, "Le client doit signer avant de confirmer la sortie.")
            return render(request, 'guerite/sortie/enregistrer.html', {
                'entree': entree,
                'form': form,
                'bon_sortie': bon_sortie,
            })

        # ── Sortie de l'entrée ──
        entree.statut = StatutVehicule.SORTI
        entree.date_sortie = timezone.now()
        entree.agent_sortie = request.user

        # ── Bon de sortie ──
        if entree.motif != MotifEntree.VISITE and bon_sortie:
            if not save_signature_from_dataurl(bon_sortie, signature_data, 'signature_client'):
                messages.error(request, "Erreur lors de l'enregistrement de la signature.")
                return render(request, 'guerite/sortie/enregistrer.html', {
                    'entree': entree,
                    'form': form,
                    'bon_sortie': bon_sortie,
                })

            bon_sortie.est_valide = True
            bon_sortie.date_validation = timezone.now()
            bon_sortie.etats = EtatBon.VALIDER
            bon_sortie.save()
            entree.bon_sortie = bon_sortie

        # ── Réception associée ──
        if reception is not None:
            reception.statut = StatutVehicule.SORTI
            update_fields = ['statut']
            if hasattr(reception, 'date_sortie'):
                reception.date_sortie = timezone.now()
                update_fields.append('date_sortie')
            reception.save(update_fields=update_fields)

        entree.save()

        if entree.motif != MotifEntree.VISITE and bon_sortie:
            notifier_sortie_vehicule(bon_sortie)

        log_action(
            request,
            ActionType.CHANGEMENT_STATUT,
            'GUERITE',
            entree,
            {'statut': 'SORTI'},
        )

        messages.success(
            request,
            f"Sortie du véhicule {entree.vehicule.immatriculation} enregistrée.",
        )
        return redirect('dashboard_guerite')

    return render(request, 'guerite/sortie/enregistrer.html', {
        'entree': entree,
        'form': form,
        'bon_sortie': bon_sortie,
    })


@guerite_required
def consulter_bon_sortie(request):
    numero = request.GET.get('numero', '').strip()
    bon = None
    if numero:
        try:
            bon = BonSortie.objects.select_related('vehicule', 'vehicule__client').get(numero=numero)
        except BonSortie.DoesNotExist:
            messages.warning(request, f"Aucun bon de sortie trouvé avec le numéro {numero}")
    return render(request, 'guerite/bon_sortie/consulter.html', {'bon': bon, 'numero': numero})




def get_filtered_entrees(request):
    entrees = (
        EnregistrementEntree.objects
        .select_related('vehicule', 'vehicule__client', 'conducteur', 'agent_entree')
        .annotate(date_tri=Coalesce('date_sortie', 'date_entree'))
        .order_by(F('date_tri').desc())
    )

    statut = request.GET.get('statut', '').strip()
    motif = request.GET.get('motif', '').strip()
    date_debut = request.GET.get('date_debut', '').strip()
    date_fin = request.GET.get('date_fin', '').strip()
    q = request.GET.get('q', '').strip()

    if statut == 'SORTI':
        entrees = entrees.filter(statut='SORTI')
    elif statut == 'PRESENT':
        entrees = entrees.exclude(statut='SORTI')

    if motif:
        entrees = entrees.filter(motif=motif)
    if date_debut:
        entrees = entrees.filter(date_entree__date__gte=date_debut)
    if date_fin:
        entrees = entrees.filter(date_entree__date__lte=date_fin)
    if q:
        entrees = entrees.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(numero__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )
    return entrees


def historique_entrees(request):
    qs = get_filtered_entrees(request)
    paginator = Paginator(qs, 25)  # 25 par page
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'guerite/historique.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'motifs': MotifEntree.choices,   # adapte
'statuts': [
            ('PRESENT', 'Présent'),
            ('SORTI', 'Sorti'),
        ],    }
        )





def liste_vehicules_presents(request):
    page = get_entrees_presentes_filtrees(request, per_page=30)
    return render(request, 'guerite/vehicules_presents.html', {
        'entrees': page,           # boucle {% for entree in entrees %}
        'page_obj': page,          # pagination
        'motifs' : MotifEntree.choices,
        'paginator': page.paginator,
        'filters': {
            'q': request.GET.get('q', ''),
            'motif': request.GET.get('motif', ''),
            'date_debut': request.GET.get('date_debut', ''),
            'date_fin': request.GET.get('date_fin', ''),
        },
    })


 
# Filtre partagé — utilisé par vehicules_presents() ET les deux exports,
# pour garantir que "ce qu'on exporte" == "ce qu'on voit à l'écran".
# ---------------------------------------------------------------------------

def get_entrees_presentes_filtrees(request, per_page=30):
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

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page", 1)
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        page = paginator.page(1)
    except EmptyPage:
        page = paginator.page(paginator.num_pages)

    return page  # objet Page (itérable + infos pagination)
