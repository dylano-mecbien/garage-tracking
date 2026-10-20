"""
Endpoints AJAX : autocomplétions + créations rapides (client, conducteur).
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.reception.views._utils import get_or_none
from apps.vehicules.models import Client, Conducteur, Marque, Modele, Vehicule

from ._utils import TYPES_CLIENT, json_body, jstr

MIN_CARACTERES = 2


def _detail(*parts):
    return ' — '.join(p for p in parts if p)


def _conducteur_json(c):
    return {
        'id': str(c.id),
        'nom': f"{c.prenom or ''} {c.nom or ''}".strip(),
        'detail': _detail(c.telephone,
                          f"Permis: {c.permis}" if c.permis else '',
                          f"Cat. {c.categorie_permis}" if c.categorie_permis else ''),
        'is_client': False,
    }


def _client_json(c):
    if c.type_client == 'PARTICULIER':
        nom = f"{c.prenom} {c.nom}".strip() if c.prenom else c.nom
        detail = _detail(c.telephone, c.ville or 'Particulier')
    else:
        nom = c.nom
        detail = _detail(c.telephone, f"Entreprise{' | ' + c.ninea if c.ninea else ''}")
    return {'id': str(c.id), 'nom': nom, 'detail': detail}


# ─── Autocomplétions (toutes protégées par login : AJOUTÉ) ───────────────
@login_required
def autocomplete_vehicules(request):
    q = request.GET.get('q', '').strip()
    if len(q) < MIN_CARACTERES:
        return JsonResponse({'results': []})
    qs = (Vehicule.objects.filter(immatriculation__icontains=q)
          .select_related('client').order_by('immatriculation')[:10])
    return JsonResponse({'results': [{
        'id': v.id,
        'immatriculation': v.immatriculation,
        'marque': v.marque,
        'modele': v.modele,
        'client': str(v.client) if v.client else '',
    } for v in qs]})


@login_required
def autocomplete_inventaires(request):
    """Chauffeurs / conducteurs : nom, prénom, téléphone."""
    q = request.GET.get('q', '').strip()
    if len(q) < MIN_CARACTERES:
        return JsonResponse({'results': []})
    qs = (Conducteur.objects
          .filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q))
          .order_by('nom', 'prenom')[:15])
    return JsonResponse({'results': [{
        'id': str(c.id),
        'nom': c.nom or '',
        'prenom': c.prenom or '',
        'label': f"{c.prenom or ''} {c.nom or ''}".strip() or str(c),
        'telephone': c.telephone or '',
    } for c in qs]})


@login_required
def autocomplete_conducteurs(request):
    """Conducteurs d'abord, complétés par les clients particuliers (à convertir)."""
    q = request.GET.get('q', '').strip()
    limite = 10

    conducteurs = Conducteur.objects.all()
    if q:
        conducteurs = conducteurs.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q)
            | Q(cni__icontains=q) | Q(permis__icontains=q))
    results = [_conducteur_json(c) for c in conducteurs[:limite]]

    reste = limite - len(results)
    if reste > 0:
        clients = Client.objects.filter(is_active=True, type_client='PARTICULIER')
        if q:
            clients = clients.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q))
        for c in clients[:reste]:
            results.append({
                'id': f"client_{c.id}",  # identifiant distinct pour le front
                'client_id': c.id,
                'nom': f"{c.prenom or ''} {c.nom or ''}".strip(),
                'prenom': c.prenom or '',
                'nom_famille': c.nom or '',
                'telephone': c.telephone or '',
                'cni': getattr(c, 'cni', '') or '',
                'detail': _detail("Client Particulier (À créer)", c.telephone),
                'is_client': True,  # le JS doit créer un conducteur
            })
    return JsonResponse({'results': results})


@login_required
def autocomplete_clients(request):
    q = request.GET.get('q', '').strip()
    type_client = request.GET.get('type', '')

    qs = Client.objects.filter(is_active=True)
    if type_client in TYPES_CLIENT:
        qs = qs.filter(type_client=type_client)
    if q:
        # AJOUTÉ : recherche aussi par téléphone (réflexe courant à la guérite)
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(telephone__icontains=q))
    return JsonResponse({'results': [_client_json(c) for c in qs[:10]]})


