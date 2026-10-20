"""apps/atelier/views_lecture.py — pages de VISUALISATION (lecture seule) des deux fiches."""
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from apps.reception.models import Reception
from apps.accounts.decorators_atelier import lecture_fiches_required
from . import controle
from .forms import TECHNIQUE_ETAPES, signature_preview_url
from .lecture import construire, CONTROLE_SECTIONS
from .models import FicheControleTemporaire
from .roles import ROLE_ADMIN, ROLE_RECEPTION, ROLE_RESP
from .utils import entree_de, MSG_SANS_ENTREE


def _rec(rec_id):
    return get_object_or_404(Reception.objects.select_related('vehicule', 'vehicule__client'), id=rec_id)


def _back(user, rec):
    from django.urls import reverse
    if user.role in (ROLE_RECEPTION, ROLE_ADMIN):
        return reverse('detail_reception', args=[rec.id])
    if user.role == ROLE_RESP:
        return reverse('dashboard_atelier')
    return ''                                   # technicien : bouton « Retour » = historique du navigateur


@lecture_fiches_required
def voir_fiche_controle(request, rec_id):
    rec = _rec(rec_id)
    entree = entree_de(rec)
    if entree is None:
        messages.error(request, MSG_SANS_ENTREE)
        return redirect(_back(request.user, rec) or '/')
    fiche = getattr(entree, 'fiche_controle', None)
    if fiche is None:
        messages.info(request, "La fiche de contrôle n'a pas encore été créée.")
        return redirect(_back(request.user, rec) or '/')

    sections, defauts = construire(fiche, CONTROLE_SECTIONS)
    signatures = [
        {'role': "Technicien (entrée)", 'nom': fiche.nom_technicien,
         'img': signature_preview_url(fiche.signature_technicien)},
        {'role': "Client — état à l'entrée", 'nom': fiche.nom_client_avant,
         'img': signature_preview_url(fiche.signature_client_avant)},
    ]

    # Contrôle de sortie : archivé (signé) ou en cours
    sortie = None
    if fiche.sortie_signee:
        sortie = {
            'sections': controle.comparatif(fiche, fiche.etat_sortie or {}, fiche.differences_sortie or []),
            'nb_diff': len(fiche.differences_sortie or []),
            'km_entree': fiche.kilometrage, 'km_sortie': fiche.kilometrage_sortie,
            'degats_avant': fiche.points_degats_carrosserie or [],
            'degats_apres': (fiche.etat_sortie or {}).get('points_degats_carrosserie') or [],
            'par': fiche.controle_sortie_par, 'date_controle': fiche.date_controle_sortie,
            'date_signature': fiche.date_signature_sortie,
        }
        signatures.append({'role': "Client — contrôle de sortie", 'nom': fiche.nom_client_apres,
                           'img': signature_preview_url(fiche.signature_client_apres)})
    sortie_en_cours = FicheControleTemporaire.objects.filter(fiche_controle=fiche).first()

    peut_modifier = (request.user.role in (ROLE_RESP, ROLE_ADMIN) and not fiche.signee_client
                     and not hasattr(entree, 'ordre_reparation'))
    return render(request, 'atelier/fiche_voir.html', {
        'rec': rec, 'fiche': fiche, 'titre': "Fiche de contrôle", 'mode': 'controle',
        'sections': sections, 'defauts': defauts, 'signatures': signatures,
        'receptionniste': fiche.nom_receptionniste,
        'auteur': fiche.inspecte_par, 'date': fiche.date_inspection,
        'terminee': fiche.terminee, 'signee_client': fiche.signee_client,
        'degats_json': fiche.points_degats_carrosserie or [],
        'peut_modifier': peut_modifier, 'modifier_url_name': 'creer_fiche_controle_etape',
        'sortie': sortie, 'sortie_en_cours': sortie_en_cours,
        'back_url': _back(request.user, rec),
    })


@lecture_fiches_required
def voir_fiche_technique(request, rec_id):
    rec = _rec(rec_id)
    entree = entree_de(rec)
    if entree is None:
        messages.error(request, MSG_SANS_ENTREE)
        return redirect(_back(request.user, rec) or '/')
    fiche = getattr(entree, 'fiche_technique', None)
    if fiche is None:
        messages.info(request, "La fiche technique n'a pas encore été créée.")
        return redirect(_back(request.user, rec) or '/')

    sections, defauts = construire(fiche, TECHNIQUE_ETAPES)
    signatures = [{'role': "Technicien / contrôleur", 'nom': fiche.nom_controleur,
                   'img': signature_preview_url(fiche.signature_controleur)}]
    peut_modifier = request.user.role in (ROLE_RESP, ROLE_ADMIN) and not hasattr(entree, 'ordre_reparation')
    return render(request, 'atelier/fiche_voir.html', {
        'rec': rec, 'fiche': fiche, 'titre': "Fiche technique", 'mode': 'technique',
        'sections': sections, 'defauts': defauts, 'signatures': signatures,
        'receptionniste': '', 'auteur': fiche.cree_par, 'date': fiche.date_creation,
        'terminee': fiche.terminee, 'signee_client': None, 'degats_json': [],
        'numero_fiche': fiche.numero_fiche,
        'peut_modifier': peut_modifier, 'modifier_url_name': 'creer_fiche_technique_etape',
        'back_url': _back(request.user, rec),
    })
