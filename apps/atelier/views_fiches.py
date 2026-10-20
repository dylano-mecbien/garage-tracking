"""
apps/atelier/views_fiches.py

Flux :
  1. Entrée : le technicien remplit la fiche de contrôle en 3 pages (Suivant / Suivant / Terminer)
     → retour sur le détail réception.
  2. Le client valide la réception : sa signature est enregistrée SUR la fiche de contrôle.
  3. L'atelier remplit ensuite la fiche technique (3 pages, même principe).
  4. Sortie : voir views_controle_sortie.py (prérempli depuis l'entrée, vérification
     des différences, présentation au client, signature, archivage).
"""
import json

from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.reception.models import Reception, StatutVehicule
from apps.accounts.decorators import technicien_required
from apps.accounts.decorators_atelier import resp_atelier_required
from .forms import (FicheControleStepForm, FicheTechniqueStepForm, CONTROLE_ETAPES,
                    CONTROLE_CATEGORIES_FORM, TECHNIQUE_ETAPES, TECHNIQUE_CATEGORIES_FORM, build_fields_meta,
                    save_signature_to_storage)
from .models import FicheControle, FicheTechnique


def _get_rec(rec_id):
    return get_object_or_404(
        Reception.objects.select_related('entree', 'vehicule', 'vehicule__client'), id=rec_id)


def _date_locale(d):
    if d is None:
        return None
    if hasattr(d, 'hour'):                       # datetime → date locale
        return (timezone.localtime(d) if timezone.is_aware(d) else d).date()
    return d


