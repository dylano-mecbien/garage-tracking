"""
apps/atelier/views_controle_sortie.py — contrôle de SORTIE du véhicule.

  1. controle_sortie_saisie       : seuls les éléments cochés à l'entrée, affichés vides, à recocher
  2. controle_sortie_verification : pour chaque différence, « Erreur de saisie » renvoie sur
                                    controle_sortie_recocher (l'élément est vidé et recoché),
                                    « Confirmer » demande une explication ; puis « Enregistrer la fiche »
  3. controle_sortie_client       : écran présenté au client (Avant / Maintenant), signature
                                    → archivage dans FicheControle, suppression de la ligne temporaire
"""
import json

from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.reception.models import Reception
from apps.accounts.decorators_atelier import resp_atelier_required
from . import controle
from .forms import (ControleSortieForm, SORTIE_CATEGORIES_FORM,
                    build_fields_meta, save_signature_to_storage)
from .models import FicheControleTemporaire

Statut = FicheControleTemporaire.Statut

# Statuts de réception où le contrôle de sortie peut commencer.
# Mets None pour ne pas filtrer sur le statut.
STATUTS_SORTIE = {'TRAVAUX_TERMINES', 'BON_SORTIE_FAIT'}

# Qui fait le contrôle de sortie : même décorateur que la fiche d'entrée.
controle_required = resp_atelier_required


def _charger(request, rec_id):
    """→ (rec, fiche, None) ou (rec, None, redirection) si le contrôle de sortie est impossible."""
    rec = get_object_or_404(
        Reception.objects.select_related('entree', 'vehicule', 'vehicule__client'), id=rec_id)
    retour = redirect('detail_reception_atelier', rec_id=rec.id)
    fiche = getattr(rec.entree, 'fiche_controle', None) if rec.entree_id else None

    if fiche is None or not fiche.signee_client:
        messages.error(request, "La fiche de contrôle d'entrée doit être terminée et signée par le client.")
        return rec, None, retour
    if fiche.sortie_signee:
        messages.info(request, "Le contrôle de sortie est déjà signé par le client.")
        return rec, None, redirect('voir_fiche_controle', rec_id=rec.id)
    if STATUTS_SORTIE and rec.statut not in STATUTS_SORTIE and not hasattr(fiche, 'controle_sortie_temp'):
        messages.error(request, "Le contrôle de sortie se fait quand les travaux sont terminés.")
        return rec, None, retour
    return rec, fiche, None


def _temp(fiche):
    return FicheControleTemporaire.objects.filter(fiche_controle=fiche).first()


# ══════════════════════════════════════════════════════════════════
#  1. SAISIE — uniquement les éléments cochés à l'entrée, vides
# ══════════════════════════════════════════════════════════════════
def _cases_oui_non(champs):
    """Cases à cocher (cric, manivelle, clé de roue) : à afficher vides tant qu'elles ne sont pas recochées."""
    return [n for n in champs
            if FicheControleTemporaire._meta.get_field(n).get_internal_type() == 'BooleanField'
            and not FicheControleTemporaire._meta.get_field(n).null]


def _rendu(request, rec, fiche, temp, form, titre, url_post, intro, bouton):
    return render(request, 'atelier/fiche_wizard.html', {
        'rec': rec,
        'form': form,
        'fields': build_fields_meta(form, SORTIE_CATEGORIES_FORM),
        'titre': titre,
        'step': 1, 'total': 1,
        'etapes': ["Recocher les éléments", "Vérification des différences", "Signature du client"],
        'step_title': titre,
        'quitter_url_name': 'detail_reception_atelier',
        'degats_json': json.dumps(temp.points_degats_carrosserie or []),
        'mode_sortie': True,
        'intro_sortie': intro,
        'km_entree': fiche.kilometrage,
        'km_sortie': temp.kilometrage_sortie,
        'bouton_final': bouton,
    })


