"""
Modèles Comptes & Rôles
"""
import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone





class Role(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrateur'
    GUERITE = 'GUERITE', 'Agent Guérite'
    RECEPTIONNISTE = 'RECEPTIONNISTE', 'Réceptionniste'
    SUPER_RECEPTIONNISTE = 'SUPER_RECEPTIONNISTE', 'Super_Réceptionniste'
    RESP_ATELIER = 'RESP_ATELIER', 'Responsable Atelier'
    TECHNICIEN = 'TECHNICIEN', 'Technicien / Intervenant'


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', Role.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)



class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True)
    matricule = models.CharField(max_length=20, unique=True, null=True, blank=True)

    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.GUERITE
    )
    atelier = models.ForeignKey(
        'atelier.Atelier',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employes'
    )

    photo = models.ImageField(upload_to='users/photos/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    pass_default = models.BooleanField(default=True)

    date_joined = models.DateTimeField(default=timezone.now)

    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_count = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nom', 'prenom']

    objects = UserManager()

    class Meta:
        db_table = 'accounts_users'
        ordering = ['nom', 'prenom']

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.get_role_display()})"

    @property
    def full_name(self):
        return f"{self.prenom} {self.nom}"

    def is_admin(self):
        return self.role == Role.ADMIN

    def is_guerite(self):
        return self.role == Role.GUERITE

    def is_receptionniste(self):
        return self.role == Role.RECEPTIONNISTE
    
    def is_super_receptionniste(self):
        return self.role == Role.SUPER_RECEPTIONNISTE

    def is_resp_atelier(self):
        return self.role == Role.RESP_ATELIER

    def is_technicien(self):
        return self.role == Role.TECHNICIEN

    def get_dashboard_url(self):
        urls = {
            Role.ADMIN: '/admin/admin-garage/dashboard/',
            Role.GUERITE: '/guerite/dashboard/',
            Role.RECEPTIONNISTE: '/reception/dashboard/',
            Role.SUPER_RECEPTIONNISTE: '/reception/dashboard/',
            Role.RESP_ATELIER: '/atelier/dashboard/',
            Role.TECHNICIEN: '/atelier/technicien/dashboard/',
        }
        return urls.get(self.role, '/dashboard/')


class LoginAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    success = models.BooleanField(default=False)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'login_attempts'
        verbose_name = 'Tentative de connexion'
        ordering = ['-timestamp']


class Demandeur(models.Model):
    """
    Personne externe (ni client, ni employé) pouvant demander un bon
    de sortie divers. Créée à la volée depuis l'autocomplétion si elle
    n'existe pas encore parmi les Clients ou les Employés.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=150, verbose_name="Nom")
    numero = models.CharField(max_length=30, unique=True, verbose_name="Numéro / téléphone")
    description = models.CharField(max_length=255, blank=True, default='', verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Demandeur"
        verbose_name_plural = "Demandeurs"
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.numero})"
    

 
