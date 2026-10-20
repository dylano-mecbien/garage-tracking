"""
apps/inventaire/services.py — logique de l'inventaire (un seul inventaire, validation administrateur).

  Guérite : démarrer → marquer Présent/Absent (Absent = SORTIE en table temporaire) → « Faire entrer » (ENTREE en
            table temporaire) → valider l'inventaire (statut SOUMIS + e-mail à l'administrateur).
  Admin   : choisit les entrées/sorties à appliquer → valider (définitif + suppression de la table temporaire),
            ou révoquer l'inventaire.
"""
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.inventaire.notifications import envoyer_inventaire_a_valider

from . import adapters
from .models import (Inventaire, LigneInventaire, MouvementTemporaire, Presence, StatutInventaire, TypeMouvement)

MOTIF_REVOCATION_MIN = 5


class InventaireError(Exception):
    """Erreur de règle métier, message affichable tel quel."""


def inventaire_en_cours():
    return Inventaire.objects.filter(statut=StatutInventaire.EN_COURS).first()


def inventaire_soumis():
    return Inventaire.objects.filter(statut=StatutInventaire.SOUMIS).first()


# ═════════════════════════  GUÉRITE  ═════════════════════════
@transaction.atomic
def demarrer(user):
    en_cours = inventaire_en_cours()
    if en_cours:
        return en_cours, False
    soumis = inventaire_soumis()
    if soumis:
        raise InventaireError(f"L'inventaire du {soumis.date:%d/%m/%Y} attend la décision de l'administrateur : "
                              "impossible d'en démarrer un nouveau avant.")
    inv = Inventaire.objects.create(cree_par=user)
    LigneInventaire.objects.bulk_create([
        LigneInventaire(inventaire=inv, vehicule=e.vehicule, entree=e) for e in adapters.entrees_ouvertes()])
    return inv, True


def synchroniser(inv):
    """Ajoute (à vérifier) les véhicules devenus présents dans le système depuis le démarrage."""
    if not inv.en_cours:
        return 0
    existants = set(inv.lignes.values_list('vehicule_id', flat=True))
    en_attente = set(inv.mouvements.filter(type=TypeMouvement.ENTREE).values_list('vehicule_id', flat=True))
    n = 0
    for e in adapters.entrees_ouvertes():
        if e.vehicule_id not in existants and e.vehicule_id not in en_attente:
            LigneInventaire.objects.create(inventaire=inv, vehicule=e.vehicule, entree=e)
            n += 1
    return n


def _verifier_modifiable(inv):
    if not inv.en_cours:
        raise InventaireError("Cet inventaire n'est plus modifiable.")


@transaction.atomic
def marquer(inv, ligne, presence, user):
    """Présent / Absent / À vérifier. Absent → la SORTIE passe en table temporaire (statut Sortie)."""
    _verifier_modifiable(inv)
    if presence not in Presence.values:
        raise InventaireError("Valeur invalide.")
    ligne.presence = presence
    ligne.verifie_par = user if presence != Presence.A_VERIFIER else None
    ligne.date_verification = timezone.now() if presence != Presence.A_VERIFIER else None
    ligne.save(update_fields=['presence', 'verifie_par', 'date_verification'])

    if presence == Presence.ABSENT:
        MouvementTemporaire.objects.update_or_create(
            inventaire=inv, vehicule=ligne.vehicule,
            defaults={'type': TypeMouvement.SORTIE, 'matricule': ligne.vehicule.immatriculation,
                      'entree': ligne.entree, 'cree_par': user})
    else:
        inv.mouvements.filter(vehicule=ligne.vehicule, type=TypeMouvement.SORTIE).delete()


