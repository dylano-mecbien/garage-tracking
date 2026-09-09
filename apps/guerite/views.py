"""
Vues Guérite - Entrées/Sorties véhicules
"""
import base64
import json
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import  Count, When
from django.views.decorators.http import require_POST
import os
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from .models import EnregistrementEntree, BonSortie, EtatBon, StatutEntree, MotifEntree, StatutViewHinstorisue
from .forms import RechercheVehiculeForm, VehiculeForm, ClientForm, ConducteurForm, EntreeForm, SortieForm
from apps.vehicules.models import Marque, Modele, Vehicule, Client, Conducteur
from apps.accounts.decorators import guerite_required 
from apps.audit.service import log_action
from apps.audit.models import ActionType
from itertools import chain
from ..reception.views import dashboard as reception_dashboard
from django.http import Http404, JsonResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from django.http import HttpResponse
from django.db.models import Case, IntegerField, Q, Value
import datetime
 
from django.http import HttpResponse
 
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib.enums import TA_CENTER



 
@guerite_required
def dashboard(request):
    # 👉 si réceptionniste → appeler autre view
    if request.user.role == 'RECEPTIONNISTE':
        return reception_dashboard(request)

    aujourd_hui = timezone.now().date()
    entrees_today = EnregistrementEntree.objects.filter(
        date_entree__date=aujourd_hui
    )

    # Requête avec tri prioritaire (Bon de sortie fait OU Visite) + limite à 7
    vehicules_presents = (
        EnregistrementEntree.objects.exclude(statut=StatutEntree.SORTI)
        .annotate(
            priorite=Case(
                When(
                    Q(statut='BON_SORTIE_FAIT') | Q(motif='VISITE'),
                    then=Value(0),
                ),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .select_related(
            'vehicule',
            'vehicule__client',
            'conducteur',
            'conducteur__client',
        )
        .order_by('priorite', '-date_entree')[:7]
    )
    ctx = {
        'nb_entrees_today': entrees_today.count(),
        'nb_sorties_today': entrees_today.filter(
            statut=StatutEntree.SORTI
        ).count(),
        'entrees' : get_entrees_presentes_filtrees(request),
        'vehicules_presents': vehicules_presents,
        'entrees_recentes': entrees_today.select_related(
            'vehicule', 'conducteur'
        ).order_by('-date_entree')[:7],
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
           #  entrees__statut=StatutEntree.EN_COURS  )

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


def modifier_vehicule(request, vehicule_id=None):
    """
    Sans vehicule_id  -> affiche uniquement l'étape 1 (recherche par matricule).
    Avec vehicule_id  -> affiche le formulaire préempli, et traite le POST.
    """
    vehicule = None
    if vehicule_id:
        vehicule = get_object_or_404(Vehicule, pk=vehicule_id)

    if request.method == 'POST':
        if not vehicule:
            # Sécurité : impossible de POSTer sans avoir d'abord choisi un véhicule
            return redirect('modifier_vehicule_recherche')

        form = VehiculeForm(request.POST, request.FILES, instance=vehicule)
        if form.is_valid():
            v = form.save(commit=False)

            client_id = request.POST.get('client')
            if client_id:
                v.client_id = client_id

            # Gestion des 3 emplacements photo : suppression demandée ou remplacement
            for i, field_name in enumerate(PHOTO_FIELDS):
                if request.POST.get(f'remove_photo_{i}') == '1':
                    photo = getattr(v, field_name)
                    if photo:
                        photo.delete(save=False)
                    setattr(v, field_name, None)
                uploaded = request.FILES.get(f'photo_{i}')
                if uploaded:
                    setattr(v, field_name, uploaded)

            v.save()
            messages.success(request, f"Véhicule {v.immatriculation} mis à jour avec succès.")
            return redirect('modifier_vehicule', vehicule_id=v.id)
    else:
        form = VehiculeForm(instance=vehicule) if vehicule else VehiculeForm()

    return render(request, 'guerite/modifier_vehicule.html', {
        'form': form,
        'vehicule': vehicule,
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

        if motif in ["REPARATION", "VISITE"]:
            entree.motif = motif
            entree.save()

            messages.success(
                request,
                f"Motif modifié : {entree.get_motif_display()}"
            )

    return redirect("detail_entree", entree_id=entree.id)




def get_entree_non_sortie(entree_id):
    entree = get_object_or_404(EnregistrementEntree, id=entree_id)
    if entree.statut == StatutEntree.SORTI:
        raise Http404("Entrée déjà sortie")
    return entree

# Utilisation


@guerite_required
def enregistrer_sortie(request, entree_id):
    entree = get_entree_non_sortie(entree_id)
    bon_sortie = None

    # Recherche du bon de sortie uniquement pour une réparation
    if entree.motif == MotifEntree.REPARATION:
        bons = BonSortie.objects.filter(
            vehicule=entree.vehicule,
            est_valide=False
        )
        if bons.exists():
            bon_sortie = bons.latest('created_at')

    form = SortieForm()

    if request.method == 'POST':
        form = SortieForm(request.POST)

        # Vérification du bon de sortie pour les réparations
        if entree.motif == MotifEntree.REPARATION and not bon_sortie:
            messages.error(
                request,
                "Aucun bon de sortie valide trouvé. Contactez la réception."
            )
            return render(
                request,
                'guerite/sortie/enregistrer.html',
                {
                    'entree': entree,
                    'form': form,
                    'bon_sortie': bon_sortie
                }
            )

        # Enregistrement de la sortie
        entree.statut = StatutEntree.SORTI
        entree.date_sortie = timezone.now()
        entree.agent_sortie = request.user

        # Mise à jour du bon uniquement pour une réparation
        if entree.motif == MotifEntree.REPARATION and bon_sortie:
            bon_sortie.est_valide = True
            bon_sortie.valide_par = request.user
            bon_sortie.date_validation = timezone.now()
            bon_sortie.etats = EtatBon.VALIDER
            bon_sortie.save()

            entree.bon_sortie = bon_sortie

        entree.save()

        log_action(
            request,
            ActionType.CHANGEMENT_STATUT,
            'GUERITE',
            entree,
            {'statut': 'SORTI'}
        )

        messages.success(
            request,
            f"Sortie du véhicule {entree.vehicule.immatriculation} enregistrée."
        )

        return redirect('dashboard_guerite')

    return render(
        request,
        'guerite/sortie/enregistrer.html',
        {
            'entree': entree,
            'form': form,
            'bon_sortie': bon_sortie
        }
    )

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


@guerite_required 
def historique_entrees(request):
    entrees = get_filtered_entrees(request)
    return render(request, 'guerite/historique.html', {
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


def export_entrees_excel(request):
    # Récupérer les mêmes filtres que dans historique_entrees
    entrees = get_filtered_entrees(request)  # on factorise la logique

    wb = Workbook()
    ws = wb.active
    ws.title = "Historique entrées"

    # En-têtes
    headers = [
        'N°', 'Immatriculation', 'Client', 'Téléphone client', 'Conducteur',
        'Motif', 'Statut', 'Date entrée', 'Date sortie', 'Agent entrée',
        'Observations',
    ]
    ws.append(headers)

    # Mise en forme des en-têtes
    for cell in ws[1]:
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal='center')

    for e in entrees:
        ws.append([
            e.numero,
            e.vehicule.immatriculation,
            str(e.vehicule.client),
            e.vehicule.client.telephone if e.vehicule.client else '',
            str(e.conducteur) if e.conducteur else '',
            e.get_motif_display(),
            e.get_statut_display(),
            e.date_entree.strftime("%d/%m/%Y %H:%M") if e.date_entree else '',
            e.date_sortie.strftime("%d/%m/%Y %H:%M") if e.date_sortie else '',
            e.agent_entree.full_name if e.agent_entree else '',
            e.observations or '',
        ])

    # Ajuster la largeur des colonnes
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        adjusted_width = min(max_length + 2, 30)
        ws.column_dimensions[col_letter].width = adjusted_width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=historique_entrees_{timezone.localdate()}.xlsx'
    wb.save(response)
    return response


BRAND_COLOR = colors.HexColor('#366092')


def _footer(canvas, doc):
    """Pied de page : numéro de page + date de génération, sur chaque page."""
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#999999'))
    canvas.drawString(
        1 * cm, 0.7 * cm,
        f"Généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')}",
    )
    canvas.drawRightString(
        landscape(A4)[0] - 1 * cm, 0.7 * cm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def export_entrees_pdf(request):
    entrees = get_filtered_entrees(request)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=historique_entrees_{timezone.localdate()}.pdf'

    doc = SimpleDocTemplate(
        response, pagesize=landscape(A4),
        rightMargin=1 * cm, leftMargin=1 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # Titre
    title_style = ParagraphStyle(
        'Titre', parent=styles['Heading1'], alignment=TA_CENTER,
        textColor=BRAND_COLOR, fontSize=16, spaceAfter=2,
    )
    elements.append(Paragraph("Historique des entrées", title_style))

    # Sous-titre : nombre de résultats
    meta_style = ParagraphStyle(
        'Meta', parent=styles['Normal'], alignment=TA_CENTER,
        fontSize=9, textColor=colors.HexColor('#666666'),
    )
    elements.append(Paragraph(
        f"{entrees.count()} mouvement(s) trouvé(s)", meta_style,
    ))
    elements.append(Spacer(1, 8))

    # Filtres appliqués (affichés seulement s'il y en a)
    filters = []
    if request.GET.get('q'):
        filters.append(f"Recherche : {request.GET['q']}")
    if request.GET.get('statut'):
        filters.append(f"Statut : {dict(StatutEntree.choices).get(request.GET['statut'], '')}")
    if request.GET.get('motif'):
        filters.append(f"Motif : {dict(MotifEntree.choices).get(request.GET['motif'], '')}")
    if request.GET.get('date_debut'):
        filters.append(f"Du : {request.GET['date_debut']}")
    if request.GET.get('date_fin'):
        filters.append(f"Au : {request.GET['date_fin']}")

    if filters:
        filter_style = ParagraphStyle(
            'FilterStyle', parent=styles['Normal'], alignment=TA_CENTER,
            fontSize=8.5, textColor=colors.HexColor('#888888'), spaceAfter=4,
        )
        elements.append(Paragraph("Filtres : " + " · ".join(filters), filter_style))

    elements.append(Spacer(1, 10))

    # Données du tableau
    data = [['Immat.', 'Client', 'Motif', 'Statut', 'Entrée', 'Sortie', 'Agent']]
    for e in entrees:
        data.append([
            e.vehicule.immatriculation,
            str(e.vehicule.client)[:30],
            e.get_motif_display(),
            e.get_statut_display(),
            e.date_entree.strftime("%d/%m %H:%M") if e.date_entree else '—',
            e.date_sortie.strftime("%d/%m %H:%M") if e.date_sortie else '—',
            e.agent_entree.full_name.split()[0] if e.agent_entree else '—',
        ])

    if len(data) == 1:
        elements.append(Paragraph("Aucun mouvement ne correspond à ces critères.", styles['Normal']))
    else:
        table = Table(
            data, repeatRows=1,
            colWidths=[2.2 * cm, 4.5 * cm, 2.8 * cm, 2.8 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm],
        )
        table.setStyle(TableStyle([
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            # Corps (lignes zébrées)
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F6FA')]),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
            # Global
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ]))
        elements.append(table)

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return response







@guerite_required
def liste_vehicules_presents(request):
    entrees = get_entrees_presentes_filtrees(request)
    return render(request, 'guerite/vehicules_presents.html', {'entrees': entrees,
                                                               'motifs': MotifEntree.choices})


MOTIF_LABELS = {
    "REPARATION": "🔧 Réparation",
    "VISITE": "👁 Visite",
}
 

# Filtre partagé — utilisé par vehicules_presents() ET les deux exports,
# pour garantir que "ce qu'on exporte" == "ce qu'on voit à l'écran".
# ---------------------------------------------------------------------------
def get_entrees_presentes_filtrees(request):
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
        from django.db.models import Q
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
 
    return qs
 


 
def _ligne_entree(entree):
    """Une ligne de données commune aux deux exports."""
    vehicule = entree.vehicule
    client = vehicule.client
    return [
        vehicule.immatriculation,
        f"{vehicule.marque} {vehicule.modele}".strip(),
        str(client) if client else "—",
        getattr(client, "telephone", "") or "—",
        str(entree.conducteur) if entree.conducteur else "—",
        MOTIF_LABELS.get(entree.motif, entree.get_motif_display()),
        timezone.localtime(entree.date_entree).strftime("%d/%m/%Y %H:%M"),
        str(entree.duree_sejour),
    ]
 
 
ENTETES = [
    "Immatriculation", "Véhicule", "Propriétaire", "Téléphone",
    "Conducteur", "Motif", "Entrée le", "Durée",
]
 
 
# ---------------------------------------------------------------------------
# Export Excel
# ---------------------------------------------------------------------------
def export_presents_excel(request):
    entrees = get_entrees_presentes_filtrees(request)
 
    wb = Workbook()
    ws = wb.active
    ws.title = "Véhicules présents"
 
    # Titre
    ws.merge_cells("A1:H1")
    titre = ws["A1"]
    titre.value = "Véhicules présents dans le local"
    titre.font = Font(size=14, bold=True, color="FFFFFF")
    titre.alignment = Alignment(horizontal="center", vertical="center")
    titre.fill = PatternFill("solid", fgColor="1F4E78")
    ws.row_dimensions[1].height = 26
 
    ws.merge_cells("A2:H2")
    sous_titre = ws["A2"]
    sous_titre.value = (
        f"Généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')} — "
        f"{entrees.count()} véhicule(s)"
    )
    sous_titre.font = Font(size=9, italic=True, color="666666")
    sous_titre.alignment = Alignment(horizontal="center")
 
    # En-têtes (ligne 4)
    header_row = 4
    header_fill = PatternFill("solid", fgColor="2E75B6")
    header_font = Font(bold=True, color="FFFFFF")
    thin_border = Border(*(Side(style="thin", color="CCCCCC"),) * 4)
 
    for col, entete in enumerate(ENTETES, start=1):
        cell = ws.cell(row=header_row, column=col, value=entete)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
 
    # Données
    zebra_fill = PatternFill("solid", fgColor="F2F6FA")
    for i, entree in enumerate(entrees, start=1):
        row = header_row + i
        for col, valeur in enumerate(_ligne_entree(entree), start=1):
            cell = ws.cell(row=row, column=col, value=valeur)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=False)
            if i % 2 == 0:
                cell.fill = zebra_fill
 
    # Largeurs de colonnes auto (approx.)
    largeurs = [16, 22, 22, 15, 18, 16, 17, 12]
    for col, largeur in enumerate(largeurs, start=1):
        ws.column_dimensions[get_column_letter(col)].width = largeur
 
    ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = f"A{header_row}:H{header_row}"
 
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        )
    )
    filename = f"vehicules_presents_{timezone.localtime().strftime('%Y%m%d_%H%M')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response
 
 
# ---------------------------------------------------------------------------
# Export PDF (ReportLab, cohérent avec le reste du projet)
# ---------------------------------------------------------------------------
def export_presents_pdf(request):
    entrees = get_entrees_presentes_filtrees(request)
 
    response = HttpResponse(content_type="application/pdf")
    filename = f"vehicules_presents_{timezone.localtime().strftime('%Y%m%d_%H%M')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
 
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        leftMargin=1 * cm,
        rightMargin=1 * cm,
    )
 
    styles = getSampleStyleSheet()
    titre_style = ParagraphStyle(
        "Titre", parent=styles["Title"], fontSize=16, alignment=TA_CENTER,
        textColor=colors.HexColor("#1F4E78"),
    )
    sous_titre_style = ParagraphStyle(
        "SousTitre", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"),
    )
 
    elements = [
        Paragraph("Véhicules présents dans le local", titre_style),
        Paragraph(
            f"Généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')} — "
            f"{entrees.count()} véhicule(s)",
            sous_titre_style,
        ),
        Spacer(1, 0.5 * cm),
    ]
 
    data = [ENTETES] + [_ligne_entree(e) for e in entrees]
 
    if len(data) == 1:
        elements.append(Paragraph("Aucun véhicule dans le local.", styles["Normal"]))
    else:
        col_widths = [3.0, 4.2, 4.2, 3.0, 3.4, 3.2, 3.4, 2.3]
        col_widths = [w * cm for w in col_widths]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F2F6FA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(table)
 
    doc.build(elements)
    return response
 