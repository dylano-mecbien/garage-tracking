import uuid
from django.db import models
from django.utils import timezone


class DestinataireEmail(models.Model):
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email   = models.EmailField(unique=True, verbose_name="Adresse email")
    nom     = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nom (optionnel)")
    actif   = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table  = 'destinataires_emails'
        verbose_name = "Destinataire email"
        verbose_name_plural = "Destinataires emails"
        ordering  = ['email']

    def __str__(self):
        return f"{self.nom or self.email} ({'Actif' if self.actif else 'Inactif'})"