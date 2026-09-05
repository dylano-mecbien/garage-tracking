"""
Modèles Atelier
"""
import uuid
from django.db import models
from django.utils import timezone

from apps.guerite.models import EnregistrementEntree


class Atelier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    nom = models.CharField(max_length=100, verbose_name="Nom de l'atelier")
    description = models.TextField(blank=True, verbose_name="Description")
    localisation = models.CharField(max_length=200, blank=True, verbose_name="Localisation")
    capacite = models.IntegerField(default=10, verbose_name="Capacité (véhicules)")
    responsable = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='atelier_dirige',
        verbose_name="Responsable"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ateliers'
        verbose_name = "Atelier"
        verbose_name_plural = "Ateliers"
        ordering = ['nom']

    def __str__(self):
        return f"{self.code} - {self.nom}"

    def vehicules_en_cours(self):
        return self.ordres_reparation.filter(
            statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']
        ).count()


class TypeOperation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True)
    libelle = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    duree_estimee_minutes = models.IntegerField(default=60)
    tarif_unitaire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'types_operations'
        verbose_name = "Type d'opération"

    def __str__(self):
        return f"{self.code} - {self.libelle}"


class StatutOR(models.TextChoices):
    OUVERT = 'OUVERT', 'Ouvert'
    EN_COURS = 'EN_COURS', 'En cours'
    CLOTURE = 'CLOTURE', 'Clôturé'
    ANNULE = 'ANNULE', 'Annulé'
    REOUVERT = 'REOUVERT', 'Réouvert'


class TypeOR(models.TextChoices):
    NORMAL = 'NORMAL', 'Normal'
    RETOUR = 'RETOUR', 'Retour / Malfaçon'


class OrdreReparation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero = models.CharField(max_length=20, unique=True, verbose_name="N° OR")
    type_or = models.CharField(max_length=10, choices=TypeOR.choices, default=TypeOR.NORMAL)
    statut = models.CharField(max_length=15, choices=StatutOR.choices, default=StatutOR.OUVERT)
    vehicule = models.ForeignKey(
        'vehicules.Vehicule', on_delete=models.PROTECT,
        related_name='ordres_reparation', verbose_name="Véhicule"
    ) 
    atelier = models.ForeignKey(
        Atelier, on_delete=models.PROTECT,
        related_name='ordres_reparation', verbose_name="Atelier"
    )
    responsable_atelier = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='or_responsable',
        verbose_name="Responsable atelier"
    )
    reception = models.ForeignKey(
        'reception.Reception', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ordres_reparation',
        verbose_name="Réception"
    )
    # OR retour
    or_origine = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='or_retours',
        verbose_name="OR d'origine (retour)"
    )
    motif_retour = models.TextField(blank=True, verbose_name="Motif retour")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin_prevue = models.DateTimeField(null=True, blank=True)
    date_cloture = models.DateTimeField(null=True, blank=True)
    date_reouverture = models.DateTimeField(null=True, blank=True)
    raison_reouverture = models.TextField(blank=True)

    diagnostic = models.TextField(blank=True, verbose_name="Diagnostic")
    observations = models.TextField(blank=True, verbose_name="Observations")
    duree_totale_minutes = models.IntegerField(default=0, verbose_name="Durée totale (min)")

    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='or_crees', verbose_name="Créé par"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ordres_reparation'
        verbose_name = "Ordre de réparation"
        verbose_name_plural = "Ordres de réparation"
        ordering = ['-date_creation']

    def __str__(self):
        return f"OR-{self.numero} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            from django.utils import timezone
            now = timezone.now()
            count = OrdreReparation.objects.filter(
                date_creation__year=now.year,
                date_creation__month=now.month
            ).count() + 1
            prefix = 'ORT' if self.type_or == TypeOR.RETOUR else 'OR'
            self.numero = f"{prefix}-{now.strftime('%Y%m')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def duree_heures(self):
        h = self.duree_totale_minutes // 60
        m = self.duree_totale_minutes % 60
        return f"{h}h{m:02d}"


class StatutTache(models.TextChoices):
    A_FAIRE = 'A_FAIRE', 'À faire'
    EN_COURS = 'EN_COURS', 'En cours'
    TERMINEE = 'TERMINEE', 'Terminée'


class PrioriteTache(models.TextChoices):
    BASSE = 'BASSE', 'Basse'
    NORMALE = 'NORMALE', 'Normale'
    HAUTE = 'HAUTE', 'Haute'
    URGENTE = 'URGENTE', 'Urgente'