def verifier_plaque(inv, plaque):
    """Pour la popup « Faire entrer » : que sait-on de cette plaque ?"""
    v = adapters.trouver_vehicule(plaque)
    if v is None:
        return {'ok': False, 'code': 'inconnu',
                'message': "Véhicule inconnu du système : il doit d'abord être créé (fiche véhicule)."}
    info = {'vehicule': f"{v.marque} {v.modele}".strip(), 'client': str(v.client), 'immat': v.immatriculation}
    if any(e.vehicule_id == v.id for e in adapters.entrees_ouvertes()):
        return {'ok': False, 'code': 'deja_present', **info,
                'message': "Ce véhicule est déjà présent dans le système (cherche-le dans la liste)."}
    if inv.mouvements.filter(vehicule=v).exists():
        return {'ok': False, 'code': 'deja_ajoute', **info, 'message': "Ce véhicule est déjà en attente dans cet inventaire."}
    return {'ok': True, 'code': 'ok', **info, 'message': f"✓ {info['immat']} — {info['vehicule']} ({info['client']})"}


@transaction.atomic
def ajouter_entree(inv, plaque, chauffeur, chauffeur_tel, motif, user):
    """« Faire entrer » : le mouvement est enregistré dans la table temporaire (rien de définitif)."""
    _verifier_modifiable(inv)
    chauffeur = (chauffeur or '').strip()
    if not chauffeur:
        raise InventaireError("Le chauffeur est obligatoire.")
    if motif not in dict(adapters.motifs_entree()):
        raise InventaireError("Choisis un motif d'entrée.")
    res = verifier_plaque(inv, plaque)
    if not res['ok']:
        raise InventaireError(res['message'])
    v = adapters.trouver_vehicule(plaque)
    cond = adapters.trouver_conducteur(chauffeur)
    return MouvementTemporaire.objects.create(
        inventaire=inv, type=TypeMouvement.ENTREE, vehicule=v, matricule=v.immatriculation,
        chauffeur=chauffeur, chauffeur_tel=(chauffeur_tel or '').strip(), conducteur=cond, motif=motif, cree_par=user)


def supprimer_entree(inv, mouvement_id):
    _verifier_modifiable(inv)
    inv.mouvements.filter(id=mouvement_id, type=TypeMouvement.ENTREE).delete()


def resume(inv):
    lignes = list(inv.lignes.all())
    return {
        'nb_total': len(lignes),
        'nb_present': sum(1 for l in lignes if l.presence == Presence.PRESENT),
        'nb_absent': sum(1 for l in lignes if l.presence == Presence.ABSENT),
        'a_verifier': sum(1 for l in lignes if l.presence == Presence.A_VERIFIER),
        'nb_entrees': inv.mouvements.filter(type=TypeMouvement.ENTREE).count(),
        'nb_sorties': inv.mouvements.filter(type=TypeMouvement.SORTIE).count(),
    }




def soumettre(inv, user, observation):
    """La guérite VALIDE l'inventaire → e-mail à l'administrateur. Retourne le message à afficher."""
    _verifier_modifiable(inv)
    synchroniser(inv)
    r = resume(inv)
    if r['a_verifier']:
        raise InventaireError(f"{r['a_verifier']} véhicule(s) n'ont pas encore été vérifiés.")
    renvoi = bool(inv.motif_revocation)                                  # ← nouveau
    inv.mouvements.exclude(erreur='').update(erreur='')                  # ← nouveau
    inv.statut = StatutInventaire.SOUMIS
    inv.soumis_par, inv.date_soumission, inv.observation = user, timezone.now(), (observation or '').strip()
    inv.motif_revocation = ''                                            # ← nouveau (l'historique reste dans rapport)
    inv.decide_par, inv.date_decision = None, None                       # ← nouveau
    inv.save()
    ok, nb, err = envoyer_inventaire_a_valider(inv)
    inv.email_envoye, inv.email_erreur = ok, err
    inv.save(update_fields=['email_envoye', 'email_erreur'])
    quoi = "corrigé et renvoyé" if renvoi else "validé et envoyé"
    if ok:
        return f"✅ Inventaire {quoi} à l'administrateur ({nb} destinataire(s))."
    return f"✅ Inventaire {quoi}. L'e-mail n'a pas pu partir, mais l'administrateur le voit dans son espace."



