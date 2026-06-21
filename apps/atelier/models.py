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


class FicheControle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre_reparation = models.OneToOneField(
        OrdreReparation, on_delete=models.CASCADE,
        related_name='fiche_controle', verbose_name="Ordre de réparation"
    )
    # État général
    etat_general = models.CharField(max_length=20, choices=[
        ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')
    ], default='BON')
    niveau_carburant = models.IntegerField(default=0, help_text="0-100%")
    kilometrage = models.IntegerField(default=0, verbose_name="Kilométrage")
    # Éléments
    feux_avant = models.BooleanField(default=True)
    feux_arriere = models.BooleanField(default=True)
    feux_stop = models.BooleanField(default=True)
    clignotants = models.BooleanField(default=True)
    # Carrosserie
    carrosserie_avant = models.CharField(max_length=200, blank=True)
    carrosserie_arriere = models.CharField(max_length=200, blank=True)
    carrosserie_gauche = models.CharField(max_length=200, blank=True)
    carrosserie_droite = models.CharField(max_length=200, blank=True)
    # Pneus
    pneu_avant_gauche = models.CharField(max_length=20, choices=[
        ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('A_CHANGER', 'À changer')
    ], default='BON')
    pneu_avant_droit = models.CharField(max_length=20, choices=[
        ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('A_CHANGER', 'À changer')
    ], default='BON')
    pneu_arriere_gauche = models.CharField(max_length=20, choices=[
        ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('A_CHANGER', 'À changer')
    ], default='BON')
    pneu_arriere_droit = models.CharField(max_length=20, choices=[
        ('BON', 'Bon'), ('MOYEN', 'Moyen'), ('A_CHANGER', 'À changer')
    ], default='BON')
    # Intérieur
    tableau_bord = models.BooleanField(default=True)
    radio = models.BooleanField(default=False)
    climatisation = models.BooleanField(default=False)
    siege_conducteur = models.CharField(max_length=200, blank=True)
    tapis = models.BooleanField(default=True)
    # Accessoires présents
    roue_secours = models.BooleanField(default=False)
    cric = models.BooleanField(default=False)
    triangle = models.BooleanField(default=False)
    extincteur = models.BooleanField(default=False)
    # Défauts
    defauts_observes = models.TextField(blank=True)
    # Inspecteur
    inspecte_par = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='fiches_controle'
    )
    date_inspection = models.DateTimeField(auto_now_add=True)
    signature = models.TextField(blank=True, verbose_name="Signature numérique (base64)")

    class Meta:
        db_table = 'fiches_controle'
        verbose_name = "Fiche de contrôle"


class FicheTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  
    entre_id         = models.OneToOneField(
        'guerite.EnregistrementEntree', on_delete=models.PROTECT, related_name='fiche_technique'
    )
    diagnostic = models.TextField(verbose_name="Diagnostic technique")
    pieces_recommandees = models.TextField(blank=True, verbose_name="Pièces recommandées")
    main_oeuvre_estimee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pieces_estimees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    temps_estime_heures = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    observations = models.TextField(blank=True)
    cree_par = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='fiches_techniques'
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fiches_techniques'
        verbose_name = "Fiche technique"

    @property
    def total_estime(self):
        return self.main_oeuvre_estimee + self.pieces_estimees