class Tache(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre_reparation = models.ForeignKey(
        OrdreReparation, on_delete=models.CASCADE,
        related_name='taches', verbose_name="Ordre de réparation"
    )
    type_operation = models.ForeignKey(
        TypeOperation, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Type d'opération"
    )
    libelle = models.CharField(max_length=200, verbose_name="Libellé")
    description = models.TextField(blank=True)
    statut = models.CharField(max_length=15, choices=StatutTache.choices, default=StatutTache.A_FAIRE)
    priorite = models.CharField(max_length=10, choices=PrioriteTache.choices, default=PrioriteTache.NORMALE)
    technicien = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='taches_assignees',
        verbose_name="Technicien assigné"
    )
    duree_estimee_minutes = models.IntegerField(default=60, verbose_name="Durée estimée (min)")
    duree_reelle_minutes = models.IntegerField(default=0, verbose_name="Durée réelle (min)")
    date_debut = models.DateTimeField(null=True, blank=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    # Pour OR retour - copiée depuis OR précédent
    est_copiee = models.BooleanField(default=False)
    tache_origine = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='copies'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'taches'
        verbose_name = "Tâche"
        ordering = ['priorite', 'created_at']

    def __str__(self):
        return f"{self.libelle} - {self.get_statut_display()}"


class CompteRenduIntervention(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tache = models.ForeignKey(
        Tache, on_delete=models.CASCADE,
        related_name='comptes_rendus', verbose_name="Tâche"
    )
    technicien = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='comptes_rendus',
        verbose_name="Technicien"
    )
    description = models.TextField(verbose_name="Description de l'intervention")
    duree_minutes = models.IntegerField(verbose_name="Durée (minutes)")
    pieces_utilisees = models.TextField(blank=True, verbose_name="Pièces utilisées")
    observations = models.TextField(blank=True, verbose_name="Observations")
    date_saisie = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'comptes_rendus_intervention'
        verbose_name = "Compte rendu d'intervention"
        ordering = ['-date_saisie']

    def __str__(self):
        return f"CR - {self.tache.libelle} par {self.technicien}"


class PhotoIntervention(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compte_rendu = models.ForeignKey(
        CompteRenduIntervention, on_delete=models.CASCADE,
        related_name='photos'
    )
    photo = models.ImageField(upload_to='interventions/photos/')
    legende = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'photos_intervention'





BON_DEFAUT = [('BON', 'Bon'), ('DEFAUT', 'Défaut')]
OUI_NON = [('OUI', 'Oui'), ('NON', 'Non')]


class FicheTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_fiche = models.CharField(max_length=20, blank=True, verbose_name="N° fiche")
    entre_id = models.OneToOneField(
        'guerite.EnregistrementEntree', on_delete=models.PROTECT, related_name='fiche_technique'
    )

    # ------------------------------------------------------------------
    # En-tête
    # ------------------------------------------------------------------
    entree_le = models.DateField(null=True, blank=True)
    sortie_le = models.DateField(null=True, blank=True)
    nom_client = models.CharField(max_length=100, blank=True)
    immatriculation = models.CharField(max_length=20, blank=True)
    vehicule = models.CharField(max_length=100, blank=True, verbose_name="Véhicule")
    kilometrage = models.IntegerField(default=0)
    preconisation_courroie_distribution = models.DateField(null=True, blank=True)
    rendre_pieces = models.CharField(max_length=3, choices=OUI_NON, blank=True)
    ecrou_antivol = models.CharField(max_length=3, choices=OUI_NON, blank=True)
    alarme = models.CharField(max_length=3, choices=OUI_NON, blank=True)

    # ==================================================================
    # VEHICULE AU SOL
    # ==================================================================

    # --- Éclairage AV ---
    eclairage_av_veilleuses = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_av_croisement = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_av_route = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_av_antibrouillard = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_av_clignotants = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Éclairage AR ---
    eclairage_ar_feux_position = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_ar_stop = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_ar_clignotants = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_ar_recul = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_ar_antibrouillard = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_ar_feu_plaque = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    eclairage_ar_3eme_feu_stop = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    controle_hauteur_phare = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Électronique ---
    voyant_tableau_bord = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    code_defaut = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Allumage ---
    bougies_faisceau = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    sonde_lamda = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Freinage (au sol) ---
    course_pedale_frein = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    course_frein_main = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    liquide_frein_temperature = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="°C")
    liquide_frein_etat = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    maitre_cylindre_fuite = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Climatisation ---
    climatisation_temperature_soufflage = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="°C")
    climatisation_filtre_habitacle = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Niveau d'huile à la prise en charge ---
    niveau_huile_prise_en_charge = models.CharField(
        max_length=10, choices=[('MINI', 'Mini'), ('CORRECT', 'Correct'), ('MAXI', 'Maxi')], blank=True
    )

    # --- Pare-brise ---
    balais_essuie_glace_av = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    balais_essuie_glace_ar = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    pare_brise_impact = models.CharField(max_length=3, choices=OUI_NON, blank=True)
    pare_brise_fissure = models.CharField(max_length=3, choices=OUI_NON, blank=True)
    pare_brise_fissure_appeler_le = models.CharField(max_length=20, blank=True)

    # --- Jauge carburant ---
    jauge_carburant = models.CharField(
        max_length=15,
        choices=[('E', 'Vide (E)'), ('QUART', '1/4'), ('DEMI', '1/2'), ('TROIS_QUARTS', '3/4'), ('F', 'Plein (F)')],
        blank=True
    )

    # --- Plaques d'immatriculation ---
    plaques_immatriculation_av = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    plaques_immatriculation_ar = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Charge / Démarrage ---
    batterie = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    alternateur_demarreur = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    liquide_refroidissement = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # ==================================================================
    # VEHICULE MI HAUTEUR
    # ==================================================================

    # --- Pneumatiques (profondeur en mm, usure Bon/Défaut) ---
    pneu_av_g_profondeur = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="mm")
    pneu_av_d_profondeur = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="mm")
    pneu_ar_g_profondeur = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="mm")
    pneu_ar_d_profondeur = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="mm")
    pneu_roue_secours_profondeur = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="mm")

    pneu_av_g_usure = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    pneu_av_d_usure = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    pneu_ar_g_usure = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    pneu_ar_d_usure = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    geometrie_necessaire = models.CharField(max_length=3, choices=OUI_NON, blank=True)

    # --- Suspension (AV/AR, G/D) ---
    susp_amortisseurs_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_amortisseurs_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_amortisseurs_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_amortisseurs_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    susp_coupelles_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_coupelles_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_coupelles_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_coupelles_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    susp_ressorts_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_ressorts_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_ressorts_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_ressorts_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    susp_kit_protection_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_kit_protection_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_kit_protection_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_kit_protection_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    susp_butees_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_butees_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_butees_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_butees_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    susp_biellettes_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_biellettes_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_biellettes_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    susp_biellettes_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Freinage (mi-hauteur, AV/AR, G/D) ---
    frein_flexibles_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_flexibles_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_flexibles_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_flexibles_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    frein_disques_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_disques_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_disques_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_disques_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_disques_epaisseur_mm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    frein_plaquettes_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_plaquettes_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_plaquettes_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_plaquettes_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    frein_kit_frein_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_kit_frein_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    frein_tambours_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_tambours_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_tambours_diametre_mm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    # --- Train roulant (AV/AR, G/D) ---
    train_flexibles_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_flexibles_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_flexibles_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_flexibles_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    train_disques_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_disques_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_disques_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_disques_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    train_plaquettes_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_plaquettes_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_plaquettes_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_plaquettes_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    train_kit_frein_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_kit_frein_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    train_tambours_av_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_tambours_av_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_tambours_ar_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    train_tambours_ar_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # ==================================================================
    # VEHICULE LEVE
    # ==================================================================

    # --- Échappement ---
    echap_catalyseur_filtre_particules = models.CharField(max_length=10, blank=True, help_text="'/' si non applicable")
    echap_partie_avant = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    echap_partie_intermediaire = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    echap_partie_arriere = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    echap_fixations = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Transmission ---
    transmission_soufflets_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    transmission_soufflets_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    transmission_cardans_g = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    transmission_cardans_d = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Freinage (véhicule levé) ---
    frein_canalisation = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_cable_frein_main = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)
    frein_repartiteur_fuite = models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)

    # --- Moteur ---
    fuite_moteur = models.CharField(max_length=3, choices=OUI_NON, blank=True)

    # ==================================================================
    # POST-CONTRÔLES ET MISES A NIVEAU
    # ==================================================================
    niveau_huile_apres_intervention = models.CharField(
        max_length=10, choices=[('MINI', 'Mini'), ('CORRECT', 'Correct'), ('MAXI', 'Maxi')], blank=True
    )
    ok_lave_glace = models.BooleanField(default=False, verbose_name="Lave-glace *Ok")
    ok_liquide_refroidissement = models.BooleanField(default=False, verbose_name="Liquide de refroidissement *Ok")
    ok_kit_securite = models.BooleanField(default=False, verbose_name="Kit sécurité (cales, extincteur, triangles) *Ok")
    ok_boite_ampoules = models.BooleanField(default=False, verbose_name="Boîte d'ampoules (boîte à pharmacie) *Ok")
    ok_etiquette_vidange = models.BooleanField(default=False, verbose_name="Mise en place étiquette vidange *Ok")
    ok_etiquette_monte_pneumatique = models.BooleanField(default=False, verbose_name="Mise en place étiquette monte pneumatique *Ok")
    ok_remise_a_zero_maintenance = models.BooleanField(default=False, verbose_name="Remise à zéro indicateur de maintenance *Ok")

    # ==================================================================
    # Diagnostic, chiffrage & synthèse
    # ==================================================================
    diagnostic = models.TextField(verbose_name="Diagnostic technique")
    pieces_recommandees = models.TextField(blank=True, verbose_name="Pièces recommandées")
    main_oeuvre_estimee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pieces_estimees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    temps_estime_heures = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    commentaires = models.TextField(blank=True)
    observations = models.TextField(blank=True)

    # --- Signatures ---
    nom_controleur = models.CharField(max_length=100, blank=True)
    signature_controleur = models.TextField(blank=True, help_text="base64")
    nom_client_signataire = models.CharField(max_length=100, blank=True)
    signature_client = models.TextField(blank=True, help_text="base64")

    cree_par = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='fiches_techniques'
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fiches_techniques'
        verbose_name = "Fiche technique"
        verbose_name_plural = "Fiches techniques"

    @property
    def total_estime(self):
        return self.main_oeuvre_estimee + self.pieces_estimees

    def __str__(self):
        return f"Fiche diagnostic {self.numero_fiche or self.id} - {self.immatriculation}"






