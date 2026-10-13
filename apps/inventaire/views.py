"""apps/inventaire/views.py — pages guérite (inventaire unique) + administration (validation / révocation)."""
import datetime
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.views.decorators.http import require_POST

from . import adapters, services
from .decorators import guerite_required, admin_only
from .models import Inventaire, LigneInventaire, MouvementTemporaire, Presence, StatutInventaire, TypeMouvement
from .services import InventaireError


def _url_ou_vide(name):
    try:
        return reverse(name)
    except NoReverseMatch:
        return ''


# ═════════════════════════  GUÉRITE  ═════════════════════════
@guerite_required
def accueil(request):
    en_cours, soumis = services.inventaire_en_cours(), services.inventaire_soumis()
    return render(request, 'inventaire/accueil.html', {
        'en_cours': en_cours, 'soumis': soumis,
        'historique': Inventaire.objects.select_related('decide_par')[:20],
        'nb_presents_systeme': len(adapters.entrees_ouvertes()),
    })


@guerite_required
@require_POST
def demarrer(request):
    try:
        inv, cree = services.demarrer(request.user)
    except InventaireError as e:
        messages.error(request, str(e))
        return redirect('inventaire_accueil')
    if not cree:
        messages.info(request, "Un inventaire est déjà en cours — reprise.")
    return redirect('inventaire_detail', inv_id=inv.id)


def _etat(inv):
    r = services.resume(inv)
    r['sorties'] = [{'id': str(m.id), 'matricule': m.matricule} for m in inv.mouvements.filter(type=TypeMouvement.SORTIE)]
    return r


@guerite_required
def detail(request, inv_id):
    inv = get_object_or_404(Inventaire.objects.select_related('soumis_par', 'decide_par'), id=inv_id)
    if inv.en_cours:
        ajoutes = services.synchroniser(inv)
        if ajoutes:
            messages.info(request, f"{ajoutes} véhicule(s) entré(s) au système ont été ajoutés à la liste à vérifier.")
    lignes = list(inv.lignes.select_related('vehicule', 'vehicule__client'))
    ordre = {Presence.A_VERIFIER: 0, Presence.ABSENT: 1, Presence.PRESENT: 2}
    lignes.sort(key=lambda l: (ordre[l.presence], l.vehicule.immatriculation))
    entrees = list(inv.mouvements.filter(type=TypeMouvement.ENTREE).select_related('vehicule'))
    for m in entrees:
        m.motif_libelle = adapters.libelle_motif(m.motif)
    return render(request, 'inventaire/detail.html', {
        'inv': inv, 'lignes': lignes, 'entrees': entrees, 'etat': _etat(inv),
        'sorties': inv.mouvements.filter(type=TypeMouvement.SORTIE),
        'motifs': adapters.motifs_entree(), 'chauffeurs': adapters.conducteurs_noms(),
        'url_creer_vehicule': _url_ou_vide('creer_vehicule_guerite'),
    })


