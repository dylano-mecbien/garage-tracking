"""
Endpoints AJAX : autocomplétions, création rapide de demandeur.
"""
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.choices import MotifEntree
from apps.accounts.decorators import guerite_required
from apps.accounts.models import Demandeur, User
from apps.guerite.models import EnregistrementEntree
from apps.reception.models import StatutVehicule
from apps.vehicules.models import Client, Vehicule

from ._utils import fmt_dt


@guerite_required
def api_vehicules(request):
    q = request.GET.get('q', '').strip()
    en_cours = request.GET.get('en_cours', '')

    qs = Vehicule.objects.select_related('client').filter(is_active=True)
    if q:
        qs = qs.filter(
            Q(immatriculation__icontains=q) | Q(marque__icontains=q) | Q(modele__icontains=q)
            | Q(client__nom__icontains=q) | Q(client__prenom__icontains=q)
            | Q(client__telephone__icontains=q)
        )
    if en_cours == '1':
        # CORRIGÉ : filtré en base, avant le [:12] (avant : filtré après → moins de 12 résultats)
        qs = qs.filter(entrees__statut='EN_COURS').distinct()

    # CORRIGÉ : 1 requête pour toutes les entrées actives (avant : 1 requête par véhicule)
    qs = qs.prefetch_related(Prefetch(
        'entrees',
        queryset=EnregistrementEntree.objects.filter(statut='EN_COURS').order_by('-date_entree'),
        to_attr='entrees_actives',
    )).order_by('immatriculation')

    results = []
    for v in qs[:12]:
        active = v.entrees_actives[0] if v.entrees_actives else None
        results.append({
            'id': str(v.id),
            'immatriculation': v.immatriculation,
            'marque': v.marque,
            'modele': v.modele,
            'annee': v.annee,
            'couleur': v.couleur or '',
            'client': str(v.client) if v.client else '—',
            'telephone': getattr(v.client, 'telephone', '') or '',
            'en_cours': bool(active),
            'date_entree': fmt_dt(active.date_entree) if active else '',
        })
    return JsonResponse({'results': results})


@guerite_required
def api_entrees_vehicule(request):
    vehicule_id = request.GET.get('vehicule_id', '').strip()
    if not vehicule_id:
        return JsonResponse({'entrees': []})

    entrees = EnregistrementEntree.objects.filter(
        vehicule_id=vehicule_id,
        statut='EN_COURS',
        motif='REPARATION',
        reception__isnull=True,
    ).order_by('-date_entree')

    return JsonResponse({'entrees': [{
        'id': str(e.id),
        'numero': e.numero,
        'motif': e.get_motif_display(),
        'date_entree': fmt_dt(e.date_entree),
    } for e in entrees]})


@login_required  # AJOUTÉ : accessible sans connexion avant
def autocomplete_vehicules_presents(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    entrees = (
        EnregistrementEntree.objects
        .filter(vehicule__immatriculation__icontains=q)
        .exclude(motif=MotifEntree.VISITE)
        .exclude(bon_sortie__isnull=False)
        .exclude(statut=StatutVehicule.SORTI)  # AJOUTÉ : ce que le commentaire d'origine annonçait
        .select_related('vehicule', 'vehicule__client', 'conducteur')
        .order_by('-date_entree')[:30]
    )

    results, vus = [], set()
    for e in entrees:
        v = e.vehicule
        if v.id in vus:  # AJOUTÉ : un véhicule n'apparaît qu'une fois
            continue
        vus.add(v.id)
        results.append({
            'id': v.id,
            'immatriculation': v.immatriculation,
            'client_nom': v.client.nom if v.client else '',
            'conducteur_nom': f"{e.conducteur.nom} {e.conducteur.prenom}".strip() if e.conducteur else '',
        })
        if len(results) == 15:
            break
    return JsonResponse({'results': results})


@login_required  # AJOUTÉ
def autocomplete_vehicules_reception(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    entrees = (
        EnregistrementEntree.objects
        .filter(date_sortie__isnull=True, motif=MotifEntree.REPARATION, reception__isnull=True)
        .filter(
            Q(vehicule__immatriculation__icontains=q) | Q(vehicule__marque__icontains=q)
            | Q(vehicule__modele__icontains=q) | Q(vehicule__client__nom__icontains=q)
        )
        .select_related('vehicule', 'vehicule__client', 'conducteur')
        .order_by('-date_entree')[:15]
    )

    results = []
    for e in entrees:
        v, client = e.vehicule, e.vehicule.client
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
            'date_entree': fmt_dt(e.date_entree),
        })
    return JsonResponse({'results': results})


@guerite_required
def autocomplete_demandeur(request):
    """Recherche fusionnée Client + Employé + Demandeur, avec `exact_match`."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': [], 'exact_match': False})

    results = [{
        'source': 'CLIENT', 'id': str(c.id), 'nom': c.nom,
        'numero': c.telephone or '', 'detail': 'Client',
    } for c in Client.objects.filter(Q(nom__icontains=q) | Q(telephone__icontains=q))[:8]]

    results += [{
        'source': 'EMPLOYE', 'id': str(e.id), 'nom': e.full_name,
        'numero': getattr(e, 'telephone', '') or e.matricule or '',
        'detail': e.get_role_display(),
    } for e in User.objects.filter(is_active=True).filter(
        Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(matricule__icontains=q))[:8]]

    results += [{
        'source': 'DEMANDEUR', 'id': str(d.id), 'nom': d.nom,
        'numero': d.numero, 'detail': d.description or 'Demandeur',
    } for d in Demandeur.objects.filter(Q(nom__icontains=q) | Q(numero__icontains=q))[:8]]

    q_norm = q.lower()
    exact_match = any((r['nom'] or '').strip().lower() == q_norm for r in results)
    return JsonResponse({'results': results[:15], 'exact_match': exact_match})


@guerite_required
@require_POST
def creer_demandeur_ajax(request):
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
        return JsonResponse({'success': False,
                             'error': "Ce numéro est déjà associé à un demandeur existant."}, status=400)

    d = Demandeur.objects.create(nom=nom, numero=numero, description=description)
    return JsonResponse({
        'success': True, 'id': str(d.id), 'nom': d.nom,
        'numero': d.numero, 'detail': d.description or 'Demandeur',
    })