class FicheControle(models.Model):
    STATUT_CHOICES = [('BON', 'Bon'), ('DEFAUT', 'Défaut')]
    ETAT_VITRE_CHOICES = [
        ('INTACT', 'Intact'), ('FISSURE', 'Fissuré'), ('CASSE', 'Cassé'),
    ]
    TYPE_VEHICULE_CHOICES = [
        ('VOITURE', 'Voiture'), ('PICKUP', 'Pick-up'),
        ('CAMION_CITERNE', 'Camion-citerne'), ('BENNE', 'Camion benne'),
        ('FOURGON', 'Fourgon / Van'),
    ]
    JAUGE_CHOICES = [
        ('E', 'Vide (E)'), ('QUART', '1/4'), ('DEMI', '1/2'),
        ('TROIS_QUARTS', '3/4'), ('F', 'Plein (F)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre_reparation = models.OneToOneField(
        'OrdreReparation', on_delete=models.CASCADE,
        related_name='fiche_controle', verbose_name="Ordre de réparation"
    )

    # ------------------------------------------------------------------
    # En-tête
    # ------------------------------------------------------------------
    travail_a_effectuer = models.TextField(blank=True, verbose_name="Travail à effectuer")
    entree_le = models.DateField(null=True, blank=True, verbose_name="Entrée le")
    sortir_le = models.DateField(null=True, blank=True, verbose_name="Sortie le")
    immatriculation = models.CharField(max_length=20, blank=True)
    marque = models.CharField(max_length=50, blank=True)
    modele = models.CharField(max_length=50, blank=True)
    kilometrage = models.IntegerField(default=0, verbose_name="Kilométrage")
    telephone = models.CharField(max_length=20, blank=True)

    # ------------------------------------------------------------------
    # Colonne 1 — Sécurité / accessoires / carrosserie extérieure
    # ------------------------------------------------------------------
    alarme_fonctionne = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    verrouillage_portes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    telecommande_ouverture = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    trappe_carburant = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    tirette_capot = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    climatisation_fonctionne = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    climatisation_fait_froid = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    voyant_moteur_tableau_bord = models.BooleanField(null=True, blank=True, verbose_name="Voyant moteur allumé (Oui/Non)")
    autoradio_s_allume = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    son_dans_baffles = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    dossier_vehicule_complet = models.BooleanField(null=True, blank=True, verbose_name="Dossier complet (assurance, carte rose/grise, visite technique)")
    horloge_a_heure = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)

    triangles_securite_presents = models.BooleanField(null=True, blank=True)
    triangles_securite_nombre = models.PositiveSmallIntegerField(null=True, blank=True)

    cales_metalliques_presentes = models.BooleanField(null=True, blank=True)
    cales_metalliques_nombre = models.PositiveSmallIntegerField(null=True, blank=True)

    gilet_securite_present = models.BooleanField(null=True, blank=True)
    extincteur_present = models.BooleanField(null=True, blank=True)
    boite_pharmacie_presente = models.BooleanField(null=True, blank=True)
    bouton_eclairage_plafonnier = models.BooleanField(null=True, blank=True)
    roue_secours_gonflee = models.BooleanField(null=True, blank=True)

    cric_present = models.BooleanField(default=False)
    manivelle_presente = models.BooleanField(default=False)
    cle_roue_presente = models.BooleanField(default=False)

    joints_portieres_propres = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    enjoliveurs_roues_presents = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    plaques_immatriculation_avant_arriere = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    tares_avant_arriere_presentes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    garde_boues_presents_bien_montes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    agrafes_presentes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)

    # ------------------------------------------------------------------
    # Colonne 2 — Éléments mécaniques / visibilité / éclairage
    # ------------------------------------------------------------------
    bavettes_et_goujons_roues_presents = models.BooleanField(null=True, blank=True)
    pare_brise_etat = models.CharField(max_length=10, choices=ETAT_VITRE_CHOICES, blank=True)
    pression_pneus_bonne = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    balais_essuie_glace_avant_arriere = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    gicleur_lave_glace_bocal_reserve = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    miroirs_retroviseurs_etat = models.CharField(max_length=10, choices=ETAT_VITRE_CHOICES, blank=True)
    retroviseurs_se_rabattent = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    phares_avant_etat = models.CharField(max_length=10, choices=ETAT_VITRE_CHOICES, blank=True)
    camera_recul_fonctionne = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    klaxon_fonctionne = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    clignotants_avant_arriere_fonctionnent = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    capteurs_position_avant_arriere_bipent = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    antibrouillards_feux_jour_bon_etat = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    feux_arriere_etat = models.CharField(max_length=10, choices=ETAT_VITRE_CHOICES, blank=True)
    systeme_demarrage_fonctionne = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    voyant_ceintures_securite_s_allume = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)

    # ------------------------------------------------------------------
    # Colonne 3 — Intérieur / jauge / carrosserie
    # ------------------------------------------------------------------
    sieges_propres_bon_etat = models.BooleanField(null=True, blank=True)
    tapis_sol_5_presents = models.BooleanField(null=True, blank=True)
    vitres_avant_se_baissent = models.BooleanField(null=True, blank=True)
    vitres_arriere_se_baissent = models.BooleanField(null=True, blank=True)
    telecommande_vitres_fonctionne = models.BooleanField(null=True, blank=True)
    autocollants_pare_brise_presents = models.BooleanField(null=True, blank=True, help_text="Si pare-brise à remplacer")
    voiles_peinture_sur_vitres = models.BooleanField(null=True, blank=True)

    jauge_carburant = models.CharField(max_length=15, choices=JAUGE_CHOICES, blank=True)

    # ------------------------------------------------------------------
    # Schéma carrosserie (dégâts) — X Piqûre, & Rayures, O Bosses, /// Casses
    # ------------------------------------------------------------------
    type_vehicule = models.CharField(max_length=20, choices=TYPE_VEHICULE_CHOICES, blank=True)
    points_degats_carrosserie = models.JSONField(
        default=list, blank=True,
        help_text="Liste de points sur le schéma: [{'x':.., 'y':.., 'type':'PIQURE|RAYURE|BOSSE|CASSE'}, ...]"
    )

    # ------------------------------------------------------------------
    # Commentaires & synthèse
    # ------------------------------------------------------------------
    etat_general = models.CharField(max_length=20, choices=[
        ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')
    ], default='BON')
    commentaires = models.TextField(blank=True)
    defauts_observes = models.TextField(blank=True)

    # ------------------------------------------------------------------
    # Signatures (5 blocs présents sur la fiche)
    # ------------------------------------------------------------------
    nom_receptionniste = models.CharField(max_length=100, blank=True)
    signature_receptionniste = models.TextField(blank=True, help_text="base64")

    nom_client_avant = models.CharField(max_length=100, blank=True)
    signature_client_avant = models.TextField(blank=True, help_text="base64")

    nom_client_apres = models.CharField(max_length=100, blank=True)
    signature_client_apres = models.TextField(blank=True, help_text="base64")

    nom_technicien = models.CharField(max_length=100, blank=True)
    signature_technicien = models.TextField(blank=True, help_text="base64")

    nom_controleur = models.CharField(max_length=100, blank=True)
    signature_controleur = models.TextField(blank=True, help_text="base64")

    # ------------------------------------------------------------------
    inspecte_par = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='fiches_controle'
    )
    date_inspection = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fiches_controle'
        verbose_name = "Fiche de contrôle"
        verbose_name_plural = "Fiches de contrôle"

    def __str__(self):
        return f"Fiche contrôle - {self.immatriculation or self.ordre_reparation_id}"