


from django.db import models





class StatutInventaire(models.TextChoices):
    EN_COURS = 'EN_COURS', 'En cours'
    SOUMIS = 'SOUMIS', "En attente de l'administrateur"
    VALIDE = 'VALIDE', 'Validé'
    REVOQUE = 'REVOQUE', 'Révoqué'


class Presence(models.TextChoices):
    A_VERIFIER = 'A_VERIFIER', 'À vérifier'
    PRESENT = 'PRESENT', 'Présent'
    ABSENT = 'ABSENT', 'Absent'


class TypeMouvement(models.TextChoices):
    ENTREE = 'ENTREE', 'Entrée'
    SORTIE = 'SORTIE', 'Sortie'
    

# ══════════════════════════════════════════════════════════════════
#  TÂCHES
# ══════════════════════════════════════════════════════════════════
class StatutTache(models.TextChoices):
    A_FAIRE = 'A_FAIRE', 'À faire'
    EN_COURS = 'EN_COURS', 'En cours'
    TERMINEE = 'TERMINEE', 'Terminée (en attente de validation)'
    VALIDEE = 'VALIDEE', 'Validée'



class PrioriteTache(models.TextChoices):
    BASSE = 'BASSE', 'Basse'
    NORMALE = 'NORMALE', 'Normale'
    HAUTE = 'HAUTE', 'Haute'
    URGENTE = 'URGENTE', 'Urgente'





class StatutOR(models.TextChoices):
    OUVERT = 'OUVERT', 'Ouvert'
    EN_COURS = 'EN_COURS', 'En cours'
    CLOTURE = 'CLOTURE', 'Clôturé'
    ANNULE = 'ANNULE', 'Annulé'
    REOUVERT = 'REOUVERT', 'Réouvert'


class TypeOR(models.TextChoices):
    NORMAL = 'NORMAL', 'Normal'
    RETOUR = 'RETOUR', 'Retour / Malfaçon'

class UrgenceOR(models.TextChoices):
    NORMAL   = 'NORMAL',   'Normal'
    URGENT   = 'URGENT',   'Urgent'
    CRITIQUE = 'CRITIQUE', 'Critique'


class MotifEntree(models.TextChoices):
    VISITE = 'VISITE', 'Visite'
    STATIONNEMENT = 'STATIONNEMENT', 'Stationnement'
    INTERNE = 'INTERNE', 'Interne'
    REPARATION = 'REPARATION', 'Réparation'


class TypeBon(models.TextChoices):
    VEHICULE = 'VEHICULE', 'Véhicule'
    DIVERS = 'DIVERS', 'Divers'

class EtatBon(models.TextChoices):
    CREER = 'CREER', 'Créer'
    APPROBATION = 'APPROBATION', 'Approbation'
    VALIDER = 'VALIDER', 'Valider'


class ActionType(models.TextChoices):
    CONNEXION = 'CONNEXION', 'Connexion'
    DECONNEXION = 'DECONNEXION', 'Déconnexion'
    CREATION = 'CREATION', 'Création'
    MODIFICATION = 'MODIFICATION', 'Modification'
    SUPPRESSION = 'SUPPRESSION', 'Suppression'
    CHANGEMENT_STATUT = 'CHANGEMENT_STATUT', 'Changement de statut'
    EXPORT = 'EXPORT', 'Export'
    TELECHARGEMENT = 'TELECHARGEMENT', 'Téléchargement'
    CONSULTATION = 'CONSULTATION', 'Consultation'



class StatutVehicule(models.TextChoices):
    # Étape 1 : en réception
    EN_COURS            = 'EN_COURS',           'Réception — En cours'
    RAPPORT_FAIT        = 'RAPPORT_FAIT',        'fiche de reception en attente'
    # Étape 2 : atelier
    FICHE_CONTROLE     = 'PRESENT_ATELIER',     'Fiche de controle en attente'
    FICHE_TECHNIQUE     = 'FICHE_TECHNIQUE',     'Fiche de controle établie'
    REPARATION_EN_COURS = 'REPARATION_EN_COURS', 'Réparation en cours'
    TRAVAUX_TERMINES    = 'TRAVAUX_TERMINES',    ' Travaux terminés'
    # Étape 3 : sortie
    BON_SORTIE_FAIT     = 'BON_SORTIE_FAIT',     'Bon de sortie établi'
    SORTI               = 'SORTI',               'Véhicule sorti'


class StatutReception(models.TextChoices):
    # Étape 1 : en réception
    RAPPORT_FAIT        = 'RAPPORT_FAIT',        'fiche de reception en attente'
    # Étape 2 : atelier
    FICHE_CONTROLE     = 'PRESENT_ATELIER',     'Fiche de controle en attente'
    FICHE_TECHNIQUE     = 'FICHE_TECHNIQUE',     'Fiche de controle établie'
    REPARATION_EN_COURS = 'REPARATION_EN_COURS', 'Réparation en cours'
    TRAVAUX_TERMINES    = 'TRAVAUX_TERMINES',    ' Travaux terminés'
    # Étape 3 : sortie
    BON_SORTIE_FAIT     = 'BON_SORTIE_FAIT',     'Bon de sortie établi'


class StatutVehiculeAtelier(models.TextChoices):
    # Étape 1 : en réception
    RAPPORT_FAIT        = 'RAPPORT_FAIT',        'fiche de reception en attente'
    # Étape 2 : atelier
    FICHE_CONTROLE     = 'PRESENT_ATELIER',     'Fiche de controle en attente'
    FICHE_TECHNIQUE     = 'FICHE_TECHNIQUE',     'Fiche de controle établie'
    REPARATION_EN_COURS = 'REPARATION_EN_COURS', 'Réparation en cours'
    TRAVAUX_TERMINES    = 'TRAVAUX_TERMINES',    ' Travaux terminés'
    # Étape 3 : sortie
    BON_SORTIE_FAIT     = 'BON_SORTIE_FAIT',     'Bon de sortie établi'
