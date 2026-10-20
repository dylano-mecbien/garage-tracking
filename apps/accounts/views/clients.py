"""
Clients et centres.

Un centre = un Client dont `parent` pointe sur l'entreprise.
Les véhicules restent sur vehicule.client (l'entreprise = siège, ou un centre).
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.forms_centres import CentreForm   # ⚠️ chemin réel de CentreForm
from apps.accounts.views.vehicules import photo_vehicule
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.forms import ClientForm
from apps.guerite.models import EnregistrementEntree
from apps.reception.views import paginate_queryset
from apps.vehicules.models import Client, Vehicule

from ..decorators import admin_required, receptionniste_required
from ._utils import post_str, qs_sans

VEHICULES_PAR_PAGE = 8
MOUVEMENTS_PAR_PAGE = 15


def _fiche(client_id, **params):
    url = reverse('admin_detail_client', args=[client_id])
    if params:
        url += '?' + '&'.join(f"{k}={v}" for k, v in params.items())
    return url


# ─── Clients ─────────────────────────────────────────────────────────────
@admin_required
def admin_clients(request):
    q = request.GET.get('q', '').strip()
    filtre_type = request.GET.get('type', 'tous')
    ville = request.GET.get('ville', '')
    avec_vehicule = request.GET.get('avec_vehicule', '')

    # Seulement les entreprises et particuliers : les centres s'affichent dans la fiche de leur entreprise
    qs = (
        Client.objects.filter(is_active=True, parent__isnull=True)
        .prefetch_related('vehicules')
        .annotate(
            nb_centres=Count('centres', distinct=True),
            # véhicules / passages de l'entreprise + de ses centres
            nb_vehicules_total=Count('vehicules', distinct=True) + Count('centres__vehicules', distinct=True),
            nb_passages=Count('vehicules__entrees', distinct=True)
                        + Count('centres__vehicules__entrees', distinct=True),
        )
    )
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q)
            | Q(email__icontains=q) | Q(ninea__icontains=q) | Q(ville__icontains=q)
            | Q(numero_client__icontains=q)
            | Q(centres__nom__icontains=q)          # trouver une entreprise par le nom d'un de ses centres
        ).distinct()
    if filtre_type and filtre_type != 'tous':
        qs = qs.filter(type_client=filtre_type)
    if ville:
        qs = qs.filter(Q(ville=ville) | Q(centres__ville=ville)).distinct()
    if avec_vehicule == '1':
        qs = qs.filter(Q(vehicules__isnull=False) | Q(centres__vehicules__isnull=False)).distinct()
    elif avec_vehicule == '0':
        qs = qs.filter(vehicules__isnull=True).exclude(centres__vehicules__isnull=False)

    actifs = Client.objects.filter(is_active=True)
    principaux = actifs.filter(parent__isnull=True)
    stats = principaux.aggregate(
        total=Count('id', distinct=True),
        particuliers=Count('id', filter=Q(type_client='PARTICULIER'), distinct=True),
        entreprises=Count('id', filter=Q(type_client='ENTREPRISE'), distinct=True),
    )
    stats['centres'] = actifs.filter(parent__isnull=False).count()
    stats['total_vehicules'] = Vehicule.objects.filter(client__is_active=True).count()

    villes = (actifs.exclude(ville__isnull=True).exclude(ville='')
              .values_list('ville', flat=True).distinct().order_by('ville'))

    page_obj = paginate_queryset(request, qs.order_by('nom'), per_page=25)
    return render(request, 'admin_custom/clients/liste.html', {
        'clients': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'villes': villes,
        'filtre_type': filtre_type,
        'filters': {'q': q, 'ville': ville, 'avec_vehicule': avec_vehicule},
    })


@admin_required
def admin_creer_client(request):
    form = ClientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        client = form.save(commit=False)
        client.created_by = request.user
        client.save()
        log_action(request, ActionType.CREATION, 'GUERITE', client)
        messages.success(request, f"Client {client} créé.")
        return redirect('admin_clients')
    return render(request, 'admin_custom/clients/creer_client.html', {'form': form})


@admin_required
def admin_modifier_client(request, client_id):
    c = get_object_or_404(Client.objects.select_related('parent'), id=client_id)

    if request.method == 'POST':
        nouveau_type = request.POST.get('type_client', c.type_client)
        if c.parent_id:
            nouveau_type = 'ENTREPRISE'                 # un centre reste rattaché à une entreprise
        elif nouveau_type == 'PARTICULIER' and c.centres.exists():
            messages.error(request, "Ce client a des centres : il ne peut pas devenir particulier. "
                                    "Supprime ou déplace d'abord ses centres.")
            return redirect('admin_modifier_client', c.id)
        c.type_client = nouveau_type

        if c.type_client == 'ENTREPRISE':
            c.nom = post_str(request, 'nom_entreprise') or post_str(request, 'nom') or c.nom
            c.prenom = ''
            c.ninea = post_str(request, 'ninea')
            c.telephone = post_str(request, 'telephone_entreprise') or post_str(request, 'telephone')
            c.nom_correspondant = post_str(request, 'nom_correspondant')
            c.telephone2 = ''
        else:
            c.nom = post_str(request, 'nom', c.nom)
            c.prenom = post_str(request, 'prenom')
            c.ninea = ''
            c.telephone = post_str(request, 'telephone')
            c.telephone2 = post_str(request, 'telephone2')

        c.email = post_str(request, 'email')
        c.ville = post_str(request, 'ville')
        c.adresse = post_str(request, 'adresse')
        c.save()

        log_action(request, ActionType.MODIFICATION, 'ADMIN', c)
        messages.success(request, f"Client {c} mis à jour.")
        if c.parent_id:
            return redirect(_fiche(c.parent_id, tab='vehicules', centre=c.id))
        return redirect('admin_clients')

    return render(request, 'admin_custom/clients/modifier.html', {'c': c})


@receptionniste_required
def admin_detail_client(request, client_id):
    c = get_object_or_404(Client.objects.select_related('parent'), id=client_id)

    # La fiche d'un centre = la fiche de son entreprise, filtrée sur ce centre
    if c.parent_id:
        return redirect(_fiche(c.parent_id, tab='vehicules', centre=c.id))

    today = timezone.localdate()
    tous_vehicules = Vehicule.objects.filter(Q(client=c) | Q(client__parent=c))   # entreprise + centres

    centres = list(c.centres.annotate(nb_vehicules=Count('vehicules')).order_by('nom'))
    nb_vehicules = tous_vehicules.count()
    nb_siege = tous_vehicules.filter(client=c).count()

    # Siège d'abord, puis chaque centre par nom
    vehicules = (
        tous_vehicules
        .select_related('client')
        .annotate(
            nb_passages=Count('entrees', distinct=True),
            ordre_siege=Case(When(client=c, then=Value(0)), default=Value(1), output_field=IntegerField()),
        )
        .order_by('ordre_siege', 'client__nom', 'immatriculation')
    )

    # Filtre : ?centre=<id du centre> ou ?centre=siege
    filtre_centre = request.GET.get('centre', '')
    if filtre_centre == 'siege':
        vehicules = vehicules.filter(client=c)
    elif filtre_centre:
        vehicules = vehicules.filter(client_id=filtre_centre)

    page_vehicules = Paginator(vehicules, VEHICULES_PAR_PAGE).get_page(request.GET.get('page'))

    # Regroupement de la page courante : siège puis centres
    total_par_centre = {ct.id: ct.nb_vehicules for ct in centres}
    groupes = []
    for v in page_vehicules:
        if not groupes or groupes[-1]['client_id'] != v.client_id:
            siege = v.client_id == c.id
            groupes.append({
                'client_id': v.client_id,
                'siege': siege,
                'centre': None if siege else v.client,
                'total': nb_siege if siege else total_par_centre.get(v.client_id, 0),
                'vehicules': [],
            })
        groupes[-1]['vehicules'].append(v)

    # Centres sans véhicule : en fin de liste, pour pouvoir les modifier / supprimer
    centres_vides = []
    if not page_vehicules.has_next():
        centres_vides = [ct for ct in centres
                         if ct.nb_vehicules == 0 and filtre_centre in ('', str(ct.id))]

    entrees = (
        EnregistrementEntree.objects
        .filter(Q(vehicule__client=c) | Q(vehicule__client__parent=c))
        .select_related('vehicule', 'vehicule__client', 'reception')
        .order_by('-date_entree')
    )
    page_entrees = Paginator(entrees, MOUVEMENTS_PAR_PAGE).get_page(request.GET.get('page_mvt'))

    stats = entrees.aggregate(
        nb_passages=Count('id'),
        nb_reparations=Count('id', filter=Q(motif='REPARATION')),
        nb_visites=Count('id', filter=Q(motif='VISITE')),
    )

    onglet = request.GET.get('tab', 'vehicules')
    if onglet not in ('vehicules', 'mouvements', 'infos'):
        onglet = 'vehicules'

    return render(request, 'admin_custom/clients/detail.html', {
        'client': c,
        'today': today,
        'onglet': onglet,
        'peut_avoir_centres': c.peut_avoir_centres,
        'centres': centres,
        'centres_vides': centres_vides,
        'filtre_centre': filtre_centre,
        'nb_siege': nb_siege,
        'nb_vehicules': nb_vehicules,
        'page_vehicules': page_vehicules,
        'groupes': groupes,
        'qs_vehicules': qs_sans(request, 'page', 'page_mvt', 'tab') + 'tab=vehicules&',
        'page_entrees': page_entrees,
        'qs_mouvements': qs_sans(request, 'page_mvt', 'tab') + 'tab=mouvements&',
        'passages_par_vehicule': (tous_vehicules.annotate(nb=Count('entrees'))
                                  .order_by('-nb', 'immatriculation').values('immatriculation', 'nb')),
        **stats,
        'premier_passage': entrees.last(),
        'dernier_passage': entrees.first(),
        'assurance_nb_expiree': tous_vehicules.filter(expiry_assurance__lt=today).count(),
    })


# ─── Centres (= clients enfants) ─────────────────────────────────────────
def _retour_fiche(client_id):
    return redirect(_fiche(client_id, tab='vehicules'))


def _erreurs(form):
    return " ".join(e for errs in form.errors.values() for e in errs)


@admin_required
@require_POST
def admin_creer_centre(request, client_id):
    parent = get_object_or_404(Client, id=client_id)
    if not parent.peut_avoir_centres:
        messages.error(request, "Seule une entreprise (qui n'est pas elle-même un centre) peut avoir des centres.")
        return _retour_fiche(parent.entreprise.id)
    form = CentreForm(request.POST, parent=parent)
    if form.is_valid():
        centre = form.save(commit=False)
        centre.created_by = request.user
        centre.save()
        log_action(request, ActionType.CREATION, 'ADMIN', centre)
        messages.success(request, f"Centre « {centre.nom} » créé.")
    else:
        messages.error(request, f"Centre non créé : {_erreurs(form)}")
    return _retour_fiche(parent.id)


@admin_required
@require_POST
def admin_modifier_centre(request, centre_id):
    centre = get_object_or_404(Client.objects.select_related('parent'), id=centre_id, parent__isnull=False)
    form = CentreForm(request.POST, instance=centre, parent=centre.parent)
    if form.is_valid():
        form.save()
        log_action(request, ActionType.MODIFICATION, 'ADMIN', centre)
        messages.success(request, f"Centre « {centre.nom} » modifié.")
    else:
        messages.error(request, f"Centre non modifié : {_erreurs(form)}")
    return _retour_fiche(centre.parent_id)


@admin_required
def admin_supprimer_centre(request, centre_id):
    centre = get_object_or_404(Client, id=centre_id, parent__isnull=False)
    parent_id, nom = centre.parent_id, centre.nom
    nb = centre.vehicules.count()
    if nb:
        # Supprimer un client supprime ses véhicules en cascade : on bloque.
        messages.error(request, f"Impossible de supprimer « {nom} » : {nb} véhicule(s) "
                                f"y sont encore rattachés. Déplace-les d'abord.")
    else:
        log_action(request, ActionType.SUPPRESSION, 'ADMIN', details={'centre': nom, 'id': str(centre.id)})
        centre.delete()
        messages.success(request, f"Centre « {nom} » supprimé.")
    return _retour_fiche(parent_id)
