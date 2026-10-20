"""
apps/atelier/controle.py — fiche de contrôle : catégories, libellés, comparaison entrée / sortie.

Flux du contrôle de sortie :
  1. demarrer_sortie()    → crée la ligne fiches_controle_temporaires, VIDE
  2. le technicien recoche uniquement les éléments cochés à l'entrée (champs_coches),
     affichés vides
  3. differences()        → éléments différents de l'entrée ; pour chacun :
       - erreur de saisie : erreur_saisie() vide l'élément et le technicien retourne
         sur le formulaire pour le recocher
       - différence confirmée : confirmer() avec une explication obligatoire
  4. valider_technicien() → possible seulement quand tout est résolu
  5. archiver()           → après la signature du client : tout part dans FicheControle,
                            la ligne temporaire est supprimée
"""
from django.db import transaction
from django.utils import timezone

from .models import FicheControle, FicheControleTemporaire


# ══════════════════════════════════════════════════════════════════
#  CATÉGORIES (ordre d'affichage) — « Habitacle » regroupe les sièges
# ══════════════════════════════════════════════════════════════════
CATEGORIES = [
    ("Équipements et sécurité", [
        'alarme_fonctionne', 'verrouillage_portes', 'telecommande_ouverture', 'trappe_carburant',
        'tirette_capot', 'dossier_vehicule_complet',
        'triangles_securite_presents', 'triangles_securite_nombre',
        'cales_metalliques_presentes', 'cales_metalliques_nombre',
        'gilet_securite_present', 'extincteur_present', 'boite_pharmacie_presente',
        'roue_secours_gonflee_et_remis_en_place', 'cric_present', 'manivelle_presente', 'cle_roue_presente',
    ]),
    ("Habitacle", [
        'voyant_ceintures_securite_s_allume', 'tapis_sol_5_presents',
        'vitres_avant_se_baissent', 'vitres_arriere_se_baissent', 'telecommande_vitres_fonctionne',
        'console_fermeture_ouverture_portiere_fonctionnel', 'reglage_des_miroirs_retroviseurs_fonctionnel',
        'bouton_eclairage_plafonnier', 'climatisation_fonctionne', 'climatisation_fait_froid',
        'autoradio_s_allume', 'son_dans_baffles', 'horloge_a_heure',
        'voyant_moteur_tableau_bord', 'systeme_demarrage_fonctionne', 'jauge_carburant',
    ]),
    ("Extérieur, vitrage et éclairage", [
        'joints_portieres_propres', 'enjoliveurs_et_ecrous_roues_presents', 'bavettes_et_goujons_roues_presents',
        'pression_pneus_bonne', 'plaques_immatriculation_avant_arriere', 'tares_avant_arriere_presentes',
        'garde_boues_presents_bien_montes', 'agrafes_presentes',
        'pare_brise_etat', 'autocollants_pare_brise_presents', 'voiles_peinture_sur_vitres',
        'balais_essuie_glace_avant_arriere', 'gicleur_lave_glace_bocal_reserve',
        'miroirs_retroviseurs_etat', 'retroviseurs_se_rabattent',
        'phares_avant_etat', 'feux_arriere_etat', 'clignotants_avant_arriere_fonctionnent',
        'antibrouillards_feux_jour_bon_etat', 'klaxon_fonctionne', 'camera_recul_fonctionne',
        'capteurs_position_avant_arriere_bipent',
    ]),
    ("Sous le capot", [
        'cosses_batterie_serrées', 'sous_capot_moteur_est_propre', 'isolant_thermique_capot_present',
        'niveau_liquide_lave_glace_bon', 'niveau_liquide_huile_bon',
        'niveau_liquide_refroisseur_bon', 'niveau_liquide_frein_bon',
    ]),
    ("Peinture et carrosserie", [
        'qualite_rendu_peinture_rayures', 'qualite_rendu_peinture_decollement',
        'qualite_rendu_peinture_couleur', 'qualite_rendu_peinture_eclat_brillance',
        'qualite_rendu_peinture_frissure',
        'type_vehicule', 'points_degats_carrosserie',
    ]),
    ("Synthèse", ['etat_general']),
]