# ═════════════════════════  ADMINISTRATEUR  ═════════════════════════
def _ligne_rapport(mv, decision, detail=''):
    return {'type': mv.type, 'matricule': mv.matricule, 'chauffeur': mv.chauffeur, 'motif': mv.motif,
            'decision': decision, 'detail': detail}


def valider_selection(inv, admin, ids_selectionnes):
    """
    L'administrateur a choisi les mouvements à appliquer.
      • sélectionné  → enregistrement DÉFINITIF (entrée ou sortie) puis suppression de la table temporaire ;
      • non retenu   → écarté (supprimé aussi) ;
    En cas d'échec sur un mouvement, il reste en attente avec son erreur et l'inventaire reste SOUMIS.
    Retourne (appliques, ecartes, erreurs).
    """
    if inv.statut != StatutInventaire.SOUMIS:
        raise InventaireError("Cet inventaire n'est pas en attente de validation.")
    ids = {str(i) for i in ids_selectionnes}
    rapport = list((inv.rapport or {}).get('mouvements', []))
    appliques = ecartes = 0
    erreurs = []
    for mv in list(inv.mouvements.select_related('vehicule', 'entree')):
        if str(mv.id) not in ids:
            continue
        try:
            with transaction.atomic():
                if mv.type == TypeMouvement.ENTREE:
                    adapters.creer_entree_definitive(mv, admin)
                else:
                    adapters.cloturer_sortie_definitive(mv, admin)
                rapport.append(_ligne_rapport(mv, 'VALIDE'))
                mv.delete()
                appliques += 1
        except (ValueError, IntegrityError, Exception) as exc:           # noqa — message affiché, mouvement conservé
            mv.erreur = str(exc)[:500]
            mv.save(update_fields=['erreur'])
            erreurs.append(f"{mv.get_type_display()} {mv.matricule} : {mv.erreur}")
    if not erreurs:
        for mv in inv.mouvements.all():
            rapport.append(_ligne_rapport(mv, 'ECARTE'))
            ecartes += 1
        inv.mouvements.all().delete()
        inv.statut = StatutInventaire.VALIDE
        inv.decide_par, inv.date_decision = admin, timezone.now()
        # avant : inv.rapport = {'mouvements': rapport}
    inv.rapport = {**(inv.rapport or {}), 'mouvements': rapport}
    inv.save()
    return appliques, ecartes, erreurs




@transaction.atomic
def revoquer(inv, admin, motif):
    """
    L'administrateur renvoie l'inventaire à la guérite pour correction.
    Rien n'est appliqué : lignes et mouvements sont CONSERVÉS, l'inventaire redevient EN_COURS (modifiable).
    """
    if inv.statut != StatutInventaire.SOUMIS:
        raise InventaireError("Seul un inventaire en attente de validation peut être renvoyé pour correction.")
    motif = (motif or '').strip()
    if len(motif) < MOTIF_REVOCATION_MIN:
        raise InventaireError("Indique le motif de la révocation.")

    rapport = dict(inv.rapport or {})
    rapport.setdefault('revocations', []).append({
        'date': timezone.now().isoformat(),
        'par': admin.get_full_name() if hasattr(admin, 'get_full_name') else str(admin),
        'motif': motif,
        'soumis_le': inv.date_soumission.isoformat() if inv.date_soumission else None,
        'nb_entrees': inv.mouvements.filter(type=TypeMouvement.ENTREE).count(),
        'nb_sorties': inv.mouvements.filter(type=TypeMouvement.SORTIE).count(),
    })

    inv.statut = StatutInventaire.EN_COURS
    inv.motif_revocation = motif                   # affiché à la guérite tant qu'elle n'a pas renvoyé
    inv.decide_par, inv.date_decision = admin, timezone.now()
    inv.email_envoye, inv.email_erreur = False, ''
    inv.rapport = rapport
    inv.save()