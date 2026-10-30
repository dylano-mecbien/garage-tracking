"""
Réceptions, rapports, transferts ateliers, entrées guérite.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Case, Count, IntegerField, Prefetch, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.choices import MotifEntree, StatutReception
from apps.accounts.decorators import guerite_required, receptionniste_required
from apps.atelier.models import OrdreReparation, ReouvertureOR
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.models import BonSortie, EnregistrementEntree
from apps.reception.forms import RapportReceptionForm, TransfertAtelierForm
from apps.reception.models import Reception, StatutVehicule, TransfertAtelier
from apps.vehicules.models import Vehicule

from ._utils import (
    MOTIFS_VALIDES, get_entrees_presentes_filtrees, get_filtered_entrees,
    get_or_none, paginate_queryset, post_str,
)




def _contexte_or_reception(rec):
    """OR d'origine + OR réouverts sur cette réception, et les réouvertures."""
    reouvertures_ici = (
        ReouvertureOR.objects.filter(reception=rec)
        .select_related('ordre_reparation', 'reouvert_par')
        .prefetch_related('taches__techniciens')
    )
    or_list = list(
        OrdreReparation.objects
        .filter(Q(reception=rec) | Q(reouvertures__reception=rec))
        .distinct()
        .select_related('reception')
        .prefetch_related(
            'ateliers',
            Prefetch('reouvertures', queryset=ReouvertureOR.objects.filter(reception=rec),
                     to_attr='reouvertures_ici'),
        )
        .annotate(nb_taches=Count('taches', distinct=True),
                  nb_reouv=Count('reouvertures', distinct=True))
        .order_by('-date_creation')
    )
    for o in or_list:
        # True : OR créé pour cette réception ; False : OR d'une autre réception réouvert ici
        o.est_origine = o.reception_id == rec.id
        o.derniere_reouverture_ici = o.reouvertures_ici[0] if o.reouvertures_ici else None
    return {
        'or_list': or_list,
        'nb_or_origine': sum(o.est_origine for o in or_list),
        'nb_or_reouverts': sum(not o.est_origine for o in or_list),
        'reouvertures_ici': list(reouvertures_ici),
    }
 
 
def _signe(fiche, champ):
    return bool(fiche and str(getattr(fiche, champ, '') or '').strip())


def _ordre_receptions(qs):
    """Fiches (contrôle / technique) en premier, puis réparation, puis le reste."""
    return qs.annotate(
        priorite=Case(
            When(statut=StatutReception.FICHE_CONTROLE, then=0),   # PRESENT_ATELIER
            When(statut=StatutReception.FICHE_TECHNIQUE, then=1),
            When(statut=StatutReception.RAPPORT_FAIT, then=2),
            When(statut=StatutReception.REPARATION_EN_COURS, then=3),
            When(statut=StatutReception.TRAVAUX_TERMINES, then=4),
            When(statut=StatutReception.BON_SORTIE_FAIT, then=5),
            default=9,
            output_field=IntegerField(),
        )
    ).order_by('priorite', '-created_at')



@receptionniste_required
def liste_receptions(request):
    qs = Reception.objects.select_related(
        'vehicule', 'vehicule__client', 'receptionniste'
    )
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()

    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(
            Q(vehicule__immatriculation__icontains=q)
            | Q(numero__icontains=q)
            | Q(vehicule__client__nom__icontains=q)
        )

    qs = _ordre_receptions(qs)
    page_obj = paginate_queryset(request, qs)
    return render(request, 'reception/liste_receptions.html', {
        'receptions': page_obj,
        'page_obj': page_obj,
        'statuts': StatutReception.choices,
        'statut_filter': statut,
    })



