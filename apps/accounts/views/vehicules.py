"""
Véhicules : liste, création, modification, détail, photos, mouvements (AJAX).
"""
import json
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.forms import VehiculeForm
from apps.guerite.models import EnregistrementEntree
from apps.reception.views import paginate_queryset
from apps.vehicules.models import Client, Marque, Vehicule

from ..decorators import admin_required
from ._utils import (
    CARBURANTS, NB_PHOTOS, STATUTS_OR_ACTIFS, TRANSMISSIONS,
    appliquer_photos, enregistrer_photo, photos_list, post_int, post_str, supprimer_fichier,
)


@admin_required
def admin_vehicules(request):
    q = request.GET.get('q', '').strip()
    carburant = request.GET.get('carburant', '')
    type_client = request.GET.get('type_client', '')
    assurance = request.GET.get('assurance', '')
    presence = request.GET.get('presence', 'tous')
    today = timezone.localdate()

    qs = Vehicule.objects.select_related('client').filter(is_active=True)
    if q:
        qs = qs.filter(
            Q(immatriculation__icontains=q) | Q(marque__icontains=q) | Q(modele__icontains=q)
            | Q(numero_chassis__icontains=q) | Q( client__nom__icontains=q)
            | Q(client__prenom__icontains=q) | Q(client__telephone__icontains=q)
        )

   
    if carburant:
        qs = qs.filter(type_carburant=carburant) 
    if type_client:
        qs = qs.filter(client__type_client=type_client)
    if assurance == 'expiree':
        qs = qs.filter(expiry_assurance__lt=today)
    elif assurance == 'valide':
        qs = qs.filter(expiry_assurance__gte=today)

    present_q = Q(entrees__statut='EN_COURS')
    atelier_q = Q(ordres_reparation__statut__in=STATUTS_OR_ACTIFS)
    if presence == 'presents':
        qs = qs.filter(present_q).distinct()
    elif presence == 'atelier':
        qs = qs.filter(atelier_q).distinct()
    elif presence == 'libres':
        qs = qs.exclude(present_q).distinct()

    # Stats globales en 1 requête
    stats = Vehicule.objects.filter(is_active=True).aggregate(
        total=Count('id', distinct=True),
        presents=Count('id', filter=present_q, distinct=True),
        en_atelier=Count('id', filter=atelier_q, distinct=True),
        entreprises=Count('id', filter=Q(client__type_client='ENTREPRISE'), distinct=True),
    )
    stats['libres'] = stats['total'] - stats['presents']

    page_obj = paginate_queryset(request, qs.order_by('immatriculation'), per_page=25)
    return render(request, 'admin_custom/vehicules/liste.html', {
        'vehicules': page_obj,
        'page_obj': page_obj,
        'nb_presents': stats['presents'],
        'stats': stats,
        'filtre_presence': presence,
        'filters': {'q': q, 'carburant': carburant, 'type_client': type_client, 'assurance': assurance},
        'carburants': CARBURANTS,
    })


@admin_required
def admin_creer_vehicule(request):
    client_id = request.GET.get('client_id')
    client = Client.objects.filter(id=client_id).first() if client_id else None
    form = VehiculeForm(request.POST or None, request.FILES or None,
                        initial={'client': client.id} if client else {})

    if request.method == 'POST':
        if not request.POST.get('client'):
            form.add_error('client', 'Veuillez sélectionner un propriétaire.')

        if form.is_valid():
            vehicule = form.save(commit=False)
            vehicule.created_by = request.user
            vehicule.immatriculation = vehicule.immatriculation.upper().strip()
            # Alimente le référentiel des marques (autocomplétion)
            Marque.objects.get_or_create(nom=form.cleaned_data['marque'].strip())
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
            return redirect('detail_vehicule', vehicule_id=vehicule.id)

    return render(request, 'admin_custom/vehicules/creer_vehicule.html', {
        'form': form,
        'client_id': client.id if client else None,
        'client_preselect': str(client) if client else None,
    })


