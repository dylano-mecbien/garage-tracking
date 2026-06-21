"""
Audit Logs - Traçabilité complète
"""
import uuid
from django.db import models


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


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='audit_logs'
    )
    action = models.CharField(max_length=25, choices=ActionType.choices)
    module = models.CharField(max_length=50, verbose_name="Module")
    objet_type = models.CharField(max_length=100, blank=True, verbose_name="Type d'objet")
    objet_id = models.CharField(max_length=100, blank=True, verbose_name="ID objet")
    objet_repr = models.CharField(max_length=200, blank=True, verbose_name="Représentation")
    details = models.JSONField(null=True, blank=True, verbose_name="Détails")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        verbose_name = "Log d'audit"
        verbose_name_plural = "Logs d'audit"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} | {self.user} | {self.action} | {self.module}"