@receptionniste_required
def creer_reception(request):
    entree = None
    entree_id = request.GET.get('entree_id')
    if entree_id:
        entree = get_object_or_404(
            EnregistrementEntree.objects.select_related('vehicule'),
            id=entree_id, motif=MotifEntree.REPARATION,
        )
        if hasattr(entree, 'reception'):
            messages.warning(request, "Cette entrée a déjà une réception.")
            return redirect('detail_reception', rec_id=entree.reception.id)

    if request.method != 'POST':
        return render(request, 'reception/creer_reception.html', {'entree': entree})

    entree_id_post = post_str(request, 'entree_id') or post_str(request, 'entree_select')
    vehicule_id_post = post_str(request, 'vehicule_id')
    decision = request.POST.get('decision', 'VERS_ATELIER')
    observations = post_str(request, 'observations')

    error, vehicule = None, None
    if not (vehicule_id_post or entree_id_post):
        error = "Sélectionnez un véhicule ou une entrée guérite."
    elif not observations:
        error = "Les observations sont obligatoires."
    elif entree_id_post:
        entree = get_or_none(EnregistrementEntree.objects.select_related('vehicule'), id=entree_id_post)
        if entree is None:
            error = "Entrée introuvable."
        elif hasattr(entree, 'reception'):
            # CORRIGÉ : évite une IntegrityError (2 réceptions pour la même entrée)
            error = "Cette entrée a déjà une réception."
        else:
            vehicule = entree.vehicule
    else:
        vehicule = get_or_none(Vehicule.objects, id=vehicule_id_post)
        if vehicule is None:
            error = "Véhicule introuvable."

    if error:
        return render(request, 'reception/creer_reception.html', {'entree': entree, 'error': error})

    with transaction.atomic():
        rec = Reception.objects.create(
            entree=entree,
            vehicule=vehicule,
            statut=StatutVehicule.RAPPORT_FAIT,
            receptionniste=request.user,
            observations=observations,
        )
        if entree:
            entree.statut = StatutVehicule.RAPPORT_FAIT
            entree.save(update_fields=['statut'])

    log_action(request, ActionType.CREATION, 'RECEPTION', rec, {'decision': decision})
    messages.success(request, f"Réception {rec.numero} créée.")

    if decision == 'SORTIE_DIRECTE':
        if entree:
            return redirect('creer_bon_sortie_rec', rec_id=entree.id)
        # CORRIGÉ : avant, crash (entree = None) quand on passait par le véhicule seul
        messages.warning(request, "Sortie directe impossible sans entrée guérite.")

    return redirect('detail_reception', rec_id=rec.id)


@receptionniste_required
def detail_reception(request, rec_id):
    rec = get_object_or_404(
        Reception.objects
        .select_related('vehicule', 'vehicule__client', 'entree', 'receptionniste')
        .prefetch_related('transferts__atelier'),
        id=rec_id,
    )
    entree = getattr(rec, 'entree', None)
    fiche = getattr(entree, 'fiche_controle', None)
 
    # ── Bon de sortie : UNIQUEMENT celui attaché à cette réception ──
    bon_sortie = (
        BonSortie.objects
        .filter(reception=rec)
        .order_by('-created_at')
        .first()
    )

    return render(request, 'reception/detail_reception.html', {
        'rec': rec,
        **_contexte_or_reception(rec),
        'bon_sortie': bon_sortie,
        'fiche_technique': getattr(entree, 'fiche_technique', None),
        'fiche_controle': fiche, 
        'a_fiche_controle': _signe(fiche, 'signature_technicien'),
        'client_a_signe': _signe(fiche, 'signature_client_avant'),
        'signature_apres_faite': _signe(fiche, 'signature_client_apres'),
    })
 

@receptionniste_required
def detail_vehicule(request, vehicule_id):
    v = get_object_or_404(Vehicule.objects.select_related('client'), id=vehicule_id)
    return render(request, 'reception/detail_vehicule.html', {
        'v': v,
        'entrees': v.entrees.order_by('-date_entree')[:10],
        'or_list': v.ordres_reparation.order_by('-date_creation')[:10],
        'rec_list': v.receptions.order_by('-created_at')[:5],
    })


# ─── Rapport ─────────────────────────────────────────────────────────────
@receptionniste_required
def creer_rapport(request, rec_id):
    rec = get_object_or_404(Reception, id=rec_id)
    if hasattr(rec, 'rapport'):
        messages.info(request, "Rapport déjà créé.")
        return redirect('choisir_ateliers', rec_id=rec.id)

    form = RapportReceptionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            rapport = form.save(commit=False)
            rapport.reception = rec
            rapport.cree_par = request.user
            rapport.save()
            rec.statut = StatutVehicule.RAPPORT_FAIT
            rec.save(update_fields=['statut'])
        log_action(request, ActionType.CREATION, 'RECEPTION', rapport)

        if rapport.decision == 'SORTIE_DIRECTE':
            # CORRIGÉ : creer_bon_sortie attend l'id de l'ENTRÉE, pas celui de la réception
            if rec.entree_id:
                messages.success(request, "Rapport créé — sortie directe. Créez le bon de sortie.")
                return redirect('creer_bon_sortie_rec', rec_id=rec.entree_id)
            messages.warning(request, "Rapport créé, mais aucune entrée guérite liée pour le bon de sortie.")
            return redirect('detail_reception', rec_id=rec.id)

        messages.success(request, "Rapport créé. Choisissez les ateliers.")
        return redirect('choisir_ateliers', rec_id=rec.id)

    return render(request, 'reception/creer_rapport.html', {'form': form, 'rec': rec})