@controle_required
def controle_sortie_saisie(request, rec_id):
    rec, fiche, stop = _charger(request, rec_id)
    if stop:
        return stop

    temp, cree = controle.demarrer_sortie(fiche, request.user)
    champs = controle.champs_coches(fiche)
    premiere_fois = temp.kilometrage_sortie is None
    vides = _cases_oui_non(champs) if premiere_fois else _cases_oui_non(controle.a_recocher(temp))

    if request.method == 'POST':
        form = ControleSortieForm(champs, request.POST, instance=temp, kilometrage_entree=fiche.kilometrage)
        if form.is_valid():
            temp = form.save(commit=False)
            controle.recoche(temp, champs)
            temp.statut = Statut.VERIFICATION
            temp.date_validation = None
            temp.save()
            return redirect('controle_sortie_verification', rec_id=rec.id)
    else:
        form = ControleSortieForm(champs, instance=temp, kilometrage_entree=fiche.kilometrage, vides=vides)

    return _rendu(
        request, rec, fiche, temp, form, "Contrôle de sortie", None,
        f"Seuls les {len(champs)} éléments cochés à l'entrée sont affichés, vides : recochez chacun "
        f"selon l'état actuel du véhicule.",
        "Comparer avec l'entrée →")


@controle_required
def controle_sortie_recocher(request, rec_id):
    """Erreur de saisie : le technicien recoche seulement les éléments signalés."""
    rec, fiche, stop = _charger(request, rec_id)
    if stop:
        return stop
    temp = _temp(fiche)
    if temp is None or temp.kilometrage_sortie is None:
        return redirect('controle_sortie_saisie', rec_id=rec.id)
    champs = [n for n in controle.champs_coches(fiche) if n in set(controle.a_recocher(temp))]
    if not champs:
        return redirect('controle_sortie_verification', rec_id=rec.id)

    if request.method == 'POST':
        form = ControleSortieForm(champs, request.POST, instance=temp, avec_km=False)
        if form.is_valid():
            temp = form.save(commit=False)
            controle.recoche(temp, champs)
            temp.statut = Statut.VERIFICATION
            temp.save()
            return redirect('controle_sortie_verification', rec_id=rec.id)
    else:
        form = ControleSortieForm(champs, instance=temp, avec_km=False, vides=_cases_oui_non(champs))

    return _rendu(
        request, rec, fiche, temp, form, "Erreur de saisie : recocher", None,
        "Recochez correctement le ou les éléments signalés comme erreur de saisie.",
        "Revenir à la vérification →")


# ══════════════════════════════════════════════════════════════════
#  2. VÉRIFICATION DES DIFFÉRENCES
# ══════════════════════════════════════════════════════════════════
@controle_required
def controle_sortie_verification(request, rec_id):
    rec, fiche, stop = _charger(request, rec_id)
    if stop:
        return stop
    temp = _temp(fiche)
    if temp is None or temp.kilometrage_sortie is None:
        return redirect('controle_sortie_saisie', rec_id=rec.id)
    if controle.a_recocher(temp) and request.method == 'GET':
        return redirect('controle_sortie_recocher', rec_id=rec.id)

    if request.method == 'POST':
        action = request.POST.get('action')
        champ = request.POST.get('champ', '')
        if action in ('erreur', 'confirmer', 'annuler') and champ not in controle.champs_coches(fiche):
            messages.error(request, "Élément inconnu.")
        elif action == 'erreur':
            controle.erreur_saisie(temp, champ)
            messages.info(request, f"« {controle.libelle(champ)} » : erreur de saisie, recochez l'élément.")
            return redirect('controle_sortie_recocher', rec_id=rec.id)
        elif action == 'confirmer':
            explication = request.POST.get('explication', '')
            if not explication.strip():
                messages.error(request, f"« {controle.libelle(champ)} » : l'explication est obligatoire "
                                        f"pour confirmer une différence.")
            else:
                controle.confirmer(temp, champ, explication, request.user)
        elif action == 'annuler':
            controle.annuler_confirmation(temp, champ)
        elif action == 'valider':
            if controle.valider_technicien(fiche, temp):
                messages.success(request, "✅ Contrôle de sortie enregistré. Présentez l'écran au client.")
                return redirect('controle_sortie_client', rec_id=rec.id)
            messages.error(request, "Toutes les différences doivent être vérifiées avant d'enregistrer la fiche.")
        return redirect('controle_sortie_verification', rec_id=rec.id)

    diffs = controle.differences(fiche, temp)
    restantes = sum(1 for d in diffs if not d['confirmee'])
    return render(request, 'atelier/controle_sortie/verification.html', {
        'rec': rec, 'fiche': fiche, 'temp': temp,
        'diffs': diffs, 'restantes': restantes, 'resolues': len(diffs) - restantes,
        'km_entree': fiche.kilometrage, 'km_sortie': temp.kilometrage_sortie,
    })


