"""
Bons de sortie : création, liste, détail, validation, PDF.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.choices import TypeBon
from apps.accounts.decorators import guerite_required, receptionniste_required
from apps.accounts.models import Role
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.documents.pdf_generator import generer_pdf_bon_sortie
from apps.guerite.models import BonSortie, EnregistrementEntree
from apps.notifications.hook import notifier_bon_sortie_cree
from apps.reception.forms import BonSortieForm
from apps.reception.models import StatutVehicule
from apps.reception.pdf_bon_liste import generer_pdf_liste_bons
from apps.vehicules.models import Vehicule

from ._utils import (
    _gen_qr, a_champ, filtrer_bons, get_or_none, paginate_queryset, pdf_response,
    post_str, save_signature_from_dataurl, url_liste_bons, vehicules_presents_json,
)


def _notifier_si_pas_admin(request, bon):
    if request.user.role != Role.ADMIN:
        notifier_bon_sortie_cree(bon)


# ─── Liste / détail / PDF ────────────────────────────────────────────────
@guerite_required
def liste_bons_sortie(request):
    qs = filtrer_bons(request, BonSortie.objects.select_related(
        'vehicule', 'vehicule__client', 'cree_par', 'valide_par'
    ).order_by('-created_at'))

    # 1 requête au lieu de 5
    stats = BonSortie.objects.aggregate(
        total=Count('id'),
        valides=Count('id', filter=Q(etats='VALIDER')),
        en_attente=Count('id', filter=~Q(etats='VALIDER')),
        vehicules=Count('id', filter=Q(types='VEHICULE')),
        divers=Count('id', filter=Q(types='DIVERS')),
    )
    filters = {k: request.GET.get(k, '').strip()
               for k in ('q', 'type', 'etat', 'periode', 'date_debut', 'date_fin')}
    filters['sort'] = request.GET.get('sort', 'date')

    page_obj = paginate_queryset(request, qs)
    return render(request, 'reception/bons_sortie_liste.html', {
        'bons': page_obj, 'page_obj': page_obj, 'stats': stats, 'filters': filters,
    })


@receptionniste_required
def detail_bon_sortie(request, bon_id):
    bon = get_object_or_404(
        BonSortie.objects.select_related('vehicule', 'vehicule__client', 'reception'), id=bon_id)
    return render(request, 'reception/detail_bon_sortie.html', {'bon': bon})


@guerite_required
def detail_bon_sortie_guerite(request, bon_id):
    bon = get_object_or_404(
        BonSortie.objects.select_related(
            'vehicule', 'vehicule__client', 'cree_par', 'valide_par', 'reception'),
        id=bon_id,
    )
    return render(request, 'reception/bons_sortie_detail.html', {
        'bon': bon,
        'super': request.user.role in (Role.SUPER_RECEPTIONNISTE, Role.ADMIN),
    })


@login_required  # AJOUTÉ : le PDF était téléchargeable sans connexion
def pdf_bon_sortie(request, bon_id):
    bon = get_object_or_404(BonSortie.objects.select_related('vehicule', 'vehicule__client'), id=bon_id)
    pdf = generer_pdf_bon_sortie(bon)
    log_action(request, ActionType.TELECHARGEMENT, 'RECEPTION', bon)
    return pdf_response(pdf, f"bon-sortie-{bon.numero}.pdf")


@guerite_required
def pdf_bon_sortie_guerite(request, bon_id):
    bon = get_object_or_404(BonSortie.objects.select_related('vehicule', 'vehicule__client'), id=bon_id)
    try:
        pdf = generer_pdf_bon_sortie(bon)
    except Exception as e:
        messages.error(request, f"Erreur génération PDF : {e}")
        return redirect('detail_bon_sortie_guerite', bon_id=bon_id)
    log_action(request, ActionType.TELECHARGEMENT, 'GUERITE', bon)
    return pdf_response(pdf, f"bon-sortie-{bon.numero}.pdf")


@receptionniste_required
def export_bons_pdf(request):
    # Mêmes filtres que la liste (y compris la période) → le PDF = ce qu'on voit
    qs = filtrer_bons(request, BonSortie.objects.select_related(
        'vehicule', 'cree_par', 'valide_par'
    ).order_by('-created_at'))
    return pdf_response(generer_pdf_liste_bons(qs), "bons-sortie.pdf")


# ─── Validation / approbation (signature) ────────────────────────────────
def _assurer_signature(request):
    """S'assure que l'utilisateur a une signature (sinon la prend du canvas).
    Retourne un message d'erreur, ou None si tout va bien."""
    user = request.user
    if user.signature:
        return None
    data = request.POST.get('signature_admin')
    if not data:
        return "Vous devez signer avant de valider."
    if not save_signature_from_dataurl(user, data, 'signature'):
        return "Erreur lors de l'enregistrement de la signature."
    user.save()
    return None


def _signer_bon(request, bon_id, appliquer, verbe, module):
    """Logique commune de validation (divers) et d'approbation (véhicule)."""
    bon = get_object_or_404(BonSortie, id=bon_id)
    if request.method != 'POST':
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    nouvelle_signature = not request.user.signature
    erreur = _assurer_signature(request)
    if erreur:
        messages.error(request, erreur)
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    bon.signature_admin = request.user.signature
    etat = appliquer(bon, request.user, timezone.now())
    bon.save()

    log_action(request, ActionType.CHANGEMENT_STATUT, module, bon, {'etat': etat})
    suite = "Votre signature a été enregistrée." if nouvelle_signature else "(signature existante)"
    messages.success(request, f"Bon {bon.numero} {verbe}. {suite}")
    return redirect(url_liste_bons(request.user))