@admin_required
def admin_modifier_vehicule(request, vehicule_id):
    v = get_object_or_404(Vehicule, id=vehicule_id)

    def render_form():
        urls = [default_storage.url(p) if p else '' for p in photos_list(v)]
        return render(request, 'admin_custom/vehicules/modifier.html', {
            'v': v,
            'carburants': CARBURANTS,
            'transmissions': TRANSMISSIONS,
            'photo_urls_json': json.dumps(urls),
        })

    if request.method != 'POST':
        return render_form()

    # ── Propriétaire (vérifié en premier pour ne rien modifier si erreur) ──
    client = Client.objects.filter(id=post_str(request, 'client')).first()
    if not client:
        messages.error(request, "Veuillez sélectionner un propriétaire valide.")
        return render_form()

    v.client = client
    v.immatriculation = post_str(request, 'immatriculation', v.immatriculation).upper()
    v.marque = post_str(request, 'marque', v.marque)
    v.modele = post_str(request, 'modele', v.modele)
    v.annee = post_int(request, 'annee')          # plus d'erreur 500 sur saisie invalide
    v.puissance = post_int(request, 'puissance')
    v.couleur = post_str(request, 'couleur') or None
    v.type_carburant = request.POST.get('type_carburant', v.type_carburant)
    v.transmission = request.POST.get('transmission', v.transmission)
    v.numero_chassis = post_str(request, 'numero_chassis') or None
    v.num_assurance = post_str(request, 'num_assurance')
    v.expiry_assurance = post_str(request, 'expiry_assurance') or None
    v.date_visite = post_str(request, 'date_visite') or None
    v.notes = post_str(request, 'notes')

    # ── Photos : suppression / remplacement ──
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
    log_action(request, ActionType.MODIFICATION, 'ADMIN', v)
    messages.success(request, f"Véhicule {v.immatriculation} mis à jour.")
    return redirect('admin_vehicules')


@admin_required
def detail_vehicule(request, vehicule_id):
    v = get_object_or_404(Vehicule.objects.select_related('client'), id=vehicule_id)
    return render(request, 'admin_custom/vehicules/detail.html', {
        'v': v,
        'entrees': v.entrees.order_by('-date_entree')[:10],
        'or_list': v.ordres_reparation.order_by('-date_creation')[:10],
        'rec_list': v.receptions.order_by('-created_at')[:5],
    })


@admin_required
def admin_mouvements_vehicule(request, vehicule_id):
    """AJAX — mouvements d'un véhicule."""
    v = get_object_or_404(Vehicule, id=vehicule_id)
    base = EnregistrementEntree.objects.filter(vehicule=v)

    # CORRIGÉ : les stats portent sur tout l'historique, pas sur les 20 derniers
    stats = base.aggregate(
        total_passages=Count('id'),
        reparations=Count('id', filter=Q(motif='REPARATION')),
    )

    fmt = '%d/%m/%Y %H:%M'
    mouvements = [{
        'numero': e.numero,
        'motif': e.get_motif_display(),
        'statut': e.statut,
        'date_entree': timezone.localtime(e.date_entree).strftime(fmt),
        'date_sortie': timezone.localtime(e.date_sortie).strftime(fmt) if e.date_sortie else None,
        'duree': None,
        'reception': getattr(getattr(e, 'reception', None), 'numero', None),
    } for e in base.select_related('reception').order_by('-date_entree')[:20]]

    return JsonResponse({
        'mouvements': mouvements,
        'statut_presence': v.statut_presence,
        'stats': stats,
    })


@login_required  # CORRIGÉ : photo accessible sans connexion avant
def photo_vehicule(request, vehicule_id):
    """Sert la photo via le storage Django (MinIO), même si le bucket est privé."""
    v = get_object_or_404(Vehicule.objects.only('id', 'photo'), id=vehicule_id)
    if not v.photo:
        raise Http404("Pas de photo")
    try:
        fichier = v.photo.storage.open(v.photo.name, 'rb')
    except Exception:
        raise Http404("Photo introuvable sur le stockage")
    resp = FileResponse(fichier, content_type=mimetypes.guess_type(v.photo.name)[0] or 'image/jpeg')
    resp['Cache-Control'] = 'private, max-age=86400'
    return resp