# ══════════════════════════════════════════════════════════════════
#  3. PRÉSENTATION AU CLIENT ET SIGNATURE → ARCHIVAGE
# ══════════════════════════════════════════════════════════════════
@controle_required
def controle_sortie_client(request, rec_id):
    rec, fiche, stop = _charger(request, rec_id)
    if stop:
        return stop
    temp = _temp(fiche)
    if temp is None:
        return redirect('controle_sortie_saisie', rec_id=rec.id)
    if temp.statut != Statut.A_SIGNER:
        messages.error(request, "Le technicien doit d'abord vérifier et enregistrer le contrôle de sortie.")
        return redirect('controle_sortie_verification', rec_id=rec.id)

    diffs = controle.differences(fiche, temp)
    ctx = {
        'rec': rec, 'fiche': fiche, 'temp': temp,
        'sections': controle.comparatif(fiche, controle.etat_de(temp), diffs),
        'nb_diff': len(diffs),
        'km_entree': fiche.kilometrage, 'km_sortie': temp.kilometrage_sortie,
        'degats_avant': fiche.points_degats_carrosserie or [],
        'degats_apres': temp.points_degats_carrosserie or [],
        'nom_defaut': fiche.nom_client_avant or str(getattr(rec.entree, 'conducteur', '') or ''),
    }

    if request.method == 'POST':
        nom = request.POST.get('nom_client', '').strip()
        signature = request.POST.get('signature', '').strip()
        lu = request.POST.get('lu') == '1'
        if not nom or not signature or not lu:
            return render(request, 'atelier/controle_sortie/presentation_client.html', {
                **ctx, 'nom_defaut': nom,
                'error': "Le nom, la case « J'ai pris connaissance » et la signature du client sont obligatoires."})

        chemin = save_signature_to_storage(signature, folder='signatures/clients', field_name='client_apres')
        if not chemin:
            return render(request, 'atelier/controle_sortie/presentation_client.html', {
                **ctx, 'nom_defaut': nom, 'error': "Signature invalide ou trop volumineuse. Réessayez."})

        if controle.archiver(fiche.pk, nom, chemin) is None:
            messages.error(request, "Le contrôle de sortie a changé entre-temps : vérifiez-le à nouveau.")
            return redirect('controle_sortie_verification', rec_id=rec.id)

        messages.success(request, "✅ Contrôle de sortie signé par le client et archivé. Le véhicule peut être libéré.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    return render(request, 'atelier/controle_sortie/presentation_client.html', ctx)


@controle_required
@require_POST
def controle_sortie_abandonner(request, rec_id):
    """Supprime le contrôle de sortie en cours (la fiche d'entrée n'est pas touchée)."""
    rec, fiche, stop = _charger(request, rec_id)
    if stop:
        return stop
    FicheControleTemporaire.objects.filter(fiche_controle=fiche).delete()
    messages.info(request, "Contrôle de sortie abandonné.")
    return redirect('detail_reception_atelier', rec_id=rec.id)