# ══════════════════════════════════════════════════════════════════
#  FICHE DE CONTRÔLE (ENTRÉE) — 3 pages
# ══════════════════════════════════════════════════════════════════
@resp_atelier_required
def creer_fiche_controle_etape(request, rec_id, step):
    if step not in (1, 2, 3):
        raise Http404

    rec = _get_rec(rec_id)
    if rec.entree_id is None:
        messages.error(request, "Cette réception n'est liée à aucune entrée guérite. "
                                "Impossible de créer la fiche de contrôle.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    instance = FicheControle.objects.filter(entree_id=rec.entree_id).first()
    v, c = rec.vehicule, rec.vehicule.client
    nom_tech = request.user.get_full_name() or str(request.user)

    if step > 1 and instance is None:
        messages.error(request, "Commencez par la page 1.")
        return redirect('creer_fiche_controle_etape', rec_id=rec.id, step=1)

    # Une fois signée par le client, l'état d'entrée n'est plus modifiable
    if instance and instance.signee_client:
        messages.info(request, "La fiche d'entrée est signée par le client : elle n'est plus modifiable.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    if request.method == 'POST':
        form = FicheControleStepForm(step, request.POST, instance=instance)
        if form.is_valid():
            fiche = form.save(commit=False)
            fiche.entree_id = rec.entree_id
            if instance is None:
                fiche.inspecte_par = request.user
            fiche.save()

            if step < 3:
                return redirect('creer_fiche_controle_etape', rec_id=rec.id, step=step + 1)

            messages.success(request, "✅ Fiche de contrôle d'entrée terminée. "
                                      "Le client doit maintenant valider la réception.")
            return redirect('detail_reception_atelier', rec_id=rec.id)
    else:
        initial = None
        if instance is None and step == 1:
            initial = {
                'immatriculation': v.immatriculation,
                'marque': v.marque,
                'modele': v.modele,
                'entree_le': _date_locale(rec.entree.date_entree),
                'telephone': getattr(c, 'telephone', ''),
                'kilometrage': getattr(rec.entree, 'kilometrage_entree', 0) or 0,
            }
        elif step == 3:
            initial = {'nom_technicien': (instance.nom_technicien if instance else '') or nom_tech}
        form = FicheControleStepForm(step, instance=instance, initial=initial)

    return render(request, 'atelier/fiche_wizard.html', {
        'rec': rec,
        'form': form,
        'fields': build_fields_meta(form, CONTROLE_CATEGORIES_FORM),
        'titre': "Fiche de contrôle — entrée",
        'step': step,
        'total': 3,
        'etapes': [t for t, _ in CONTROLE_ETAPES],
        'step_title': CONTROLE_ETAPES[step - 1][0],
        'url_name': 'creer_fiche_controle_etape',
        'quitter_url_name': 'detail_reception_atelier',
        'degats_json': json.dumps(instance.points_degats_carrosserie if instance else []),
    })


# ══════════════════════════════════════════════════════════════════
#  FICHE TECHNIQUE — 3 pages (possible seulement après la signature du client)
# ══════════════════════════════════════════════════════════════════
@resp_atelier_required
def creer_fiche_technique_etape(request, rec_id, step):
    if step not in (1, 2, 3):
        raise Http404

    rec = _get_rec(rec_id)
    if rec.entree_id is None:
        messages.error(request, "Aucune entrée liée à cette réception.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    instance = FicheTechnique.objects.filter(entree_id=rec.entree_id).first()
    v = rec.vehicule
    c = v.client if v else None
    nom_tech = request.user.get_full_name() or str(request.user)

    if step > 1 and instance is None:
        messages.error(request, "Commencez par la page 1.")
        return redirect('creer_fiche_technique_etape', rec_id=rec.id, step=1)

    initial = {}
    if instance is None and step == 1 and v:
        initial = {
            'nom_client': str(c) if c else '',
            'immatriculation': (v.immatriculation or '').upper(),
            'vehicule': f"{v.marque or ''} {v.modele or ''}".strip(),
            'entree_le': _date_locale(rec.entree.date_entree),
            'kilometrage': getattr(rec.entree, 'kilometrage_entree', 0) or 0,
        }

    if request.method == 'POST':
        form = FicheTechniqueStepForm(step, request.POST, instance=instance)
        if form.is_valid():
            fiche = form.save(commit=False)
            if step == 1 and instance is None:
                # À la création, l'en-tête vient toujours du véhicule
                for name in ('nom_client', 'immatriculation', 'vehicule', 'entree_le'):
                    setattr(fiche, name, initial.get(name) or getattr(fiche, name))

            fiche.entree_id = rec.entree_id
            if instance is None:
                fiche.cree_par = request.user
                fiche.numero_fiche = f"FT-{timezone.now():%Y%m}-{FicheTechnique.objects.count() + 1:04d}"
            fiche.save()

            if step < 3:
                return redirect('creer_fiche_technique_etape', rec_id=rec.id, step=step + 1)

            if rec.statut in (StatutVehicule.FICHE_CONTROLE, StatutVehicule.RAPPORT_FAIT):
                rec.statut = StatutVehicule.FICHE_TECHNIQUE
                rec.save(update_fields=['statut', 'updated_at'])

            messages.success(request, "✅ Fiche technique terminée. En attente de l'ordre de réparation.")
            return redirect('detail_reception_atelier', rec_id=rec.id)
    else:
        if step == 3:
            initial = {'nom_controleur': (instance.nom_controleur if instance else '') or nom_tech}
        form = FicheTechniqueStepForm(step, instance=instance, initial=initial or None)

    return render(request, 'atelier/fiche_wizard.html', {
        'rec': rec,
        'form': form,
        'fields': build_fields_meta(form, TECHNIQUE_CATEGORIES_FORM),
        'titre': "Fiche technique",
        'step': step,
        'total': 3,
        'etapes': [t for t, _ in TECHNIQUE_ETAPES],
        'step_title': TECHNIQUE_ETAPES[step - 1][0],
        'url_name': 'creer_fiche_technique_etape',
        'quitter_url_name': 'detail_reception_atelier',
        'degats_json': None,
    })


# ══════════════════════════════════════════════════════════════════
#  SIGNATURE DU CLIENT À L'ENTRÉE — bouton « Valider la réception »
#  (la signature de sortie se fait sur l'écran comparatif : views_controle_sortie.py)
# ══════════════════════════════════════════════════════════════════
@technicien_required
def signer_fiche_controle(request, rec_id):
    rec = _get_rec(rec_id)
    fc = getattr(rec.entree, 'fiche_controle', None) if rec.entree_id else None

    if fc is None or not fc.terminee:
        messages.error(request, "La fiche de contrôle n'est pas encore terminée.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    if fc.signee_client:
        if fc.sortie_signee:
            messages.info(request, "Les signatures d'entrée et de sortie sont déjà enregistrées.")
            return redirect('detail_reception_atelier', rec_id=rec.id)
        # La signature de sortie passe par le contrôle de sortie
        return redirect('controle_sortie_client', rec_id=rec.id)

    ctx = {'rec': rec, 'fiche': fc, 'type_signature': 'avant'}

    if request.method == 'POST':
        nom = request.POST.get('nom_client', '').strip()
        signature = request.POST.get('signature', '').strip()
        if not nom or not signature:
            return render(request, 'atelier/resp/signer_fiche_controle.html', {
                **ctx, 'nom_defaut': nom, 'error': "Le nom et la signature du client sont obligatoires."})

        chemin = save_signature_to_storage(signature, folder='signatures/clients', field_name='client_avant')
        if not chemin:
            return render(request, 'atelier/resp/signer_fiche_controle.html', {
                **ctx, 'nom_defaut': nom, 'error': "Signature invalide ou trop volumineuse. Réessayez."})

        fc.nom_client_avant = nom
        fc.signature_client_avant = chemin
        fc.save(update_fields=['nom_client_avant', 'signature_client_avant'])

        if rec.statut == StatutVehicule.RAPPORT_FAIT:
            rec.statut = StatutVehicule.FICHE_CONTROLE
            rec.save(update_fields=['statut'])
        messages.success(request, "✅ Réception validée : signature du client enregistrée. "
                                  "L'atelier peut faire la fiche technique.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    return render(request, 'atelier/resp/signer_fiche_controle.html', {
        **ctx, 'nom_defaut': str(rec.entree.conducteur)})
