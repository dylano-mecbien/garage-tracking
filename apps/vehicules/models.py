"""
Modèles Véhicules, Clients, Conducteurs
"""
import uuid
from django.db import models



class Marque(models.Model):
    nom = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nom

    class Meta:
        ordering = ['nom']


class Modele(models.Model):
    nom = models.CharField(max_length=100)
    marque = models.ForeignKey(Marque, on_delete=models.CASCADE, related_name='modeles')

    class Meta:
        unique_together = ['nom', 'marque']  # Évite les doublons pour une même marque
        ordering = ['marque__nom', 'nom']

    def __str__(self):
        return f"{self.marque.nom} {self.nom}"
    

class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    TYPE_CLIENT = [('PARTICULIER', 'Particulier'), ('ENTREPRISE', 'Entreprise')]
    type_client = models.CharField(max_length=15, choices=TYPE_CLIENT, default='PARTICULIER')
    # Particulier
    nom = models.CharField(max_length=100, verbose_name="Nom / Raison sociale")
    prenom = models.CharField(max_length=100, blank=True)
    nom_correspondant = models.CharField(max_length=100, blank=True)
    # Coordonnées
    telephone = models.CharField(max_length=20)
    telephone2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    ville = models.CharField(max_length=100, blank=True)
    # Entreprise
    ninea = models.CharField(max_length=50, blank=True, verbose_name="NINEA / RC")
    # Fidélité
    numero_client = models.CharField(max_length=20, unique=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='clients_crees'
    )

    class Meta:
        db_table = 'clients'
        verbose_name = "Client"
        ordering = ['nom']

    def __str__(self):
        if self.prenom:
            return f"{self.prenom} {self.nom}"
        return self.nom

    def save(self, *args, **kwargs):
        if not self.numero_client:
            count = Client.objects.count() + 1
            self.numero_client = f"CLI-{count:05d}"
        super().save(*args, **kwargs)


class Conducteur(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=100, verbose_name="Nom")
    prenom = models.CharField(max_length=100, verbose_name="Prénom")
    telephone = models.CharField(max_length=20)
    telephone2 = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    cni = models.CharField(max_length=50, blank=True, verbose_name="N° CNI")
    permis = models.CharField(max_length=50, blank=True, verbose_name="N° Permis")
    categorie_permis = models.CharField(max_length=10, blank=True)
    adresse = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='conducteurs_crees'
    )

    class Meta:
        db_table = 'conducteurs'
        verbose_name = "Conducteur"
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.prenom} {self.nom}"


class Vehicule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    immatriculation = models.CharField(max_length=20, unique=True, verbose_name="Immatriculation")
    marque = models.CharField(max_length=50, verbose_name="Marque")
    modele = models.CharField(max_length=100, verbose_name="Modèle")
    annee = models.IntegerField(null=True, blank=True, verbose_name="Année")
    couleur = models.CharField(max_length=50,null=True, blank=True, verbose_name="Couleur")
    numero_chassis = models.CharField(max_length=50, blank=True, unique=True, null=True, verbose_name="N° Châssis")
    type_carburant = models.CharField(max_length=20, choices=[
        ('NON_DEFINI', 'Non défini'),
        ('ESSENCE', 'Essence'), ('DIESEL', 'Diesel'), ('ELECTRIQUE', 'Électrique'),
        ('HYBRIDE', 'Hybride'), ('GPL', 'GPL'),
    ], default='NON_DEFINI')
    puissance = models.IntegerField(null=True, blank=True, verbose_name="Puissance (CV)")
    transmission = models.CharField(max_length=20, choices=[
        ('NON_DEFINI', 'Non défini'),
        ('MANUELLE', 'Manuelle'), ('AUTOMATIQUE', 'Automatique')
    ], default='NON_DEFINI')
    # Propriétaire
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT,
        related_name='vehicules', verbose_name="Propriétaire"
    )
    # Photo 
    photo = models.ImageField(upload_to='vehicules/photos/', null=True, blank=True)
    
    photos = models.CharField(max_length=500, blank=True, null=True) # stocke les chemins séparés par ;
    # Assurance
    num_assurance = models.CharField(max_length=50, blank=True, verbose_name="N° Assurance")
    expiry_assurance = models.DateField(null=True, blank=True, verbose_name="Expiration assurance")
    # Visite technique
    date_visite = models.DateField(null=True, blank=True, verbose_name="Visite technique")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, 
        null=True, related_name='vehicules_crees'
    )

    class Meta:
        db_table = 'vehicules'
        verbose_name = "Véhicule"
        ordering = ['immatriculation']

    def __str__(self):
        return f"{self.immatriculation} - {self.marque} {self.modele} ({self.annee})"

    @property
    def derniere_entree(self):
        return self.entrees.order_by('-date_entree').first()

    @property
    def en_atelier(self):
        return self.ordres_reparation.filter(
            statut__in=['OUVERT', 'EN_COURS', 'REOUVERT']
        ).exists()
    

    @property
    def en_local(self):
        """
        Vérifie si le véhicule est actuellement présent
        dans les locaux du garage / à la guérite
        """
        return self.entrees.exclude(
             statut='SORTI'
        ).exists()
    
 
    @property
    def statut_presence(self):
        """
        Retourne un statut lisible
        """
        if self.en_local and self.en_atelier:
            return "Présent au garage / En atelier"

        if self.en_local:
            return "Présent au local"

        if self.en_atelier:
            return "En atelier"

        return "Hors garage"