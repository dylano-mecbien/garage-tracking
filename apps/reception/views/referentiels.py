"""
Référentiels vus depuis la réception : conducteurs, véhicules, clients (+ exports PDF).
"""
import json

from django.contrib import messages
from django.core.files.storage import default_storage
from django.db.models import Case, Count, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST


from apps.accounts.decorators import receptionniste_required
from apps.accounts.forms_centres import CentreForm
from apps.accounts.views._utils import qs_sans
from apps.accounts.views.clients import MOUVEMENTS_PAR_PAGE, VEHICULES_PAR_PAGE
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.models import EnregistrementEntree
from apps.reception.pdf_client_liste import generer_pdf_liste_clients
from apps.reception.pdf_vehicules_pdf import generer_pdf_liste_vehicules
from apps.vehicules.models import Client, Conducteur, Vehicule
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from ._utils import (
    CARBURANTS, NB_PHOTOS, Q_ATELIER, Q_PRESENT, TRANSMISSIONS,
    appliquer_photos, enregistrer_photo, filtrer_clients, filtrer_vehicules, fmt_dt, paginate_queryset, pdf_response,
    photos_list, post_int, post_str, supprimer_fichier,
)

CHAMPS_CONDUCTEUR = ('nom', 'prenom', 'telephone', 'telephone2', 'cni', 'permis', 'categorie_permis')


# ════════════════════════════════════════════════════════════════════════
#  CONDUCTEURS
# ════════════════════════════════════════════════════════════════════════
def _creer_conducteur(request):
    infos = {k: post_str(request, k) for k in CHAMPS_CONDUCTEUR}
    if not (infos['nom'] and infos['prenom'] and infos['telephone']):
        return messages.error(request, "Nom, prénom et téléphone sont obligatoires.")
    if Conducteur.objects.filter(telephone=infos['telephone']).exists():
        return messages.error(request, f"Un conducteur avec le téléphone {infos['telephone']} existe déjà.")

    c = Conducteur.objects.create(**infos, created_by=request.user)
    log_action(request, ActionType.CREATION, 'ADMIN', c)
    messages.success(request, f"Conducteur {c.prenom} {c.nom} créé.")


def _modifier_conducteur(request, cond_id):
    c = get_object_or_404(Conducteur, id=cond_id)
    infos = {k: post_str(request, k) for k in CHAMPS_CONDUCTEUR}
    if not (infos['nom'] and infos['telephone']):
        return messages.error(request, "Nom et téléphone sont obligatoires.")
    # AJOUTÉ : même contrôle de doublon qu'à la création
    if Conducteur.objects.filter(telephone=infos['telephone']).exclude(id=c.id).exists():
        return messages.error(request, f"Un autre conducteur utilise déjà le {infos['telephone']}.")

    for champ, valeur in infos.items():
        setattr(c, champ, valeur)
    c.save()
    log_action(request, ActionType.MODIFICATION, 'ADMIN', c)
    messages.success(request, f"Conducteur {c.prenom} {c.nom} mis à jour.")



@receptionniste_required
def rec_conducteurs(request):
    # ══════════════════════════════════════════════════════════════
    #  POST (création / modification)
    # ══════════════════════════════════════════════════════════════
    if request.method == 'POST':
        action  = request.POST.get('action')
        cond_id = post_str(request, 'cond_id')

        if action == 'creer':
            _creer_conducteur(request)
        elif action == 'modifier' and cond_id:
            _modifier_conducteur(request, cond_id)

        return redirect('rec_conducteurs')

    # ══════════════════════════════════════════════════════════════
    #  Filtres
    # ══════════════════════════════════════════════════════════════
    q         = request.GET.get('q', '').strip()
    categorie = request.GET.get('categorie', '')

    qs = Conducteur.objects.all()

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) |
            Q(prenom__icontains=q) |
            Q(telephone__icontains=q) |
            Q(cni__icontains=q) |
            Q(permis__icontains=q)
        )

    if categorie:
        qs = qs.filter(categorie_permis__icontains=categorie)

    # ══════════════════════════════════════════════════════════════
    #  Annotations (N+1 évité)
    # ══════════════════════════════════════════════════════════════
    entrees_c = (
        EnregistrementEntree.objects
        .filter(conducteur=OuterRef('pk'))
        .order_by()
    )

    qs = (
        qs
        .annotate(
            nb_passages=Coalesce(
                Subquery(
                    entrees_c
                    .values('conducteur')
                    .annotate(n=Count('id'))
                    .values('n')[:1],
                    output_field=IntegerField(),
                ),
                0,
            ),
            dernier_passage_id=Subquery(
                entrees_c.order_by('-date_entree').values('id')[:1]
            ),
        )
        .order_by('nom', 'prenom')
    )

    # ══════════════════════════════════════════════════════════════
    #  PAGINATION
    # ══════════════════════════════════════════════════════════════
    paginator = Paginator(qs, 25)             # ← 25 par page
    page_num  = request.GET.get('page', 1)
    page_obj  = paginator.get_page(page_num)

    # ── Chargement des derniers passages pour la page courante ──
    conducteurs = list(page_obj)
    derniers = EnregistrementEntree.objects.select_related('vehicule').in_bulk(
        [c.dernier_passage_id for c in conducteurs if c.dernier_passage_id]
    )
    for c in conducteurs:
        c.dernier_passage = derniers.get(c.dernier_passage_id)

    # ── Catégories disponibles pour le filtre ──
    categories = (
        Conducteur.objects
        .exclude(categorie_permis__isnull=True)
        .exclude(categorie_permis='')
        .values_list('categorie_permis', flat=True)
        .distinct()
        .order_by('categorie_permis')
    )

    return render(request, 'reception/conducteurs.html', {
        'conducteurs':  conducteurs,
        'page_obj':     page_obj,
        'paginator':    paginator,
        'nb_total':     Conducteur.objects.count(),
        'categories':   list(categories),
        'filters':      {'q': q, 'categorie': categorie},
    })