def _valider(bon, user, now):
    bon.etats = 'VALIDER'
    bon.est_valide = True
    bon.valide_par = user
    bon.date_validation = now
    return 'VALIDER'


def _approuver(bon, user, now):
    bon.etats = 'APPROBATION'
    bon.approuve_par = user
    bon.date_approbation = now
    return 'APPROBATION'


@guerite_required
def valider_bon_sortie_divers(request, bon_id):
    return _signer_bon(request, bon_id, _valider, "validé", 'GUERITE')


@guerite_required
def valider_bon_sortie_vehicule(request, bon_id):
    return _signer_bon(request, bon_id, _approuver, "approuvé", 'ADMIN')


# ─── Création ────────────────────────────────────────────────────────────
@receptionniste_required
def creer_bon_sortie(request, rec_id):
    """rec_id = id de l'ENREGISTREMENT D'ENTRÉE (nom historique conservé pour urls.py)."""
    enreg = get_object_or_404(EnregistrementEntree.objects.select_related('vehicule'), id=rec_id)
    rapport = getattr(enreg, 'rapport', None)
    reception = getattr(enreg, 'reception', None)

    form = BonSortieForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            bon = form.save(commit=False)
            bon.cree_par = request.user
            bon.types = TypeBon.VEHICULE
            if enreg.vehicule:
                bon.vehicule = enreg.vehicule
            bon.save()

            enreg.bon_sortie = bon
            enreg.save(update_fields=['bon_sortie'])

            if reception is not None:
                reception.statut = StatutVehicule.BON_SORTIE_FAIT
                champs = ['statut']
                # CORRIGÉ : date_sortie était affectée mais jamais sauvegardée
                if a_champ(reception, 'date_sortie'):
                    reception.date_sortie = timezone.now()
                    champs.append('date_sortie')
                reception.save(update_fields=champs)

            _gen_qr(bon)

        _notifier_si_pas_admin(request, bon)
        log_action(request, ActionType.CREATION, 'RECEPTION', bon)
        messages.success(request, f"Bon de sortie {bon.numero} créé.")
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    vehicles_data, vehicles_json = vehicules_presents_json()
    return render(request, 'reception/creer_bon_sortie.html', {
        'form': form,
        'rec': enreg,
        'reception': enreg,
        'vehicles_data': vehicles_data,
        'vehicles_json': vehicles_json,
        'sortie_directe': bool(rapport and rapport.decision == 'SORTIE_DIRECTE'),
    })



@guerite_required
def creer_bon_sortie_direct(request):
    """Bon de sortie créé directement depuis la guérite, sans réception."""

    if request.method == 'POST':
        vehicule_id = request.POST.get('vehicule_id')

        # ── Validation ──
        if not vehicule_id:
            messages.error(request, "Veuillez sélectionner un véhicule.")
        else:
            vehicule = Vehicule.objects.filter(id=vehicule_id).first()

            if vehicule is None:
                messages.error(request, "Véhicule introuvable.")
            else:
                # ── Entrée active liée à ce véhicule ──
                entree_active = (
                    EnregistrementEntree.objects
                    .filter(vehicule=vehicule)
                    .exclude(statut=StatutVehicule.SORTI)
                    .order_by('-id')
                    .first()
                )

                # ── Réception liée à l'entrée active (si elle existe) ──
                reception = getattr(entree_active, 'reception', None) if entree_active else None

                # ── Création atomique ──
                with transaction.atomic():
                    bon = BonSortie.objects.create(
                        types=TypeBon.VEHICULE,
                        vehicule=vehicule,
                        nom_demandeur=post_str(request, 'nom_demandeur'),
                        observations=post_str(request, 'observations'),
                        cree_par=request.user,
                    )

                    # Lier le bon à l'entrée active
                    if entree_active is not None:
                        entree_active.bon_sortie = bon
                        entree_active.save(update_fields=['bon_sortie'])

                    # Mettre à jour la réception associée
                    if reception is not None:
                        reception.statut = StatutVehicule.BON_SORTIE_FAIT
                        champs = ['statut']
                        if a_champ(reception, 'date_sortie'):
                            reception.date_sortie = timezone.now()
                            champs.append('date_sortie')
                        reception.save(update_fields=champs)

                    _gen_qr(bon)

                # ── Notifications + audit (hors transaction) ──
                _notifier_si_pas_admin(request, bon)
                log_action(request, ActionType.CREATION, 'GUERITE', bon)

                messages.success(request, f"Bon de sortie {bon.numero} créé.")
                return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    # ── GET (ou POST avec erreur) : afficher le formulaire ──
    vehicles_data, vehicles_json = vehicules_presents_json()

    return render(request, 'reception/creer_bon_sortie.html', {
        'vehicles_data': vehicles_data,
        'vehicles_json': vehicles_json,
        'form':          BonSortieForm(),
        'reception':     None,
    })

@guerite_required
def creer_bon_sortie_divers(request):
    """Bon de sortie divers (articles, matériel…)."""
    if request.method == 'POST':
        nom_demandeur = post_str(request, 'nom_demandeur')
        observations = post_str(request, 'observations')

        if not nom_demandeur:
            messages.error(request, "Veuillez sélectionner un demandeur.")
        elif not observations:
            messages.error(request, "Veuillez saisir au moins une ligne (article) dans les observations.")
        else:
            bon = BonSortie.objects.create(
                types='DIVERS',
                nom_demandeur=nom_demandeur,
                Origine_demande='DIVERS',
                observations=observations,
                cree_par=request.user,
            )
            _notifier_si_pas_admin(request, bon)
            log_action(request, ActionType.CREATION, 'GUERITE', bon, {'type': 'DIVERS'})
            messages.success(request, f"Bon de sortie {bon.numero} créé avec succès.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    return render(request, 'reception/creer_divers.html')