# ─── Transfert ateliers ──────────────────────────────────────────────────
@receptionniste_required
def choisir_ateliers(request, rec_id):
    rec = get_object_or_404(Reception, id=rec_id)
    form = TransfertAtelierForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        ateliers = form.cleaned_data['ateliers']
        with transaction.atomic():
            for atelier in ateliers:
                TransfertAtelier.objects.get_or_create(
                    reception=rec, atelier=atelier,
                    defaults={'motif': form.cleaned_data['motif'], 'effectue_par': request.user},
                )
            rec.statut = StatutVehicule.EN_ATELIER
            rec.save(update_fields=['statut'])

        noms = ', '.join(a.nom for a in ateliers)
        log_action(request, ActionType.CHANGEMENT_STATUT, 'RECEPTION', rec, {'ateliers': noms})
        messages.success(request, f"Transféré vers : {noms}")
        return redirect('detail_reception', rec_id=rec.id)

    return render(request, 'reception/choisir_ateliers.html', {
        'form': form,
        'rec': rec,
        'transferts': rec.transferts.select_related('atelier').order_by('-date_transfert'),
    })


# ─── Entrées guérite ─────────────────────────────────────────────────────
@guerite_required
def historique_entrees(request):
    page_obj = paginate_queryset(request, get_filtered_entrees(request))
    return render(request, 'reception/historique.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'statuts': StatutVehicule.choices,
        'motifs': MotifEntree.choices,
    })


@guerite_required
def detail_entree(request, entree_id):
    entree = get_object_or_404(
        EnregistrementEntree.objects.select_related(
            'vehicule', 'vehicule__client', 'conducteur', 'agent_entree'),
        id=entree_id,
    )
    return render(request, 'reception/Entre_detail_rec.html', {'entree': entree})


@login_required  # AJOUTÉ : la vue était accessible sans connexion
def liste_vehicules_presents(request):
    page_obj = paginate_queryset(request, get_entrees_presentes_filtrees(request))
    return render(request, 'reception/vehicules_presents_rec.html', {
        'entrees': page_obj,
        'page_obj': page_obj,
        'motifs': MotifEntree.choices,
    })


@receptionniste_required
def modifier_motif_reception(request, entree_id):
    entree = get_object_or_404(EnregistrementEntree, pk=entree_id)

    if request.method == 'POST':
        motif = request.POST.get('motif')
        if motif in MOTIFS_VALIDES:
            entree.motif = motif
            entree.save(update_fields=['motif'])
            # CORRIGÉ : log uniquement si la modification a eu lieu (avant : aussi en GET)
            log_action(request, ActionType.MODIFICATION, 'ADMIN', entree, {'motif': motif})
            messages.success(request, f"Motif modifié : {entree.get_motif_display()}")
        else:
            messages.error(request, "Motif invalide.")

    return redirect('detail_entree_rec', entree_id=entree.id)



@receptionniste_required
def ref_devis(request, rec_id):
    rec = get_object_or_404(Reception, id=rec_id)

    if request.method == 'POST':
        ref = request.POST.get('reference_devis', '').strip()
        date_str = request.POST.get('date_creation_devis', '').strip()

        if not ref or not date_str:
            messages.error(request, "Référence et date de création sont obligatoires.")
            return redirect('detail_reception', rec_id=rec.id)

        try:
            from datetime import datetime
            date_creation = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Date invalide.")
            return redirect('detail_reception', rec_id=rec.id)

        rec.reference_devis = ref
        rec.date_creation_devis = date_creation
        rec.date_systeme_devis_create = timezone.localdate()  # auto
        rec.save(update_fields=[
            'reference_devis',
            'date_creation_devis',
            'date_systeme_devis_create',
        ])

        log_action(request, ActionType.MODIFICATION, 'RECEPTION', rec, {
            'reference_devis': ref,
            'date_creation_devis': str(date_creation),
        })
        messages.success(request, f"Devis {ref} référencé.")
        return redirect('detail_reception', rec_id=rec.id)

    return redirect('detail_reception', rec_id=rec.id)

