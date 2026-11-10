"""
Bons de sortie (véhicule, direct, divers).
"""
from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.choices import EtatBon
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.models import BonSortie, EnregistrementEntree, StatutVehicule, TypeBon
from apps.notifications.hook import notifier_bon_sortie_cree
from apps.reception.forms import BonSortieForm
from apps.reception.views import _gen_qr, paginate_queryset
from apps.reception.views._utils import a_champ
from apps.reception.views.bons import _champ_etat, _etat, _notifier_si_pas_admin, peut_modifier

from ..decorators import admin_required
from ..models import Role
from ._utils import post_str, vehicules_presents_json


@admin_required
def liste_bons_sortie(request):
    qs = BonSortie.objects.select_related(
        'vehicule', 'vehicule__client', 'cree_par', 'valide_par'
    ).order_by('-created_at')

    f = {k: request.GET.get(k, '').strip()
         for k in ('q', 'type', 'etat', 'periode', 'date_debut', 'date_fin')}
    f['sort'] = request.GET.get('sort', 'date')

    if f['q']:
        q = f['q']
        qs = qs.filter(
            Q(numero__icontains=q) | Q(nom_demandeur__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(Origine_demande__icontains=q) | Q(observations__icontains=q)
        )
    if f['type']:
        qs = qs.filter(types=f['type'])
    if f['etat']:
        qs = qs.filter(etats=f['etat'])

    now = timezone.localtime()
    periode = f['periode']
    if periode == 'today':
        qs = qs.filter(created_at__date=now.date())
    elif periode == 'week':
        qs = qs.filter(created_at__gte=now - timedelta(days=7))
    elif periode == 'month':
        qs = qs.filter(created_at__year=now.year, created_at__month=now.month)
    elif periode == 'custom':
        if f['date_debut']:
            qs = qs.filter(created_at__date__gte=f['date_debut'])
        if f['date_fin']:
            qs = qs.filter(created_at__date__lte=f['date_fin'])

    if f['sort'] == 'numero':
        qs = qs.order_by('numero')

    # 1 requête au lieu de 5
    stats = BonSortie.objects.aggregate(
        total=Count('id'),
        valides=Count('id', filter=Q(etats='VALIDER')),
        en_attente=Count('id', filter=~Q(etats='VALIDER')),
        vehicules=Count('id', filter=Q(types='VEHICULE')),
        divers=Count('id', filter=Q(types='DIVERS')),
    )

    page_obj = paginate_queryset(request, qs, per_page=25)
    return render(request, 'admin_custom/bons/bons_sortie_liste_admin.html', {
        'bons': page_obj, 'page_obj': page_obj, 'stats': stats, 'filters': f,
    })

@admin_required
def creer_bon_sortie(request, rec_id):
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
            # Rattacher le bon à la réception si elle existe
            if reception is not None:
                bon.reception = reception
            bon.save()

            # Le statut SORTI sera appliqué par la guérite, pas ici.
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
            log_action(request, ActionType.CREATION, 'RECEPTION', bon)

        messages.success(request, f"Bon de sortie {bon.numero} créé.")
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    vehicles_data, vehicles_json = vehicules_presents_json()
    return render(request, 'admin_custom/bons/creer_bon_sortie.html', {
        'form': form,
        'reception': enreg,
        'vehicles_data': vehicles_data,
        'vehicles_json': vehicles_json,
        'sortie_directe': bool(rapport and rapport.decision == 'SORTIE_DIRECTE'),
    })


@admin_required
def creer_bon_sortie_direct(request):
    """Bon de sortie créé directement, sans réception préalable."""
    if request.method == 'POST':
        vehicule_id = request.POST.get('vehicule_id')

        # On ne peut créer un bon que pour un véhicule actuellement présent
        entree = (
            EnregistrementEntree.objects
            .exclude(statut=StatutVehicule.SORTI)
            .filter(vehicule_id=vehicule_id)
            .select_related('vehicule')
            .order_by('-id')
            .first()
        ) if vehicule_id else None

        if not vehicule_id:
            messages.error(request, "Veuillez sélectionner un véhicule.")
        elif entree is None:
            messages.error(request, "Ce véhicule n'est pas présent sur le site.")
        else:
            # ── Réception liée à l'entrée active (si elle existe) ──
            reception = getattr(entree, 'reception', None)

            with transaction.atomic():
                bon = BonSortie.objects.create(
                    types=TypeBon.VEHICULE,
                    vehicule=entree.vehicule,
                    reception=reception,  # None si pas de réception
                    nom_demandeur=post_str(request, 'nom_demandeur'),
                    observations=post_str(request, 'observations'),
                    cree_par=request.user,
                )
                entree.bon_sortie = bon
                entree.save(update_fields=['bon_sortie'])

                # Mettre à jour la réception associée
                if reception is not None:
                    reception.statut = StatutVehicule.BON_SORTIE_FAIT
                    champs = ['statut']
                    if a_champ(reception, 'date_sortie'):
                        reception.date_sortie = timezone.now()
                        champs.append('date_sortie')
                    reception.save(update_fields=champs)

                _gen_qr(bon)
                log_action(request, ActionType.CREATION, 'GUERITE', bon)

            messages.success(request, f"Bon de sortie {bon.numero} créé.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    vehicles_data, vehicles_json = vehicules_presents_json()
    return render(request, 'admin_custom/bons/creer_bon_sortie_admin.html', {
        'vehicles_data': vehicles_data,
        'vehicles_json': vehicles_json,
        'form': BonSortieForm(),
        'reception': None,
    })



@admin_required
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
            # Utile seulement si admin_required laisse passer d'autres rôles
            if request.user.role not in (Role.SUPER_RECEPTIONNISTE, Role.ADMIN):
                notifier_bon_sortie_cree(bon)
            log_action(request, ActionType.CREATION, 'GUERITE', bon, {'type': 'DIVERS'})
            messages.success(request, f"Bon de sortie {bon.numero} créé avec succès.")
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    return render(request, 'admin_custom/bons/creer_divers_admin.html')





@admin_required
def modifier_bon_admin_vehicule(request, bon_id):
    """Modifier un bon de sortie tant qu'il est CRÉÉ ou REFUSÉ.
 
    Le véhicule n'est pas modifiable (il est lié à l'enregistrement d'entrée) :
    on modifie le demandeur et les observations. Un bon REFUSÉ qui est corrigé
    repasse à l'état CRÉER pour être de nouveau traité.
    """
    bon = get_object_or_404(
        BonSortie.objects.select_related('vehicule', 'vehicule__client', 'reception'),
        id=bon_id,
    )
 
    if not peut_modifier(bon):
        messages.error(
            request,
            f"Le bon {bon.numero} ne peut plus être modifié (état : {_etat(bon)}).")
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)
 
    etait_refuse = _etat(bon) == EtatBon.REFUSER
    vehicule_origine = bon.vehicule
 
    form = BonSortieForm(request.POST or None, instance=bon)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            bon = form.save(commit=False)
            bon.vehicule = vehicule_origine          # le véhicule ne change jamais ici
            if etait_refuse:
                setattr(bon, _champ_etat(bon), EtatBon.CREER)
                if a_champ(bon, 'motif_refus'):
                    bon.motif_refus = ''
            bon.save()
 
        if etait_refuse:
            # Le bon repart dans le circuit : on prévient comme à la création
            _notifier_si_pas_admin(request, bon)
        log_action(request, getattr(ActionType, 'MODIFICATION', ActionType.CREATION),
                   'RECEPTION', bon)
        messages.success(
            request,
            f"Bon de sortie {bon.numero} modifié"
            + (" et renvoyé pour validation." if etait_refuse else "."))
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)
 
    vehicles_data, vehicles_json = vehicules_presents_json()
    return render(request, 'admin_custom/bons/creer_bon_sortie.html', {
        'form': form,
        'bon': bon,                      # active le mode « modification » du template
        'bon_refuse': etait_refuse,
        'reception': None,
        'vehicles_data': vehicles_data,
        'vehicles_json': vehicles_json,
    })