# Champs comparés entre l'entrée et la sortie (commentaires : non comparés)
CHAMPS_COMPARES = [c for _, champs in CATEGORIES for c in champs]
CATEGORIE_DE = {c: titre for titre, champs in CATEGORIES for c in champs}
# Tout ce qui est recopié de l'entrée vers la sortie, puis archivé
CHAMPS_ETAT = CHAMPS_COMPARES + ['commentaires']

# Booléens où « Oui » est un défaut
INVERSES = {
    'voyant_moteur_tableau_bord', 'voiles_peinture_sur_vitres',
    'qualite_rendu_peinture_rayures', 'qualite_rendu_peinture_decollement', 'qualite_rendu_peinture_frissure',
}
MAUVAIS = {'DEFAUT', 'CASSE', 'FISSURE', 'MAUVAIS'}
BONS = {'BON', 'INTACT'}

LIBELLES = {
    'alarme_fonctionne': "L'alarme fonctionne-t-elle ?",
    'verrouillage_portes': "Verrouillage des portes (intérieur/extérieur)",
    'telecommande_ouverture': "Télécommande d'ouverture",
    'trappe_carburant': "Trappe à carburant",
    'tirette_capot': "Tirette de capot",
    'dossier_vehicule_complet': "Dossier complet (assurance, carte grise, visite technique)",
    'triangles_securite_presents': "Triangles de sécurité présents",
    'triangles_securite_nombre': "Nombre de triangles",
    'cales_metalliques_presentes': "Cales métalliques présentes",
    'cales_metalliques_nombre': "Nombre de cales",
    'gilet_securite_present': "Gilet de sécurité",
    'extincteur_present': "Extincteur",
    'boite_pharmacie_presente': "Boîte à pharmacie",
    'roue_secours_gonflee_et_remis_en_place': "Roue de secours gonflée et remise en place",
    'cric_present': "Cric",
    'manivelle_presente': "Manivelle",
    'cle_roue_presente': "Clé de roue",

    # Fiche technique — habitacle
    'siege_conducteur_etat': "Siège conducteur",
    'siege_passager_etat': "Siège passager",
    'sieges_arriere_etat': "Sièges arrière / banquette",
    'ceintures_securite_etat': "Ceintures de sécurité",
    'voyant_ceintures_securite_s_allume': "Voyant des ceintures après serrage",
    'tapis_sol_5_presents': "Les 5 tapis de sol présents",
    'vitres_avant_se_baissent': "Vitres avant se baissent",
    'vitres_arriere_se_baissent': "Vitres arrière se baissent",
    'telecommande_vitres_fonctionne': "Commande des vitres",
    'console_fermeture_ouverture_portiere_fonctionnel': "Console d'ouverture / fermeture des portières",
    'reglage_des_miroirs_retroviseurs_fonctionnel': "Réglage des rétroviseurs",
    'bouton_eclairage_plafonnier': "Éclairage du plafonnier",
    'climatisation_fonctionne': "La climatisation fonctionne",
    'climatisation_fait_froid': "La climatisation fait du froid",
    'autoradio_s_allume': "L'autoradio s'allume",
    'son_dans_baffles': "Son dans les baffles",
    'horloge_a_heure': "Horloge à l'heure",
    'voyant_moteur_tableau_bord': "Voyant moteur allumé au tableau de bord",
    'systeme_demarrage_fonctionne': "Système de démarrage",
    'jauge_carburant': "Jauge carburant",

    'joints_portieres_propres': "Joints de portières propres",
    'enjoliveurs_et_ecrous_roues_presents': "Enjoliveurs et écrous de roues présents",
    'bavettes_et_goujons_roues_presents': "Bavettes et goujons de roues présents",
    'pression_pneus_bonne': "Pression des pneus",
    'plaques_immatriculation_avant_arriere': "Plaques d'immatriculation AV / AR",
    'tares_avant_arriere_presentes': "Tares AV / AR présentes",
    'garde_boues_presents_bien_montes': "Garde-boues présents et bien montés",
    'agrafes_presentes': "Agrafes",
    'pare_brise_etat': "Pare-brise",
    'autocollants_pare_brise_presents': "Autocollants du pare-brise présents",
    'voiles_peinture_sur_vitres': "Voiles de peinture sur les vitres",
    'balais_essuie_glace_avant_arriere': "Balais d'essuie-glace AV / AR",
    'gicleur_lave_glace_bocal_reserve': "Gicleur lave-glace et bocal de réserve",
    'miroirs_retroviseurs_etat': "Miroirs des rétroviseurs",
    'retroviseurs_se_rabattent': "Les rétroviseurs se rabattent",
    'phares_avant_etat': "Phares avant",
    'feux_arriere_etat': "Feux arrière",
    'clignotants_avant_arriere_fonctionnent': "Clignotants AV / AR",
    'antibrouillards_feux_jour_bon_etat': "Antibrouillards et feux de jour",
    'klaxon_fonctionne': "Klaxon",
    'camera_recul_fonctionne': "Caméra de recul",
    'capteurs_position_avant_arriere_bipent': "Capteurs de stationnement AV / AR",

    'cosses_batterie_serrées': "Cosses de batterie serrées",
    'sous_capot_moteur_est_propre': "Sous le capot propre",
    'isolant_thermique_capot_present': "Isolant thermique du capot présent",
    'niveau_liquide_lave_glace_bon': "Niveau du lave-glace",
    'niveau_liquide_huile_bon': "Niveau d'huile",
    'niveau_liquide_refroisseur_bon': "Niveau du liquide de refroidissement",
    'niveau_liquide_frein_bon': "Niveau du liquide de frein",

    'qualite_rendu_peinture_rayures': "Peinture : rayures",
    'qualite_rendu_peinture_decollement': "Peinture : décollement",
    'qualite_rendu_peinture_couleur': "Peinture : couleur conforme",
    'qualite_rendu_peinture_eclat_brillance': "Peinture : éclat / brillance",
    'qualite_rendu_peinture_frissure': "Peinture : fissures",
    'type_vehicule': "Type de véhicule (schéma)",
    'points_degats_carrosserie': "Dégâts marqués sur le schéma",

    'etat_general': "État général",
    'commentaires': "Commentaires",
}