@login_required
def autocomplete_marques(request):
    q = request.GET.get('q', '').strip()
    if len(q) < MIN_CARACTERES:
        return JsonResponse({'results': []})
    return JsonResponse({'results': [
        {'id': m.id, 'nom': m.nom} for m in Marque.objects.filter(nom__icontains=q).order_by('nom')[:15]
    ]})


@login_required
def autocomplete_modeles(request):
    q = request.GET.get('q', '').strip()
    marque = request.GET.get('marque', '').strip()
    qs = Modele.objects.filter(nom__icontains=q)
    if marque:
        qs = qs.filter(marque__nom__icontains=marque)
    return JsonResponse({'results': [{'nom': m.nom} for m in qs.order_by('nom')[:10]]})


# ─── Créations rapides ───────────────────────────────────────────────────
@login_required  # AJOUTÉ : un visiteur anonyme pouvait créer des clients
def creer_client_ajax(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

    data = json_body(request)
    if data is None:
        return JsonResponse({'success': False, 'error': 'Données invalides'})

    nom, telephone = jstr(data, 'nom'), jstr(data, 'telephone')
    if not nom or not telephone:
        return JsonResponse({'success': False, 'error': 'Nom et téléphone obligatoires'})

    # CORRIGÉ : .first() au lieu de exists() + get() (plantait s'il y avait 2 clients
    # avec le même numéro, et faisait 2 requêtes)
    existant = Client.objects.filter(telephone=telephone).first()
    if existant:
        return JsonResponse({'success': True, 'id': str(existant.id), 'nom': str(existant),
                             'detail': _detail(existant.telephone, existant.ville)})

    type_client = jstr(data, 'type_client', 'PARTICULIER')
    if type_client not in TYPES_CLIENT:  # AJOUTÉ : valeur validée
        type_client = 'PARTICULIER'

    client = Client.objects.create(
        type_client=type_client,
        nom=nom,
        telephone=telephone,
        created_by=request.user,
        **{k: jstr(data, k) for k in ('prenom', 'nom_correspondant', 'telephone2',
                                      'email', 'adresse', 'ville', 'ninea')},
    )
    log_action(request, ActionType.CREATION, 'GUERITE', client)
    return JsonResponse({'success': True, 'id': str(client.id), 'nom': str(client),
                         'detail': _detail(client.telephone, client.ville or type_client)})


@login_required
@require_POST
def creer_conducteur_ajax(request):
    data = json_body(request)
    if data is None:
        return JsonResponse({'success': False, 'error': 'Données invalides.'}, status=400)

    nom, telephone = jstr(data, 'nom'), jstr(data, 'telephone')
    if not nom or not telephone:
        return JsonResponse({'success': False, 'error': 'Le nom et le téléphone sont obligatoires.'})

    # AJOUTÉ : pas de doublon sur le téléphone → on renvoie le conducteur existant
    existant = Conducteur.objects.filter(telephone=telephone).first()
    if existant:
        return JsonResponse({'success': True, **_conducteur_json(existant)})

    client = None
    if data.get('client_id'):
        # CORRIGÉ : réponse JSON (avant : page HTML 404 renvoyée au JavaScript)
        client = get_or_none(Client.objects, id=data['client_id'])
        if client is None:
            return JsonResponse({'success': False, 'error': 'Client introuvable.'}, status=404)

    conducteur = Conducteur.objects.create(
        nom=nom,
        telephone=telephone,
        client=client,
        created_by=request.user,
        **{k: jstr(data, k) for k in ('prenom', 'telephone2', 'cni', 'permis', 'categorie_permis')},
    )
    log_action(request, ActionType.CREATION, 'GUERITE', conducteur)  # AJOUTÉ
    return JsonResponse({'success': True, **_conducteur_json(conducteur)})
