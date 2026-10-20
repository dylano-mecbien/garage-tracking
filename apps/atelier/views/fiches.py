"""
Fiches de contrôle et fiches techniques (rec_id = id de l'OrdreReparation).
"""
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.decorators_atelier import resp_atelier_required
from apps.atelier.models import FicheControle, FicheTechnique, OrdreReparation
from apps.audit.models import ActionType
from apps.audit.service import log_action

from ._utils import (
    _entree_from_or, atelier_requis, get_or_none, passer_or_en_cours,
    post_decimal, post_int, post_str,
)


@resp_atelier_required
@atelier_requis
def creer_fiche_controle(request, rec_id):
    """rec_id = id OrdreReparation."""
    # 1 requête au lieu de 2 (existence + appartenance à l'atelier)
    or_obj = get_or_none(
        OrdreReparation.objects.select_related('vehicule', 'reception'),
        id=rec_id, ateliers=request.atelier,
    )
    if or_obj is None:
        messages.error(request, "Ordre de réparation introuvable ou hors de votre atelier.")
        return redirect('dashboard_atelier')

    entree = _entree_from_or(or_obj)
    if entree is None:
        messages.error(request, "Aucune entrée guérite liée à cette réception.")
        return redirect('detail_or_atelier', or_id=rec_id)

    fiche = FicheControle.objects.filter(entree=entree).first()

    if request.method == 'POST':
        km = post_int(request, 'kilometrage')

        if fiche:
            fiche.kilometrage = km or fiche.kilometrage
            fiche.etat_general = request.POST.get('etat_general', fiche.etat_general)
            fiche.defauts_observes = post_str(request, 'defauts_observes')
            fiche.commentaires = post_str(request, 'commentaires')
            fiche.travail_a_effectuer = post_str(request, 'travail_a_effectuer', fiche.travail_a_effectuer or '')
            fiche.save()
            action, msg = ActionType.MODIFICATION, "✅ Fiche de contrôle mise à jour."
        else:
            with transaction.atomic():
                fiche = FicheControle.objects.create(
                    entree=entree,
                    immatriculation=or_obj.vehicule.immatriculation,
                    kilometrage=km,
                    etat_general=request.POST.get('etat_general', 'BON'),
                    defauts_observes=post_str(request, 'defauts_observes'),
                    commentaires=post_str(request, 'commentaires'),
                    travail_a_effectuer=post_str(request, 'travail_a_effectuer'),
                    inspecte_par=request.user,
                )
                passer_or_en_cours(request, or_obj)  # désormais tracé dans l'audit
            action, msg = ActionType.CREATION, "✅ Fiche de contrôle créée."

        log_action(request, action, 'ATELIER', fiche, {'or': or_obj.numero, 'type': 'fiche_controle'})
        messages.success(request, msg)
        return redirect('detail_or_atelier', or_id=rec_id)

    return render(request, 'atelier/resp/fiche_controle.html', {
        'or': or_obj, 'entree': entree, 'fiche': fiche,
    })


CHAMPS_MONTANTS = ('temps_estime_heures', 'main_oeuvre_estimee', 'pieces_estimees')


@resp_atelier_required
@atelier_requis
def creer_fiche_technique(request, rec_id):
    or_obj = get_object_or_404(
        OrdreReparation.objects.select_related('vehicule', 'reception'),
        id=rec_id, ateliers=request.atelier,
    )
    entree = _entree_from_or(or_obj)
    if entree is None:
        messages.error(request, "Aucune entrée guérite liée.")
        return redirect('detail_or_atelier', or_id=rec_id)

    if not FicheControle.objects.filter(entree=entree).exists():
        messages.error(request, "⚠️ La fiche de contrôle doit être créée avant.")
        return redirect('detail_or_atelier', or_id=rec_id)

    fiche = FicheTechnique.objects.filter(entre=entree).first()

    if request.method == 'POST':
        diagnostic = post_str(request, 'diagnostic')
        if not diagnostic:
            messages.error(request, "Le diagnostic est obligatoire.")
            return redirect('creer_fiche_technique', rec_id=rec_id)

        valeurs = {
            'diagnostic': diagnostic,
            'pieces_recommandees': post_str(request, 'pieces_recommandees'),
            'observations': post_str(request, 'observations'),
            # Decimal au lieu de float (pas d'arrondis bizarres) + « 1,5 » accepté
            **{champ: post_decimal(request, champ) for champ in CHAMPS_MONTANTS},
        }

        if fiche:
            for champ, val in valeurs.items():
                setattr(fiche, champ, val)
            fiche.save()
            action, msg = ActionType.MODIFICATION, "✅ Fiche technique mise à jour."
        else:
            fiche = FicheTechnique.objects.create(
                entre=entree,
                immatriculation=or_obj.vehicule.immatriculation,
                cree_par=request.user,
                **valeurs,
            )
            action, msg = ActionType.CREATION, "✅ Fiche technique créée."

        log_action(request, action, 'ATELIER', fiche, {'or': or_obj.numero, 'type': 'fiche_technique'})
        messages.success(request, msg)
        return redirect('detail_or_atelier', or_id=rec_id)

    return render(request, 'atelier/resp/fiche_technique.html', {
        'or': or_obj, 'entree': entree, 'fiche': fiche,
    })