def _field(nom):
    return FicheControle._meta.get_field(nom)


def libelle(nom):
    if nom in LIBELLES:
        return LIBELLES[nom]
    v = str(_field(nom).verbose_name)
    return v[:1].upper() + v[1:]


# ══════════════════════════════════════════════════════════════════
#  VALEURS : normalisation, affichage, bon / défaut
# ══════════════════════════════════════════════════════════════════
def _points_norm(points):
    out = []
    for p in points or []:
        try:
            out.append((int(round(float(p.get('x', 0)))), int(round(float(p.get('y', 0)))), str(p.get('type', ''))))
        except (AttributeError, TypeError, ValueError):
            continue
    return sorted(out)


def normaliser(nom, valeur):
    """Forme comparable d'une valeur ('' et None = non renseigné)."""
    if nom == 'points_degats_carrosserie':
        return _points_norm(valeur)
    if valeur == '':
        return None
    return valeur


def identiques(nom, a, b):
    return normaliser(nom, a) == normaliser(nom, b)


def afficher(nom, valeur):
    """Texte lisible d'une valeur brute."""
    if nom == 'points_degats_carrosserie':
        n = len(_points_norm(valeur))
        return f"{n} point{'s' if n > 1 else ''} marqué{'s' if n > 1 else ''}" if n else "Aucun dégât"
    if valeur in (None, '', []):
        return "—"
    f = _field(nom)
    if f.choices:
        return str(dict(f.flatchoices).get(valeur, valeur))
    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"
    return str(valeur)


def qualite(nom, valeur):
    """'good' | 'bad' | '' — sert au code couleur."""
    if valeur in (None, '', []):
        return ''
    if nom == 'points_degats_carrosserie':
        return 'bad' if _points_norm(valeur) else 'good'
    if isinstance(valeur, bool):
        bon = (not valeur) if nom in INVERSES else valeur
        return 'good' if bon else 'bad'
    if valeur in MAUVAIS:
        return 'bad'
    if valeur in BONS:
        return 'good'
    return ''


