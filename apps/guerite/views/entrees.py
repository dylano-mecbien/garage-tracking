"""
Entrées et sorties de véhicules.
"""
from itertools import chain

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.choices import EtatBon, MotifEntree, StatutVehicule
from apps.accounts.decorators import guerite_required
from apps.audit.models import ActionType
from apps.audit.service import log_action
from apps.guerite.forms import EntreeForm, SortieForm
from apps.guerite.models import BonSortie, EnregistrementEntree
from apps.notifications.hook import notifier_sortie_vehicule
from apps.reception.views._utils import MOTIFS_VALIDES, a_champ, save_signature_from_dataurl
from apps.vehicules.models import Client, Conducteur, Vehicule
import threading
from ._utils import entree_active, get_entree_non_sortie


# ─── Entrée ──────────────────────────────────────────────────────────────
@guerite_required
def nouvelle_entree(request):
    """Étape 1 : choisir un véhicule existant ou en créer un."""
    vehicule_id = request.GET.get('vehicule_id')
    vehicule = get_object_or_404(Vehicule, id=vehicule_id) if vehicule_id else None
    return render(request, 'guerite/entree/choix.html', {'vehicule': vehicule})


def _liste_conducteurs():
    """Conducteurs + clients actifs, triés par nom.
    ⚠️ Charge toute la table à chaque affichage : à remplacer à terme par
    l'autocomplete `autocomplete_conducteurs` qui existe déjà."""
    return sorted(
        chain(Conducteur.objects.all(), Client.objects.filter(is_active=True)),
        key=lambda x: (x.nom or '').lower(),  # CORRIGÉ : plantait si un nom était vide (None)
    )


@guerite_required
def enregistrer_entree(request):
    vehicule_id = request.GET.get('vehicule_id')
    vehicule = get_object_or_404(Vehicule, id=vehicule_id) if vehicule_id else None

    form = EntreeForm(request.POST or None, initial={'vehicule': vehicule} if vehicule else {})
    if request.method == 'POST' and form.is_valid():
        entree = form.save(commit=False)

        # AJOUTÉ : un véhicule déjà sur site ne peut pas entrer une 2e fois
        deja = entree_active(entree.vehicule)
        if deja:
            messages.error(request, f"Ce véhicule est déjà sur site (entrée {deja.numero}). "
                                    "Enregistrez d'abord sa sortie.")
            return redirect('detail_entree', entree_id=deja.id)

        entree.agent_entree = request.user
        entree.save()
        log_action(request, ActionType.CREATION, 'GUERITE', entree, {'motif': entree.motif})
        messages.success(request, f"Entrée {entree.numero} enregistrée avec succès !")
        return redirect('detail_entree', entree_id=entree.id)

    return render(request, 'guerite/entree/enregistrer.html', {
        'form': form, 'vehicule': vehicule, 'conducteurs': _liste_conducteurs(),
    })


@guerite_required
def modifier_motif_entree(request, entree_id):
    entree = get_object_or_404(EnregistrementEntree, pk=entree_id)

    if request.method == 'POST':
        motif = request.POST.get('motif')
        if motif in MOTIFS_VALIDES:
            entree.motif = motif
            entree.save(update_fields=['motif'])
            # CORRIGÉ : log uniquement si la modification a eu lieu (avant : aussi en GET)
            log_action(request, ActionType.MODIFICATION, 'GUERITE', entree, {'motif': motif})
            messages.success(request, f"Motif modifié : {entree.get_motif_display()}")
        else:
            messages.error(request, "Motif invalide.")

    return redirect('detail_entree', entree_id=entree.id)


# ─── Sortie ──────────────────────────────────────────────────────────────
def _bon_approuve(entree):
    """Bon de sortie approuvé et pas encore utilisé pour cette entrée."""
    if entree.motif == MotifEntree.VISITE:
        return None
    # CORRIGÉ : on prend d'abord le bon lié à CETTE entrée. Avant, on prenait
    # le dernier bon approuvé du véhicule, qui pouvait venir d'un ancien passage.
    bon = entree.bon_sortie
    if bon and bon.etats == EtatBon.APPROBATION and not bon.est_valide:
        return bon
    return (BonSortie.objects
            .filter(vehicule=entree.vehicule, etats=EtatBon.APPROBATION, est_valide=False)
            .order_by('-created_at').first())





def _envoyer_notif_async(bon_id):
    """Envoie la notification dans un thread séparé."""
    from django.db import connection
    try:
        bon = BonSortie.objects.filter(id=bon_id).first()
        if bon:
            notifier_sortie_vehicule(bon)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Erreur notif async : %s", e)
    finally:
        connection.close()   # ⚠️ important pour éviter les fuites de connexion




@guerite_required
def enregistrer_sortie(request, entree_id):
    entree = get_entree_non_sortie(entree_id)
    bon = _bon_approuve(entree)
    form = SortieForm(request.POST or None)

    def page(erreur=None):
        if erreur:
            messages.error(request, erreur)
        return render(request, 'guerite/sortie/enregistrer.html', {
            'entree': entree, 'form': form, 'bon_sortie': bon,
        })

    if request.method != 'POST':
        return page() 

    if entree.motif != MotifEntree.VISITE and not bon:
        return page("Aucun bon de sortie valide trouvé. Contactez la réception.")

    signature = request.POST.get('signature_client')
    if not signature:
        return page("Le client doit signer avant de confirmer la sortie.")

    if bon and not save_signature_from_dataurl(bon, signature, 'signature_client'):
        return page("Erreur lors de l'enregistrement de la signature.")

    now = timezone.now()
    # AJOUTÉ : tout ou rien. Avant, une erreur au milieu pouvait laisser
    # le bon validé alors que le véhicule n'était pas marqué sorti.


    with transaction.atomic():
        if bon:
            bon.est_valide = True
            bon.date_validation = now
            bon.etats = EtatBon.VALIDER
            bon.save()
            entree.bon_sortie = bon

        entree.statut = StatutVehicule.SORTI
        entree.date_sortie = now
        entree.agent_sortie = request.user
        entree.save()

        # AJOUTÉ : si une fiche de contrôle existe, on y reporte la date de sortie
        fiche = getattr(entree, 'fiche_controle', None)
        if fiche is not None:
            fiche.sortir_le = now
            fiche.save(update_fields=['sortir_le'])

        reception = getattr(entree, 'reception', None)
        if reception is not None:
            reception.statut = StatutVehicule.SORTI
            champs = ['statut']
            if a_champ(reception, 'date_sortie'):
                reception.date_sortie = now
                champs.append('date_sortie')
            reception.save(update_fields=champs)


    if bon:
       
       threading.Thread(
            target=_envoyer_notif_async,
            args=(str(bon.id),),
            daemon=True,
        ).start()
       
    log_action(request, ActionType.CHANGEMENT_STATUT, 'GUERITE', entree, {'statut': 'SORTI'})
    messages.success(request, f"Sortie du véhicule {entree.vehicule.immatriculation} enregistrée.")
    return redirect('dashboard_guerite')
