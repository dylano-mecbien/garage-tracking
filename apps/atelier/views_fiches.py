"""
apps/atelier/views_fiches.py

Flux exact :
  1. Le chef d'atelier remplit la fiche de contrôle en 3 pages (Suivant / Suivant / Terminer)
     → retour automatique sur la page de détail réception.
  2. Sur la page de détail réception, le bouton « Valider la réception » apparaît :
     le client signe → sa signature est enregistrée SUR la fiche de contrôle.
  3. Une fois signée, l'atelier peut remplir la fiche technique (3 pages, même principe)
     → c'est terminé pour l'atelier, qui attend l'ordre de réparation.
  4. Le réceptionniste lit la fiche technique, reprend le diagnostic pour préremplir l'ordre de
     réparation (modifiable), choisit les ateliers et envoie.
"""



import base64
import uuid
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

import json
from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.reception.models import Reception, StatutVehicule
from apps.accounts.decorators import receptionniste_required, technicien_required
from apps.accounts.decorators_atelier import resp_atelier_required
from .forms import (FicheControleStepForm, FicheTechniqueStepForm, CONTROLE_ETAPES,
                    TECHNIQUE_ETAPES, build_fields_meta)
from .models import Atelier, FicheControle, FicheTechnique, OrdreReparation


def _get_rec(rec_id):
    return get_object_or_404(
        Reception.objects.select_related('entree', 'vehicule', 'vehicule__client'), id=rec_id)


# ══════════════════════════════════════════════════════════════════
#  FICHE DE CONTRÔLE — 3 pages
# ══════════════════════════════════════════════════════════════════
@resp_atelier_required
def creer_fiche_controle_etape(request, rec_id, step):
    if step not in (1, 2, 3):
        raise Http404

    rec = _get_rec(rec_id)
    entree = rec.entree_id
    # ⚠️ GARDE : l'entrée guérite doit exister
    if entree is None:
        messages.error(
            request,
            "Cette réception n'est liée à aucune entrée guérite. "
            "Impossible de créer la fiche de contrôle."
        )

    instance = FicheControle.objects.filter(entree_id=rec.entree_id).first()
    v, c = rec.vehicule, rec.vehicule.client
    nom_tech = request.user.get_full_name() or str(request.user)

    if step > 1 and instance is None:
        messages.error(request, "Commencez par la page 1.")
        return redirect('creer_fiche_controle_etape', rec_id=rec.id, step=1)

    
# ── Vérifier que la signature du client est bien présente ──
    signature_ok = bool(
        instance
        and instance.signature_client_avant
        and str(instance.signature_client_avant).strip()
    )

    if signature_ok:
        return redirect('detail_reception_atelier', rec_id=rec.id)
    
    if request.method == 'POST':
        form = FicheControleStepForm(step, request.POST, instance=instance)
        if form.is_valid():
            fiche = form.save(commit=False)
            fiche.entree_id = entree                       # ✅ maintenant non-null
            if instance is None:
                fiche.inspecte_par = request.user
            fiche.save()

            if step < 3:
                return redirect('creer_fiche_controle_etape', rec_id=rec.id, step=step + 1)

            if rec.statut == StatutVehicule.RAPPORT_FAIT:
                
                rec.save(update_fields=['statut', 'updated_at'])
            messages.success(request, "✅ Fiche de réception terminée. Le client doit maintenant valider la réception.")
            return redirect('detail_reception_atelier', rec_id=rec.id)
    else:
        initial = None
        if instance is None and step == 1:
            initial = {
                'immatriculation': v.immatriculation,
                'marque': v.marque,
                'entree_le': rec.entree.date_entree,
                'modele': v.modele,
                'nom_technicien' : nom_tech,
                'telephone': getattr(c, 'telephone', ''),
                'kilometrage': getattr(entree, 'kilometrage_entree', 0) or 0,
            }
        form = FicheControleStepForm(step, instance=instance, initial=initial)
        if step == 3:
                form = FicheControleStepForm(step, instance=instance, initial={
                'nom_technicien': nom_tech,
            })
    return render(request, 'atelier/fiche_wizard.html', {
        'rec': rec,
        'form': form,
        'fields': build_fields_meta(form),
        'titre': "Fiche de réception",
        'step': step,
        'total': 3,
        'step_title': CONTROLE_ETAPES[step - 1][0],
        'url_name': 'creer_fiche_controle_etape',
        'degats_json': json.dumps(instance.points_degats_carrosserie) if instance else '[]',
    })