def etat_de(obj):
    """{champ: valeur} des éléments contrôlés d'une fiche ou d'une ligne temporaire."""
    return {nom: getattr(obj, nom) for nom in CHAMPS_ETAT}


# ══════════════════════════════════════════════════════════════════
#  CONTRÔLE DE SORTIE
# ══════════════════════════════════════════════════════════════════
def rempli(nom, valeur):
    """L'élément a-t-il été coché / renseigné ?"""
    if nom == 'points_degats_carrosserie':
        return bool(_points_norm(valeur))
    if _field(nom).get_internal_type() == 'BooleanField' and not _field(nom).null:
        return valeur is True                      # cric, manivelle, clé de roue : cochés = True
    return valeur not in (None, '', [])


def champs_coches(fiche):
    """Éléments cochés à l'entrée : les seuls que le technicien recoche à la sortie."""
    return [nom for nom in CHAMPS_COMPARES if rempli(nom, getattr(fiche, nom))]


def _vide(nom):
    f = _field(nom)
    t = f.get_internal_type()
    if t == 'JSONField':
        return []
    if t == 'BooleanField':
        return None if f.null else False
    if t in ('CharField', 'TextField'):
        return ''
    return None


def vider(temp, noms):
    for nom in noms:
        setattr(temp, nom, _vide(nom))


def demarrer_sortie(fiche, user):
    """Crée (ou reprend) la ligne temporaire, entièrement VIDE (rien n'est prérempli)."""
    temp = FicheControleTemporaire.objects.filter(fiche_controle=fiche).first()
    if temp:
        return temp, False
    temp = FicheControleTemporaire(fiche_controle=fiche, technicien=user)
    vider(temp, CHAMPS_ETAT)
    temp.save()
    return temp, True


def a_recocher(temp):
    """Éléments signalés « erreur de saisie », à recocher sur le formulaire."""
    return [nom for nom, c in (temp.confirmations or {}).items() if (c or {}).get('recocher')]


def differences(fiche, temp):
    """
    Éléments cochés à l'entrée dont la valeur de sortie diffère.
    Une différence est « confirmée » si le technicien l'a expliquée ET que la valeur
    n'a pas changé depuis (sinon la confirmation ne vaut plus).
    """
    out = []
    recocher = set(a_recocher(temp))
    for nom in champs_coches(fiche):
        avant, apres = getattr(fiche, nom), getattr(temp, nom)
        if nom not in recocher and identiques(nom, avant, apres):
            continue
        conf = (temp.confirmations or {}).get(nom) or {}
        confirmee = (nom not in recocher and bool(conf.get('explication', '').strip())
                     and identiques(nom, conf.get('apres'), apres))
        out.append({
            'champ': nom,
            'libelle': libelle(nom),
            'categorie': CATEGORIE_DE[nom],
            'avant': avant, 'apres': apres,
            'avant_txt': afficher(nom, avant), 'apres_txt': afficher(nom, apres),
            'avant_css': qualite(nom, avant), 'apres_css': qualite(nom, apres),
            'confirmee': confirmee,
            'a_recocher': nom in recocher,
            'explication': conf.get('explication', '') if confirmee else '',
        })
    return out


def toutes_resolues(diffs):
    return all(d['confirmee'] for d in diffs)


def erreur_saisie(temp, nom):
    """Erreur de saisie : l'élément est vidé et doit être recoché sur le formulaire."""
    if nom not in CHAMPS_COMPARES:
        raise ValueError(nom)
    setattr(temp, nom, _vide(nom))
    conf = dict(temp.confirmations or {})
    conf[nom] = {'recocher': True}
    temp.confirmations = conf
    temp.statut = FicheControleTemporaire.Statut.SAISIE
    temp.date_validation = None
    temp.save()


def recoche(temp, noms):
    """Les éléments viennent d'être recochés : on retire le signalement."""
    conf = dict(temp.confirmations or {})
    for nom in noms:
        if (conf.get(nom) or {}).get('recocher'):
            conf.pop(nom)
    temp.confirmations = conf


