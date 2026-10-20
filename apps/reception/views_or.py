"""
apps/reception/views_or.py

Création de l'Ordre de Réparation depuis la réception.
Règle : le réceptionniste ne peut créer l'OR que si aucun OR n'existe
encore pour cette réception (empêche les doublons une fois que
l'atelier a commencé son travail — dès qu'une fiche de contrôle existe,
un OR existe forcément déjà).
Un OR distinct est créé pour CHAQUE atelier sélectionné : chaque
responsable d'atelier ne voit et ne traite que son propre OR.
"""
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from apps.accounts.choices import ActionType
from apps.accounts.decorators import receptionniste_required
from apps.atelier.views_fiches import _get_rec
from apps.audit.service import log_action
from apps.reception.models import Reception, StatutVehicule
from apps.atelier.models import Atelier, FicheControle, FicheTechnique, OrdreReparation, UrgenceOR
from apps.reception.pdf_fiche import generer_pdf_fiche_controle, generer_pdf_fiche_technique





# ══════════════════════════════════════════════════════════════════
#  ORDRE DE RÉPARATION — créé depuis la fiche technique (réceptionniste)
# ══════════════════════════════════════════════════════════════════
@receptionniste_required
def creer_or_depuis_fiche_technique(request, rec_id):
    rec = _get_rec(rec_id)
    entree = rec.entree
    v = rec.vehicule

    # ── Fiche technique de cette entrée ──
    ft = getattr(entree, 'fiche_technique', None)
    if ft is not None and hasattr(ft, 'terminee') and not ft.terminee:
        ft = None

    # ── OR déjà existant ? ──
    if hasattr(entree, 'ordre_reparation') and entree.ordre_reparation:
        messages.warning(request, "Un ordre de réparation existe déjà pour cette entrée.")
        return redirect('detail_reception', rec_id=rec.id)

    ateliers = Atelier.objects.filter(is_active=True).order_by('nom')

    # ── Dernière fiche technique terminée de ce véhicule ──
    derniere_ft = (
        FicheTechnique.objects
        .filter(entree__vehicule=v)
        .exclude(pk=getattr(ft, 'pk', None))
        .order_by('-date_creation')
        .first()
    )

    # ── ?ft_id=... → utiliser une fiche historique ──
    ft_choisie_id = request.GET.get('ft_id', '').strip()
    if ft_choisie_id:
        candidate = FicheTechnique.objects.filter(
            pk=ft_choisie_id,
            entree__vehicule=v,
        ).first()
        if candidate:
            ft = candidate

    if request.method == 'POST':
        ateliers_ids  = [i for i in request.POST.get('ateliers_ids', '').split(',') if i]
        description   = request.POST.get('description_travaux', '').strip()
        urgence       = request.POST.get('urgence', 'NORMAL')
        date_fin_str  = request.POST.get('date_fin_prevue', '').strip()
        duree_h       = int(request.POST.get('duree_heures', '0') or 0)
        duree_m       = int(request.POST.get('duree_minutes', '0') or 0)
        duree_minutes = duree_h * 60 + duree_m

        # ── Validations ──
        errors = []
        if not ateliers_ids:
            errors.append("Sélectionnez au moins un atelier.")
        if not description:
            errors.append("La description des travaux est obligatoire.")
        if duree_minutes <= 0:
            errors.append("La durée estimée doit être supérieure à 0.")
        if not date_fin_str:
            errors.append("La date de fin prévue est obligatoire.")

        # Parsing date
        date_fin = None
        if date_fin_str:
            from datetime import datetime
            try:
                date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append("Date de fin invalide.")

        if errors:
            return render(request, 'reception/creer_or_fiche_technique.html', {
                'rec': rec,
                'ft': ft,
                'derniere_ft': derniere_ft,
                'ateliers': ateliers,
                'error': ' '.join(errors),
                'description_prefill': description,
            })

        # ── Création ──
        from django.db import transaction
        with transaction.atomic():
            or_obj = OrdreReparation.objects.create(
                vehicule=rec.vehicule,
                description_travaux=description,
                urgence=urgence,
                reception=rec,
                date_fin_prevue=date_fin,
                duree_fin_prevu=duree_minutes,     # ← durée prévue en minutes
                duree_fin_reel=0,                  # ← initialisé à 0
                created_by=request.user,
            )
            or_obj.ateliers.set(
                Atelier.objects.filter(id__in=ateliers_ids, is_active=True)
            )

            rec.statut = StatutVehicule.REPARATION_EN_COURS
            rec.save(update_fields=['statut'])

        noms = ', '.join(or_obj.ateliers.values_list('nom', flat=True))
        messages.success(
            request,
            f"✅ Ordre de réparation {or_obj.numero} envoyé à : {noms}.",
        )
        return redirect('detail_reception', rec_id=rec.id)

    # ── Prefill depuis la fiche ──
    description_prefill = ''
    if ft:
        description_prefill = "\n\n".join(filter(None, [
            getattr(ft, 'diagnostic', None) or getattr(ft, 'commentaires', None),
            getattr(ft, 'pieces_recommandees', None),
            getattr(ft, 'observations', None),
        ]))

    return render(request, 'reception/creer_or_fiche_technique.html', {
        'rec': rec,
        'ft': ft,
        'derniere_ft': derniere_ft,
        'ateliers': ateliers,
        'description_prefill': description_prefill,
    })




