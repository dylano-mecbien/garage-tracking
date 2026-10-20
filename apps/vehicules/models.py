"""
Modèles Véhicules, Clients, Conducteurs
"""
import uuid
from django.db import models
import re
from django.db import models, transaction
from django.core.exceptions import ValidationError



class ClientQuerySet(models.QuerySet):
    def principaux(self):
        """Entreprises et particuliers (sans les centres) : pour la liste des clients."""
        return self.filter(parent__isnull=True)
 
    def centres(self):
        return self.filter(parent__isnull=False)

    

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
    

class ContactBase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=100, verbose_name="Nom / Raison sociale")
    prenom = models.CharField(max_length=100, blank=True, verbose_name="Prénom")
    telephone = models.CharField(max_length=20,blank=True, verbose_name="Téléphone principal")
    telephone2 = models.CharField(max_length=20, blank=True, verbose_name="Téléphone secondaire")
    email = models.EmailField(blank=True, verbose_name="Adresse email")
    adresse = models.TextField(blank=True, verbose_name="Adresse")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    
    # %(class)s_crees génère dynamiquement 'client_crees' et 'conducteur_crees'
    created_by = models.ForeignKey(
        'accounts.User', 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True,
        related_name='%(class)s_crees'
    )

    class Meta:
        abstract = True  # Ne crée AUCUNE table en base de données

    def __str__(self):
        if self.prenom:
            return f"{self.prenom} {self.nom}".strip()
        return self.nom.strip()


class Client(ContactBase):
    TYPE_CLIENT = [('PARTICULIER', 'Particulier'), ('ENTREPRISE', 'Entreprise')]
    type_client = models.CharField(max_length=15, choices=TYPE_CLIENT, default='PARTICULIER')
    nom_correspondant = models.CharField(max_length=100, blank=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE,
        related_name='centres', verbose_name="Entreprise mère",
    )
    ville = models.CharField(max_length=100, blank=True)
    ninea = models.CharField(max_length=50, blank=True, verbose_name="NINEA / RC")
    numero_client = models.CharField(max_length=20, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'clients'
        verbose_name = "Client"
        ordering = ['nom']



    def save(self, *args, **kwargs):
        if not self.numero_client:
            with transaction.atomic():
            # Cherche le plus grand numéro existant (y compris soft-deleted si tu en as)
                last = (
                    Client.objects
                    .select_for_update()
                    .filter(numero_client__startswith='CLI-')
                    .order_by('-numero_client')
                    .values_list('numero_client', flat=True)
                    .first()
                )
                if last:
                    match = re.search(r'(\d+)$', last)
                    next_num = int(match.group(1)) + 1 if match else 1
                else:
                    next_num = 1

                self.numero_client = f"CLI-{next_num:05d}"

            # En cas de collision rare (concurrence), on réessaie
                while Client.objects.filter(numero_client=self.numero_client).exists():
                    next_num += 1
                    self.numero_client = f"CLI-{next_num:05d}"

                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


    def tous_vehicules(self):
        """Véhicules du client + de ses centres (utilise les prefetch si présents)."""
        vs = list(self.vehicules.all())
        for centre in self.centres.all():
            vs.extend(centre.vehicules.all())
        return vs

    @property
    def est_centre(self):
        return self.parent_id is not None
 
    @property
    def peut_avoir_centres(self):
        return self.type_client == 'ENTREPRISE' and self.parent_id is None
 
    @property
    def entreprise(self):
        """L'entreprise de rattachement (lui-même si ce n'est pas un centre)."""
        return self.parent if self.parent_id else self
    
    def clean(self):
        super().clean()
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError({'parent': "Un client ne peut pas être son propre centre."})
            if self.parent.parent_id:
                raise ValidationError({'parent': "Un centre ne peut pas avoir de sous-centre."})
            if self.parent.type_client != 'ENTREPRISE':
                raise ValidationError({'parent': "Seule une entreprise peut avoir des centres."})

 
    def __str__(self):
        # ⚠️ garde ton __str__ actuel pour les clients, ajoute juste le cas centre :
        nom = f"{self.prenom} {self.nom}".strip() if self.type_client == 'PARTICULIER' else self.nom
        if self.parent_id:
            return f"{self.parent.nom} — {nom}"
        return nom
    
class Conducteur(ContactBase):
    cni = models.CharField(max_length=50, blank=True, verbose_name="N° CNI")
    permis = models.CharField(max_length=50, blank=True, verbose_name="N° Permis")
    categorie_permis = models.CharField(max_length=10, blank=True)
    
    # Lien optionnel vers un compte client (ex: chauffeur d'une entreprise)
    client = models.ForeignKey(
        Client, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='conducteurs',
        verbose_name="Client rattaché"
    )

    class Meta:
        db_table = 'conducteurs'
        verbose_name = "Conducteur"
        ordering = ['nom', 'prenom']





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
    num_assurance = models.CharField(max_length=50, blank=True, verbose_name="Nom Assurance")
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