def confirmer(temp, nom, explication, user):
    """Différence confirmée : l'explication est obligatoire."""
    if nom not in CHAMPS_COMPARES:
        raise ValueError(nom)
    explication = (explication or '').strip()
    if not explication:
        raise ValueError("explication")
    conf = dict(temp.confirmations or {})
    conf[nom] = {
        'apres': getattr(temp, nom),
        'explication': explication,
        'par': str(user.pk) if user else None,
        'le': timezone.now().isoformat(),
    }
    temp.confirmations = conf
    temp.statut = FicheControleTemporaire.Statut.VERIFICATION
    temp.save()


def annuler_confirmation(temp, nom):
    conf = dict(temp.confirmations or {})
    conf.pop(nom, None)
    temp.confirmations = conf
    temp.statut = FicheControleTemporaire.Statut.VERIFICATION
    temp.save()


def valider_technicien(fiche, temp):
    """Le technicien enregistre la fiche : refusé tant qu'une différence n'est pas résolue."""
    if temp.kilometrage_sortie is None or a_recocher(temp) or not toutes_resolues(differences(fiche, temp)):
        return False
    temp.statut = FicheControleTemporaire.Statut.A_SIGNER
    temp.date_validation = timezone.now()
    temp.save(update_fields=['statut', 'date_validation', 'date_maj'])
    return True


def comparatif(fiche, etat_sortie, diffs):
    """
    Lignes « Avant / Maintenant » par catégorie pour l'écran client et l'historique.
    tendance : '' (identique) | 'mieux' | 'pire' | 'change'
    """
    par_champ = {d['champ']: d for d in diffs}
    coches = set(champs_coches(fiche))
    sections = []
    for titre, champs in CATEGORIES:
        lignes = []
        for nom in champs:
            if nom not in coches:
                continue
            avant, apres = getattr(fiche, nom), etat_sortie.get(nom)
            d = par_champ.get(nom)
            qa, qb = qualite(nom, avant), qualite(nom, apres)
            if identiques(nom, avant, apres):
                tendance = ''
            elif qa == 'bad' and qb == 'good':
                tendance = 'mieux'
            elif qb == 'bad' and qa != 'bad':
                tendance = 'pire'
            else:
                tendance = 'change'
            lignes.append({
                'champ': nom, 'libelle': libelle(nom),
                'avant_txt': afficher(nom, avant), 'apres_txt': afficher(nom, apres),
                'avant_css': qa, 'apres_css': qb,
                'tendance': tendance,
                'explication': (d or {}).get('explication', ''),
            })
        if not lignes:
            continue
        sections.append({'titre': titre, 'lignes': lignes,
                         'nb_diff': sum(1 for l in lignes if l['tendance'])})
    return sections


@transaction.atomic
def archiver(fiche_id, nom_client, chemin_signature):
    """
    Après la signature du client : l'état de sortie, les différences confirmées,
    les explications et la signature vont dans FicheControle ; la ligne temporaire est supprimée.
    Retourne la fiche, ou None si le contrôle n'est pas prêt (déjà archivé, pas validé, différence non résolue).
    """
    fiche = FicheControle.objects.select_for_update().get(pk=fiche_id)
    temp = FicheControleTemporaire.objects.select_for_update().filter(fiche_controle=fiche).first()
    if temp is None or temp.statut != FicheControleTemporaire.Statut.A_SIGNER:
        return None
    diffs = differences(fiche, temp)
    if a_recocher(temp) or not toutes_resolues(diffs):
        return None

    maintenant = timezone.now()
    fiche.kilometrage_sortie = temp.kilometrage_sortie
    fiche.etat_sortie = etat_de(temp)
    fiche.differences_sortie = [{
        'champ': d['champ'], 'libelle': d['libelle'], 'categorie': d['categorie'],
        'avant': d['avant'], 'apres': d['apres'],
        'avant_txt': d['avant_txt'], 'apres_txt': d['apres_txt'],
        'explication': d['explication'],
    } for d in diffs]
    fiche.controle_sortie_par = temp.technicien
    fiche.date_controle_sortie = temp.date_validation
    fiche.date_signature_sortie = maintenant
    fiche.nom_client_apres = nom_client
    fiche.signature_client_apres = chemin_signature
    fiche.save()
    temp.delete()
    return fiche