# ════════════════════════════════════════════════════════════════════════
#  VÉHICULES
# ════════════════════════════════════════════════════════════════════════


@receptionniste_required
def rec_vehicules(request):
    today = timezone.localdate()

    # ══════════════════════════════════════════════════════════════
    #  QuerySet filtré
    # ══════════════════════════════════════════════════════════════
    qs = filtrer_vehicules(
        request,
        Vehicule.objects.select_related('client').filter(is_active=True),
        today,
    )

    # ══════════════════════════════════════════════════════════════
    #  Stats globales (1 requête)
    # ══════════════════════════════════════════════════════════════
    stats = Vehicule.objects.filter(is_active=True).aggregate(
        total=Count('id', distinct=True),
        presents=Count('id', filter=Q_PRESENT, distinct=True),
        en_atelier=Count('id', filter=Q_ATELIER, distinct=True),
        entreprises=Count('id', filter=Q(client__type_client='ENTREPRISE'), distinct=True),
    )
    stats['libres'] = stats['total'] - stats['presents']

    # ══════════════════════════════════════════════════════════════
    #  PAGINATION
    # ══════════════════════════════════════════════════════════════
    paginator = Paginator(qs, 25)                    # 25 par page
    page_num  = request.GET.get('page', 1)
    page_obj  = paginator.get_page(page_num)

    # ── Filtres (pour la pagination + réaffichage du formulaire) ──
    g = request.GET
    filters = {
        k: g.get(k, '').strip()
        for k in ('q', 'carburant', 'type_client', 'assurance')
    }
    filtre_presence = g.get('presence', 'tous')

    # ── Vehicules de la page courante (liste, pas QuerySet) ──
    vehicules = list(page_obj)

    return render(request, 'reception/vehicules/liste.html', {
        'vehicules':       vehicules,
        'page_obj':        page_obj,
        'paginator':       paginator,
        'nb_presents':     stats['presents'],
        'stats':           stats,
        'filtre_presence': filtre_presence,
        'filters':         filters,
        'carburants':      CARBURANTS,
    })

@receptionniste_required
def rec_mouvements_vehicule(request, vehicule_id):
    """AJAX — mouvements d'un véhicule."""
    v = get_object_or_404(Vehicule, id=vehicule_id)
    base = EnregistrementEntree.objects.filter(vehicule=v)

    # CORRIGÉ : total sur tout l'historique (avant : plafonné à 20 par le slice)
    stats = base.aggregate(
        total_passages=Count('id'),
        reparations=Count('id', filter=Q(motif='REPARATION')),
    )
    mouvements = [{
        'numero': e.numero,
        'motif': e.get_motif_display(),
        'statut': e.statut,
        'date_entree': fmt_dt(e.date_entree),
        'date_sortie': fmt_dt(e.date_sortie) or None,
        'duree': None,
        'reception': getattr(getattr(e, 'reception', None), 'numero', None),
    } for e in base.select_related('reception').order_by('-date_entree')[:20]]

    return JsonResponse({'mouvements': mouvements, 'statut_presence': v.statut_presence, 'stats': stats})


@receptionniste_required
def rec_modifier_vehicule(request, vehicule_id):
    v = get_object_or_404(Vehicule, id=vehicule_id)

    def render_form():
        urls = [default_storage.url(p) if p else '' for p in photos_list(v)]
        return render(request, 'reception/vehicules/modifier.html', {
            'v': v,
            'carburants': CARBURANTS,
            'transmissions': TRANSMISSIONS,
            'photo_urls_json': json.dumps(urls),
        })

    if request.method != 'POST':
        return render_form()

    # Propriétaire vérifié AVANT toute modification
    client = Client.objects.filter(id=post_str(request, 'client')).first() if post_str(request, 'client') else None
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
    log_action(request, ActionType.MODIFICATION, 'RECEPTIONNISTE', v)
    messages.success(request, f"Véhicule {v.immatriculation} mis à jour.")
    return redirect('rec_vehicules')


