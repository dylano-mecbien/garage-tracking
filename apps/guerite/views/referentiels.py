"""
Véhicules, clients, conducteurs (pages HTML).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators import guerite_required
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.forms import ClientForm, ConducteurForm, RechercheVehiculeForm, VehiculeForm
from apps.reception.views._utils import (
    NB_PHOTOS, appliquer_photos, enregistrer_photo, get_or_none, photos_list,
    post_str, supprimer_fichier,
)
from apps.vehicules.models import Client, Marque, Modele, Vehicule

from ._utils import get_or_create_nom, safe_next


# ─── Véhicules ───────────────────────────────────────────────────────────
@guerite_required
def recherche_vehicule(request):
    query = request.GET.get('q', '').strip()
    vehicules = []
    if query:
        vehicules = (
            Vehicule.objects.filter(
                Q(immatriculation__icontains=query) | Q(marque__icontains=query)
                | Q(modele__icontains=query) | Q(client__nom__icontains=query)
                | Q(client__prenom__icontains=query) | Q(numero_chassis__icontains=query)
            )
            .select_related('client').order_by('immatriculation')[:20]
        )
    return render(request, 'guerite/recherche_vehicule.html', {
        'form': RechercheVehiculeForm(request.GET or None),
        'vehicules': vehicules,
        'query': query,
    })


def _photo_urls(vehicule):
    if not vehicule:
        return [''] * NB_PHOTOS
    return [default_storage.url(p) if p else '' for p in photos_list(vehicule)]


@guerite_required
def creer_vehicule(request):
    client_id = request.GET.get('client_id')
    client = get_or_none(Client.objects, id=client_id) if client_id else None

    form = VehiculeForm(request.POST or None, request.FILES or None,
                        initial={'client': client.id} if client else {})

    if request.method == 'POST':
        if not request.POST.get('client'):
            form.add_error('client', 'Veuillez sélectionner un propriétaire.')

        if form.is_valid():
            with transaction.atomic():
                vehicule = form.save(commit=False)
                vehicule.created_by = request.user
                vehicule.immatriculation = vehicule.immatriculation.upper().strip()

                # Référentiel marques / modèles (insensible à la casse)
                marque = get_or_create_nom(Marque, form.cleaned_data['marque'].strip())
                get_or_create_nom(Modele, form.cleaned_data['modele'].strip(), marque=marque)
                vehicule.save()

                # CORRIGÉ : un seul save() après la boucle (avant : jusqu'à 3)
                chemins = [
                    enregistrer_photo(vehicule.immatriculation, request.FILES[f'photo_{i}'], i)
                    for i in range(NB_PHOTOS) if request.FILES.get(f'photo_{i}')
                ]
                if chemins:
                    appliquer_photos(vehicule, chemins)
                    vehicule.save(update_fields=['photos', 'photo'])

            log_action(request, ActionType.CREATION, 'GUERITE', vehicule)
            messages.success(request, f"Véhicule {vehicule.immatriculation} créé.")
            return redirect(f"/guerite/entree/enregistrer/?vehicule_id={vehicule.id}")

    return render(request, 'guerite/entree/creer_vehicule.html', {
        'form': form,
        'client_id': client.id if client else None,
        'client_preselect': str(client) if client else None,
    })


@guerite_required
def modifier_vehicule(request, vehicule_id=None):
    """Sans vehicule_id : étape 1 (recherche). Avec : formulaire prérempli + POST."""
    vehicule = get_object_or_404(Vehicule, pk=vehicule_id) if vehicule_id else None

    if request.method == 'POST':
        if not vehicule:
            return redirect('modifier_vehicule_recherche')

        form = VehiculeForm(request.POST, request.FILES, instance=vehicule)

        # CORRIGÉ : l'id client était écrit tel quel → erreur 500 s'il était invalide
        client_id = post_str(request, 'client')
        client = get_or_none(Client.objects, id=client_id) if client_id else None
        if client_id and client is None:
            form.add_error(None, "Propriétaire introuvable.")

        if form.is_valid():
            v = form.save(commit=False)
            if client:
                v.client = client
            v.immatriculation = v.immatriculation.upper().strip()  # comme à la création

            chemins = photos_list(v)
            for i in range(NB_PHOTOS):
                nouveau = request.FILES.get(f'photo_{i}')
                if request.POST.get(f'remove_photo_{i}') == '1' or nouveau:
                    supprimer_fichier(chemins[i])
                    chemins[i] = ''
                if nouveau:
                    chemins[i] = enregistrer_photo(v.immatriculation, nouveau, i)
            appliquer_photos(v, chemins)

            v.save()
            log_action(request, ActionType.MODIFICATION, 'GUERITE', v)
            messages.success(request, f"Véhicule {v.immatriculation} mis à jour avec succès.")
            return redirect('modifier_vehicule', vehicule_id=v.id)
    else:
        form = VehiculeForm(instance=vehicule)

    return render(request, 'guerite/modifier_vehicule.html', {
        'form': form, 'vehicule': vehicule, 'photo_urls': _photo_urls(vehicule),
    })


@login_required  # AJOUTÉ
def modifier_vehicule_recherche(request):
    """Étape 1 seule — lien « 🔎 Changer de véhicule »."""
    return render(request, 'guerite/modifier_vehicule.html', {
        'form': VehiculeForm(), 'vehicule': None, 'photo_urls': _photo_urls(None),
    })


# ─── Clients / conducteurs ───────────────────────────────────────────────
@guerite_required
def creer_client(request):
    form = ClientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        client = form.save(commit=False)
        client.created_by = request.user
        client.save()
        log_action(request, ActionType.CREATION, 'GUERITE', client)
        messages.success(request, f"Client {client} créé.")
        # AJOUTÉ : redirection après succès. Avant, F5 recréait le client en double.
        return redirect(request.get_full_path())
    return render(request, 'guerite/entree/creer_client.html', {'form': form})


@guerite_required
def creer_conducteur(request):
    form = ConducteurForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        conducteur = form.save(commit=False)
        conducteur.created_by = request.user
        conducteur.save()
        log_action(request, ActionType.CREATION, 'GUERITE', conducteur)
        messages.success(request, f"Conducteur {conducteur} créé.")
        # CORRIGÉ : ?next= vérifié (avant : redirection vers n'importe quel site)
        return redirect(safe_next(request, 'nouvelle_entree'))
    return render(request, 'guerite/entree/creer_conducteur.html', {'form': form})