@guerite_required
@require_POST
def marquer(request, inv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    ligne = get_object_or_404(LigneInventaire, id=request.POST.get('ligne_id'), inventaire=inv)
    try:
        services.marquer(inv, ligne, request.POST.get('presence'), request.user)
    except InventaireError as e:
        return JsonResponse({'ok': False, 'erreur': str(e)}, status=400)
    return JsonResponse({'ok': True, 'etat': _etat(inv)})


@guerite_required
def verifier_plaque(request, inv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    return JsonResponse(services.verifier_plaque(inv, request.GET.get('q', '')))


@guerite_required
@require_POST
def ajouter_entree(request, inv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    try:
        mv = services.ajouter_entree(inv, request.POST.get('matricule'), request.POST.get('chauffeur'),
                                     request.POST.get('chauffeur_tel'), request.POST.get('motif'), request.user)
    except InventaireError as e:
        return JsonResponse({'ok': False, 'erreur': str(e)}, status=400)
    return JsonResponse({'ok': True, 'message': f"Entrée de {mv.matricule} enregistrée (en attente de validation)."})


@guerite_required
@require_POST
def supprimer_mouvement(request, inv_id, mv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    try:
        services.supprimer_entree(inv, mv_id)
    except InventaireError as e:
        messages.error(request, str(e))
    return redirect('inventaire_detail', inv_id=inv.id)


@guerite_required
@require_POST
def soumettre(request, inv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    try:
        messages.success(request, services.soumettre(inv, request.user, request.POST.get('observation', '')))
    except InventaireError as e:
        messages.error(request, str(e))
    return redirect('inventaire_detail', inv_id=inv.id)


# ═════════════════════════  ADMINISTRATION  ═════════════════════════
@admin_only
def admin_liste(request):
    qs = Inventaire.objects.select_related('soumis_par', 'decide_par')
    a_valider = request.GET.get('a_valider') == '1'
    if a_valider:
        qs = qs.filter(statut=StatutInventaire.SOUMIS)
    debut, fin = request.GET.get('debut', ''), request.GET.get('fin', '')
    try:
        if debut:
            qs = qs.filter(date__gte=datetime.date.fromisoformat(debut))
        if fin:
            qs = qs.filter(date__lte=datetime.date.fromisoformat(fin))
    except ValueError:
        pass
    invs = list(qs[:200])
    for i in invs:
        i.nb_entrees = i.mouvements.filter(type=TypeMouvement.ENTREE).count()
        i.nb_sorties = i.mouvements.filter(type=TypeMouvement.SORTIE).count()
    return render(request, 'inventaire/admin_liste.html', {
        'inventaires': invs, 'a_valider': a_valider, 'debut': debut, 'fin': fin,
        'nb_a_valider': Inventaire.objects.filter(statut=StatutInventaire.SOUMIS).count(),
    })


@admin_only
def admin_detail(request, inv_id):
    inv = get_object_or_404(Inventaire.objects.select_related('soumis_par', 'decide_par'), id=inv_id)
    mv = list(inv.mouvements.select_related('vehicule', 'vehicule__client', 'cree_par'))
    for m in mv:
        m.motif_libelle = adapters.libelle_motif(m.motif)
    return render(request, 'inventaire/admin_detail.html', {
        'inv': inv, 'lignes': inv.lignes.select_related('vehicule', 'vehicule__client'),
        'entrees': [m for m in mv if m.type == TypeMouvement.ENTREE],
        'sorties': [m for m in mv if m.type == TypeMouvement.SORTIE],
        'rapport': (inv.rapport or {}).get('mouvements', []), 'etat': services.resume(inv),
        'peut_decider': inv.statut == StatutInventaire.SOUMIS,
        'peut_revoquer': inv.statut in (StatutInventaire.SOUMIS, StatutInventaire.EN_COURS),
    })


@admin_only
@require_POST
def admin_valider(request, inv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    try:
        ap, ec, erreurs = services.valider_selection(inv, request.user, request.POST.getlist('mouvements'))
    except InventaireError as e:
        messages.error(request, str(e))
        return redirect('inventaire_admin_detail', inv_id=inv.id)
    if erreurs:
        messages.warning(request, f"{ap} mouvement(s) appliqué(s). Échec pour : " + " ; ".join(erreurs))
    else:
        messages.success(request, f"✅ Inventaire validé : {ap} mouvement(s) enregistré(s) définitivement, {ec} écarté(s).")
    return redirect('inventaire_admin_detail', inv_id=inv.id)


@admin_only
@require_POST
def admin_revoquer(request, inv_id):
    inv = get_object_or_404(Inventaire, id=inv_id)
    try:
        services.revoquer(inv, request.user, request.POST.get('motif', ''))
        messages.success(request, "Inventaire révoqué — aucun mouvement n'a été appliqué.")
    except InventaireError as e:
        messages.error(request, str(e))
    return redirect('inventaire_admin_detail', inv_id=inv.id)