@receptionniste_required
def export_vehicules_pdf(request):
    today = timezone.localdate()
    qs = (
        Vehicule.objects.select_related('client')
        .annotate(nb_passages=Count('entrees', distinct=True))
        .order_by('immatriculation')
    )
    # CORRIGÉ : le filtre présence utilisait en_local / en_atelier, qui sont des
    # @property → FieldError (erreur 500) dès qu'on filtrait par présence.
    qs = filtrer_vehicules(request, qs, today)

    return pdf_response(generer_pdf_liste_vehicules(qs, today), "vehicules.pdf")


# ════════════════════════════════════════════════════════════════════════
#  CLIENTS
# ════════════════════════════════════════════════════════════════════════

@receptionniste_required
def rec_clients(request):
  
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
    return render(request, 'reception/clients/liste.html', {
        'clients': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'villes': villes, 
        'filtre_type': filtre_type,
        'filters': {'q': q, 'ville': ville, 'avec_vehicule': avec_vehicule},
    })


@receptionniste_required
def rec_detail_client(request, client_id):
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

    return render(request, 'reception/clients/detail.html', {
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


@receptionniste_required
def rec_modifier_client(request, client_id):
    c = get_object_or_404(Client, id=client_id)

    if request.method == 'POST':
        c.nom = post_str(request, 'nom', c.nom)
        c.prenom = post_str(request, 'prenom', c.prenom or '')
        c.telephone = post_str(request, 'telephone', c.telephone)
        c.telephone2 = post_str(request, 'telephone2', c.telephone2 or '')
        c.email = post_str(request, 'email', c.email or '')
        c.adresse = post_str(request, 'adresse', c.adresse or '')
        c.ville = post_str(request, 'ville', c.ville or '')
        c.ninea = post_str(request, 'ninea', c.ninea or '')
        c.save()
        log_action(request, ActionType.MODIFICATION, 'RECEPTION', c)
        messages.success(request, f"Client {c} mis à jour.")
        return redirect('rec_clients')

    return render(request, 'reception/clients/modifier.html', {'c': c})


@receptionniste_required
def export_client_pdf(request):
    qs = filtrer_clients(request, Client.objects.annotate(
        nb_vehicules=Count('vehicules', distinct=True),
        nb_passages=Count('vehicules__entrees', distinct=True),
    ).order_by('nom'))

    avec_vehicule = request.GET.get('avec_vehicule', '').strip()
    if avec_vehicule == '1':
        qs = qs.filter(nb_vehicules__gt=0)
    elif avec_vehicule == '0':
        qs = qs.filter(nb_vehicules=0)


    return pdf_response(generer_pdf_liste_clients(qs), "clients.pdf")






def _fiche(client_id, **params):
    url = reverse('rec_detail_client', args=[client_id])
    if params:
        url += '?' + '&'.join(f"{k}={v}" for k, v in params.items())
    return url

# ─── Centres (= clients enfants) ─────────────────────────────────────────
def _retour_fiche(client_id):
    return redirect(_fiche(client_id, tab='vehicules'))


def _erreurs(form):
    return " ".join(e for errs in form.errors.values() for e in errs)


@receptionniste_required
@require_POST
def creer_centre(request, client_id):
    parent = get_object_or_404(Client, id=client_id)
    if not parent.peut_avoir_centres:
        messages.error(request, "Seule une entreprise (qui n'est pas elle-même un centre) peut avoir des centres.")
        return _retour_fiche(parent.entreprise.id)
    form = CentreForm(request.POST, parent=parent)
    if form.is_valid():
        centre = form.save(commit=False)
        centre.created_by = request.user
        centre.save()
        log_action(request, ActionType.CREATION, 'RECEPTION', centre)
        messages.success(request, f"Centre « {centre.nom} » créé.")
    else:
        messages.error(request, f"Centre non créé : {_erreurs(form)}")
    return _retour_fiche(parent.id)


@receptionniste_required
@require_POST
def modifier_centre(request, centre_id):
    centre = get_object_or_404(Client.objects.select_related('parent'), id=centre_id, parent__isnull=False)
    form = CentreForm(request.POST, instance=centre, parent=centre.parent)
    if form.is_valid():
        form.save()
        log_action(request, ActionType.MODIFICATION, 'RECEPTION', centre)
        messages.success(request, f"Centre « {centre.nom} » modifié.")
    else:
        messages.error(request, f"Centre non modifié : {_erreurs(form)}")
    return _retour_fiche(centre.parent_id)


@receptionniste_required
def supprimer_centre(request, centre_id):
    centre = get_object_or_404(Client, id=centre_id, parent__isnull=False)
    parent_id, nom = centre.parent_id, centre.nom
    nb = centre.vehicules.count()
    if nb:
        # Supprimer un client supprime ses véhicules en cascade : on bloque.
        messages.error(request, f"Impossible de supprimer « {nom} » : {nb} véhicule(s) "
                                f"y sont encore rattachés. Déplace-les d'abord.")
    else:
        log_action(request, ActionType.SUPPRESSION, 'RECEPTION', details={'centre': nom, 'id': str(centre.id)})
        centre.delete()
        messages.success(request, f"Centre « {nom} » supprimé.")
    return _retour_fiche(parent_id)