def _reponse_pdf(request, pdf, nom_fichier):
    resp = HttpResponse(pdf, content_type='application/pdf')
    mode = 'inline' if request.GET.get('inline') else 'attachment'
    resp['Content-Disposition'] = f'{mode}; filename="{nom_fichier}"'
    return resp



def pdf_fiche_technique(request, fiche_id):
    fiche = get_object_or_404(FicheTechnique.objects.select_related('entree', 'cree_par'), id=fiche_id)
    try:
        pdf = generer_pdf_fiche_technique(fiche)
        log_action(request, ActionType.TELECHARGEMENT, 'ATELIER', fiche)
        numero = fiche.numero_fiche or str(fiche.id).split('-')[0]
        return _reponse_pdf(request, pdf, f"fiche-diagnostic-{numero}.pdf")
    except Exception as e:
        messages.error(request, f"Erreur génération PDF: {e}")
        return redirect('detail_fiche_technique', fiche_id=fiche_id)   # ← adapte le nom d'URL



def pdf_fiche_controle(request, fiche_id):
    fiche = get_object_or_404(FicheControle.objects.select_related('entree', 'inspecte_par'), id=fiche_id)
    try:
        pdf = generer_pdf_fiche_controle(fiche)
        log_action(request, ActionType.TELECHARGEMENT, 'ATELIER', fiche)
        ref = fiche.immatriculation or str(fiche.id).split('-')[0]
        return _reponse_pdf(request, pdf, f"fiche-entree-sortie-{ref}.pdf".replace(' ', '-'))
    except Exception as e:
        messages.error(request, f"Erreur génération PDF: {e}")
        return redirect('detail_fiche_controle', fiche_id=fiche_id) 

    

@receptionniste_required
def choisir_ateliers_rec(request, rec_id):
    rec = get_object_or_404(
        Reception.objects.select_related('vehicule', 'vehicule__client'),
        id=rec_id
    )

    # ── Garde-fou anti-doublon ──────────────────────────────────
    if rec.ordres_reparation.exists():
        messages.warning(
            request,
            "Un ordre de réparation existe déjà pour cette réception — "
            "il n'est plus possible d'en recréer un tant que celui-ci est en cours."
        )
        return redirect('detail_reception', rec_id=rec.id)

    ateliers = Atelier.objects.filter(is_active=True).order_by('nom')

    if request.method == 'POST':
        ateliers_ids = request.POST.get('ateliers_ids', '').strip()
        description  = request.POST.get('description_travaux', '').strip()
        urgence      = request.POST.get('urgence', UrgenceOR.NORMAL)
        date_fin     = request.POST.get('date_fin_prevue', '').strip() or None

        ids = [i for i in ateliers_ids.split(',') if i]
        if not ids:
            return render(request, 'reception/choisir_ateliers.html', {
                'rec': rec, 'ateliers': ateliers,
                'error': "Sélectionnez au moins un atelier.",
            })
        if not description:
            return render(request, 'reception/choisir_ateliers.html', {
                'rec': rec, 'ateliers': ateliers,
                'error': "La description des travaux est obligatoire.",
            })

        # Re-vérifier le garde-fou juste avant écriture (concurrence)
        if rec.ordres_reparation.exists():
            messages.warning(request, "Un OR existe déjà pour cette réception.")
            return redirect('detail_reception', rec_id=rec.id)

        crees = []
        for atelier_id in ids:
            atelier = Atelier.objects.filter(id=atelier_id, is_active=True).first()
            if not atelier:
                continue
            or_obj = OrdreReparation.objects.create(
                reception=rec,
                vehicule=rec.entree.vehicule,
                atelier=atelier,
                description_travaux=description,
                urgence=urgence,
                date_fin_prevue=date_fin or None,
                created_by=request.user,
            )
            crees.append(or_obj)

        if not crees:
            return render(request, 'reception/choisir_ateliers.html', {
                'rec': rec, 'ateliers': ateliers,
                'error': "Aucun atelier valide sélectionné.",
            })

        rec.statut = StatutVehicule.EN_ATELIER
        rec.save(update_fields=['statut', 'updated_at'])

        noms = ', '.join(o.atelier.nom for o in crees)
        messages.success(
            request,
            f"✅ Véhicule envoyé vers : {noms}. "
            "Chaque responsable d'atelier doit maintenant créer sa fiche de contrôle."
        )
        return redirect('detail_reception', rec_id=rec.id)

    return render(request, 'reception/choisir_ateliers.html', {
        'rec': rec, 'ateliers': ateliers,
    })