# ══════════════════════════════════════════════════════════════════
#  FICHE TECHNIQUE — 3 pages (possible seulement après la signature du client)
# ══════════════════════════════════════════════════════════════════
@resp_atelier_required
def creer_fiche_technique_etape(request, rec_id, step):
    if step not in (1, 2, 3):
        raise Http404

    rec = _get_rec(rec_id)
    entree = rec.entree_id  # ← objet, pas l'id
    if entree is None:
        messages.error(request, "Aucune entrée liée à cette réception.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    instance = FicheTechnique.objects.filter(entree_id=rec.entree_id).first()
    # Si le champ s'appelle entree_id : .filter(entree_id=entree.id)

    v = rec.vehicule
    c = v.client if v else None
    nom_tech = request.user.get_full_name() or str(request.user)

    if step > 1 and instance is None:
        messages.error(request, "Commencez par la page 1.")
        return redirect('creer_fiche_technique_etape', rec_id=rec.id, step=1)

    # ── Initial (étape 1, nouvelle fiche) ──
    initial = {}
    if instance is None and step == 1 and v:
        date_entree = rec.entree.date_entree
        if date_entree is not None:
            if timezone.is_aware(date_entree):
                date_entree = timezone.localtime(date_entree).date()
            elif hasattr(date_entree, 'date'):
                date_entree = date_entree.date()

        initial = {
            'nom_client': str(c) if c else '',
            'immatriculation': (v.immatriculation or '').upper(),
            'vehicule': f"{v.marque or ''} {v.modele or ''}".strip(),
            'entree_le': date_entree,
            'nom_controleur': nom_tech,
        }
    
    
    if request.method == 'POST':
        form = FicheTechniqueStepForm(step, request.POST, instance=instance)
        if form.is_valid():
            fiche = form.save(commit=False)

            # Réinjecter les champs disabled (non présents dans POST)
            if step == 1:
                for name in ('nom_client', 'immatriculation', 'vehicule', 'entree_le'):
                    if name in initial and not getattr(fiche, name, None):
                        setattr(fiche, name, initial[name])
                if instance is None:
                    # Toujours forcer depuis le véhicule à la création
                    fiche.nom_client = initial.get('nom_client', '')
                    fiche.immatriculation = initial.get('immatriculation', '')
                    fiche.vehicule = initial.get('vehicule', '')
                    fiche.entree_le = initial.get('entree_le')

            fiche.entree_id = entree  # adapte le nom du champ si besoin
            if instance is None:
                fiche.cree_par = request.user
                fiche.numero_fiche = (
                    f"FT-{timezone.now():%Y%m}-"
                    f"{FicheTechnique.objects.count() + 1:04d}"
                )
            fiche.save()

            if step < 3:
                return redirect(
                    'creer_fiche_technique_etape', rec_id=rec.id, step=step + 1
                )

            if rec.statut in (StatutVehicule.FICHE_CONTROLE, StatutVehicule.RAPPORT_FAIT):
                rec.statut = StatutVehicule.FICHE_TECHNIQUE
                rec.save(update_fields=['statut', 'updated_at'])

            messages.success(
                request,
                "✅ Fiche technique terminée. En attente de l'ordre de réparation.",
            )
            return redirect('detail_reception_atelier', rec_id=rec.id)

        # POST invalide → on garde le form lié (erreurs)
    else:

        if step == 3:
            form_initial = {'nom_controleur': nom_tech}
            # Si une fiche existe déjà, préserver ses valeurs
            if instance and instance.nom_controleur:
                form_initial['nom_controleur'] = instance.nom_controleur
            form = FicheTechniqueStepForm(step, instance=instance, initial=form_initial)
        else:
            form = FicheTechniqueStepForm(
                step, instance=instance, initial=initial or None,
            )

    return render(request, 'atelier/fiche_wizard.html', {
        'rec': rec,
        'form': form,
        'fields': build_fields_meta(form),
        'titre': "Fiche technique",
        'step': step,
        'total': 3,
        'step_title': TECHNIQUE_ETAPES[step - 1][0],
        'url_name': 'creer_fiche_technique_etape',
        'degats_json': None,
    })

# ══════════════════════════════════════════════════════════════════
#  SIGNATURE DU CLIENT — bouton « Valider la réception » (réception)
# ══════════════════════════════════════════════════════════════════


def save_signature_aurl(data_url, folder='signatures', field_name='sig'):
    """
    Convertit un dataURL canvas en fichier image, le sauvegarde dans le storage
    par défaut (local ou MinIO/S3) et retourne le chemin relatif du fichier.

    Args:
        data_url : chaîne base64 commençant par "data:image/..."
        folder   : sous-dossier dans MEDIA_ROOT
        field_name : préfixe du nom de fichier

    Returns:
        str  : chemin relatif du fichier (ex: "signatures/sig_abc123.png")
        None : si la conversion échoue
    """
    if not data_url or not data_url.startswith('data:image'):
        return None

    try:
        # Décoder le dataURL
        header, imgstr = data_url.split(';base64,')
        ext = header.split('/')[-1].lower()
        if ext == 'jpeg':
            ext = 'jpg'

        # Nom de fichier unique
        filename = f"{folder}/{field_name}_{uuid.uuid4().hex[:10]}.{ext}"

        # Contenu binaire
        data = base64.b64decode(imgstr)

        # Sauvegarder dans le storage (local ou MinIO/S3)
        saved_path = default_storage.save(filename, ContentFile(data))

        return saved_path

    except (ValueError, base64.binascii.Error) as e:
        print("Erreur signature (décodage) :", e)
        return None
    except Exception as e:
        print("Erreur signature :", e)
        return None
    
 
@technicien_required
def signer_fiche_controle(request, rec_id):
    rec = _get_rec(rec_id)
    fc = getattr(rec.entree, 'fiche_controle', None)

    if fc is None or not fc.terminee:
        messages.error(request, "La fiche de contrôle n'est pas encore terminée.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    # ── Déterminer quelle signature demander ──
    deja_signe_avant = bool(
        fc.signature_client_avant and str(fc.signature_client_avant).strip()
    )
    deja_signe_apres = bool(
        fc.signature_client_apres and str(fc.signature_client_apres).strip()
    )

    # ── Si les deux signatures sont faites → rien à faire ──
    if deja_signe_avant and deja_signe_apres:
        messages.info(request, "Les deux signatures client sont déjà enregistrées.")
        return redirect('detail_reception_atelier', rec_id=rec.id)

    # ── Choix de la signature à traiter ──
    if not deja_signe_avant:
        type_signature = 'avant'
        champ_nom      = 'nom_client_avant'
        champ_sig      = 'signature_client_avant'
    else:
        type_signature = 'apres'
        champ_nom      = 'nom_client_apres'
        champ_sig      = 'signature_client_apres'

    # ── POST ──
    if request.method == 'POST':
        nom       = request.POST.get('nom_client', '').strip()
        signature = request.POST.get('signature', '').strip()

        if not nom or not signature:
            return render(request, 'atelier/resp/signer_fiche_controle.html', {
                'rec': rec,
                'fiche': fc,
                'nom_defaut': nom,
                'type_signature': type_signature,
                'error': "Le nom et la signature du client sont obligatoires.",
            })

        # ── Enregistrer l'image et récupérer le chemin ──
        chemin = save_signature_aurl(
            signature,
            folder='signatures/clients',
            field_name=f'client_{type_signature}',
        )

        if not chemin:
            return render(request, 'atelier/resp/signer_fiche_controle.html', {
                'rec': rec,
                'fiche': fc,
                'nom_defaut': nom,
                'type_signature': type_signature,
                'error': "Signature invalide ou trop volumineuse. Réessayez.",
            })

        # ── Mettre à jour la bonne signature ──
        setattr(fc, champ_nom, nom)
        setattr(fc, champ_sig, chemin)
        fc.save(update_fields=[champ_nom, champ_sig])

        if type_signature == 'avant':
            if rec.statut == StatutVehicule.RAPPORT_FAIT:
                rec.statut = StatutVehicule.FICHE_CONTROLE   # ou FICHE_TECHNIQUE selon votre logique
                rec.save(update_fields=['statut'])
            messages.success(
                request,
                "✅ Réception validée — signature du client enregistrée. "
                "L'atelier peut faire la fiche technique."
            )
        else:
            messages.success(
                request,
                "✅ Signature finale du client enregistrée. "
                "Le véhicule peut être libéré."
            )
        return redirect('detail_reception_atelier', rec_id=rec.id)

    # ── GET ──
    return render(request, 'atelier/resp/signer_fiche_controle.html', {
        'rec': rec,
        'fiche': fc,
        'nom_defaut': str(rec.vehicule.client),
        'type_signature': type_signature,
    })