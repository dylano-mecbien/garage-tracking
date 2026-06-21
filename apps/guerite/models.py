"""
Modèles Guérite - Entrées et Sorties véhicules
"""
import uuid
from django.db import models
from django.utils import timezone


class MotifEntree(models.TextChoices):
    VISITE = 'VISITE', 'Visite'
    REPARATION = 'REPARATION', 'Réparation'



class StatutEntree(models.TextChoices):
    GARAGE= 'GARAGE', 'garage'
    EN_COURS = 'EN_COURS', 'En cours (dans garage)'
    SORTI = 'SORTI', 'Sorti'

class StatutViewHinstorisue(models.TextChoices):
    PRESENT = 'PRESENT', 'Présent (dans garage)'
    SORTI = 'SORTI', 'Sorti'


class EnregistrementEntree(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero = models.CharField(max_length=20, unique=True, verbose_name="N° Entrée")
    vehicule = models.ForeignKey(
        'vehicules.Vehicule', on_delete=models.PROTECT,
        related_name='entrees', verbose_name="Véhicule"
    )
    conducteur = models.ForeignKey(
        'vehicules.Conducteur', on_delete=models.SET_NULL,
        null=True, related_name='entrees',
        verbose_name="Conducteur"
    )
    motif = models.CharField(max_length=20, choices=MotifEntree.choices, verbose_name="Motif")
    statut = models.CharField(max_length=15, choices=StatutEntree.choices, default=StatutEntree.EN_COURS)
    date_entree = models.DateTimeField(default=timezone.now, verbose_name="Date/heure entrée")
    date_sortie = models.DateTimeField(null=True, blank=True, verbose_name="Date/heure sortie")
    kilometrage_entree = models.IntegerField(default=0, verbose_name="Kilométrage à l'entrée")
    observations = models.TextField(blank=True, verbose_name="Observations entrée")

    agent_entree = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='entrees_enregistrees',
        verbose_name="Agent guérite (entrée)"
    )
    agent_sortie = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sorties_enregistrees',
        verbose_name="Agent guérite (sortie)"
    )
    bon_sortie = models.ForeignKey(
        'BonSortie', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='entrees_liees',
        verbose_name="Bon de sortie"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'enregistrements_entree'
        verbose_name = "Enregistrement d'entrée"
        verbose_name_plural = "Enregistrements d'entrée"
        ordering = ['-date_entree']

    def __str__(self):
        return f"{self.numero} - {self.vehicule.immatriculation}"

    def save(self, *args, **kwargs):
        if not self.numero:
            now = timezone.now()
            count = EnregistrementEntree.objects.filter(
                date_entree__date=now.date()
            ).count() + 1
            self.numero = f"ENT-{now.strftime('%Y%m%d')}-{count:03d}"
        super().save(*args, **kwargs)

    @property
    def duree_sejour(self):
        fin = self.date_sortie or timezone.now()
        delta = fin - self.date_entree
        heures = delta.total_seconds() // 3600
        return f"{int(heures)}h"




class TypeBon(models.TextChoices):
    VEHICULE = 'VEHICULE', 'Véhicule'
    DIVERS = 'DIVERS', 'Divers'

class EtatBon(models.TextChoices):
    CREER = 'CREER', 'Créer'
    APPROBATION = 'APPROBATION', 'Approbation'
    VALIDER = 'VALIDER', 'Valider'


class BonSortie(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    numero = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="N° Bon de sortie"
    )

    types = models.CharField(
        max_length=20,
        choices=TypeBon.choices,
        default=TypeBon.VEHICULE,
        verbose_name="Type"
    )
    etats = models.CharField(
        max_length=20,
        choices=EtatBon.choices,
        default=EtatBon.CREER,
        verbose_name="Etat"
    )

    vehicule = models.ForeignKey(
        'vehicules.Vehicule',
        on_delete=models.PROTECT,
        related_name='bons_sortie',
        verbose_name="Véhicule",
        null=True,
        blank=True
    )

    reception = models.ForeignKey(
        'reception.Reception',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_sortie',
        verbose_name="Réception associée"
    )

    nom_demandeur = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Nom du demandeur"
    )
    Origine_demande = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="origine du demandeur"
    )

    observations = models.TextField(
        blank=True,
        verbose_name="Observations"
    )

    # Signature numérique
    signature_client = models.TextField(
        blank=True,
        verbose_name="Signature client (base64)"
    )

    # PDF
    pdf = models.FileField(
        upload_to='bons_sortie/pdf/',
        null=True,
        blank=True
    )

    # Validation
    est_valide = models.BooleanField(
        default=False,
        verbose_name="Validé"
    )

    valide_par = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_valides'
    )

    date_validation = models.DateTimeField(
        null=True,
        blank=True
    )

    # Création
    cree_par = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='bons_crees'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bons_sortie'
        verbose_name = "Bon de sortie"
        verbose_name_plural = "Bons de sortie"
        ordering = ['-created_at']

    def __str__(self):
        if self.vehicule:
            return f"{self.numero} - {self.vehicule.immatriculation}"
        return f"{self.numero} - Divers"

    def save(self, *args, **kwargs):
        if not self.numero:
            now = timezone.now()
            count = BonSortie.objects.count() + 1
            self.numero = f"BS-{now.strftime('%Y%m')}-{count:04d}"

        if self.est_valide and not self.date_validation:
            self.date_validation = timezone.now()

        super().save(*args, **kwargs)