@admin_required  # ou @guerite_required selon ton accès
def modifier_bon_admin_divers(request, bon_id):
    """Modifier un bon DIVERS tant qu'il est CRÉER ou REFUSER."""
    bon = get_object_or_404(BonSortie, id=bon_id, types='DIVERS')

    if not peut_modifier(bon):
        messages.error(
            request,
            f"Le bon {bon.numero} ne peut plus être modifié (état : {_etat(bon)})."
        )
        return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    etait_refuse = _etat(bon) == EtatBon.REFUSER

    if request.method == 'POST':
        nom_demandeur = post_str(request, 'nom_demandeur')
        observations = post_str(request, 'observations')

        if not nom_demandeur:
            messages.error(request, "Veuillez sélectionner un demandeur.")
        elif not observations:
            messages.error(request, "Veuillez saisir au moins une ligne (article).")
        else:
            with transaction.atomic():
                bon.nom_demandeur = nom_demandeur
                bon.observations = observations
                if etait_refuse:
                    setattr(bon, _champ_etat(bon), EtatBon.CREER)
                    if a_champ(bon, 'motif_refus'):
                        bon.motif_refus = ''
                    if a_champ(bon, 'refuse_par'):
                        bon.refuse_par = None
                    if a_champ(bon, 'date_refus'):
                        bon.date_refus = None
                bon.save()

                if etait_refuse:
                    _notifier_si_pas_admin(request, bon)

                log_action(
                    request,
                    getattr(ActionType, 'MODIFICATION', ActionType.CREATION),
                    'RECEPTION',
                    bon,
                )

            messages.success(
                request,
                f"Bon de sortie {bon.numero} modifié"
                + (" et renvoyé pour validation." if etait_refuse else ".")
            )
            return redirect('detail_bon_sortie_guerite', bon_id=bon.id)

    return render(request, 'admin_custom/bons/creer_divers_admin.html', {
        'bon': bon,
        'bon_refuse': etait_refuse,
        'mode_edition': True,
    })
