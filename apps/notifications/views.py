"""
Vues admin pour gérer les destinataires email.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from apps.accounts.decorators import admin_required
from apps.audit.service import log_action
from apps.audit.models import ActionType
from apps.notifications.models import DestinataireEmail
from apps.notifications.services import envoyer_email_test


@admin_required
def destinataires_email(request):
    """Page principale : liste + création + modification + suppression."""

    if request.method == 'POST':
        action  = request.POST.get('action')
        dest_id = request.POST.get('dest_id')

        # ── Créer ──────────────────────────────────────────────
        if action == 'creer':
            email = request.POST.get('email', '').strip().lower()
            nom   = request.POST.get('nom', '').strip()
            actif = request.POST.get('actif') == 'on'

            if not email:
                messages.error(request, "L'adresse email est obligatoire.")
            elif DestinataireEmail.objects.filter(email=email).exists():
                messages.error(request, f"L'adresse {email} existe déjà.")
            else:
                d = DestinataireEmail.objects.create(email=email, nom=nom or None, actif=actif)
                log_action(request, ActionType.CREATION, 'CONFIG', d)
                messages.success(request, f"✅ Destinataire {email} ajouté avec succès.")

        # ── Modifier ────────────────────────────────────────────
        elif action == 'modifier' and dest_id:
            d     = get_object_or_404(DestinataireEmail, id=dest_id)
            email = request.POST.get('email', '').strip().lower()
            nom   = request.POST.get('nom', '').strip()
            actif = request.POST.get('actif') == 'on'

            if not email:
                messages.error(request, "L'adresse email est obligatoire.")
            elif DestinataireEmail.objects.filter(email=email).exclude(id=dest_id).exists():
                messages.error(request, f"L'adresse {email} est déjà utilisée.")
            else:
                d.email = email
                d.nom   = nom or None
                d.actif = actif
                d.save()
                log_action(request, ActionType.MODIFICATION, 'CONFIG', d)
                messages.success(request, f"✅ Destinataire {email} mis à jour.")

        # ── Toggle actif/inactif ────────────────────────────────
        elif action == 'toggle' and dest_id:
            d       = get_object_or_404(DestinataireEmail, id=dest_id)
            d.actif = not d.actif
            d.save(update_fields=['actif'])
            etat = "activé" if d.actif else "désactivé"
            log_action(request, ActionType.MODIFICATION, 'CONFIG', d, {'actif': d.actif})
            messages.success(request, f"Destinataire {d.email} {etat}.")

        # ── Supprimer ───────────────────────────────────────────
        elif action == 'supprimer' and dest_id:
            d = get_object_or_404(DestinataireEmail, id=dest_id)
            email = d.email
            d.delete()
            log_action(request, ActionType.SUPPRESSION, 'CONFIG', details={'email': email})
            messages.success(request, f"🗑 Destinataire {email} supprimé.")

        return redirect('destinataires_email')

    # GET
    destinataires = DestinataireEmail.objects.all()
    return render(request, 'admin_custom/destinataires_email.html', {
        'destinataires': destinataires,
        'nb_actifs':    destinataires.filter(actif=True).count(),
        'nb_inactifs':  destinataires.filter(actif=False).count(),
    })


@admin_required
def test_email_bon_sortie(request):
    """Endpoint AJAX pour envoyer un email de test."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'})

    ok, msg = envoyer_email_test()
    if ok:
        return JsonResponse({'success': True, 'message': msg})
    return JsonResponse({'success': False, 'error': msg})