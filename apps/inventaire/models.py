"""
apps/inventaire/models.py — UN SEUL inventaire (plus de jour/nuit).

  Inventaire          : une session de la guérite → EN_COURS → SOUMIS (validé par la guérite, e-mail à l'admin)
                        → VALIDE (décision de l'administrateur) ou REVOQUE.
  LigneInventaire     : un véhicule que le système croit présent, marqué Présent / Absent par la guérite.
  MouvementTemporaire : la TABLE TEMPORAIRE. Une ligne par mouvement à valider :
                          ENTREE = véhicule présent sur le site mais absent du système (« Faire entrer »)
                          SORTIE = véhicule que le système croit présent mais marqué Absent
                        Supprimée dès que l'administrateur a validé (le mouvement devient définitif) ou révoqué.
"""
import uuid
from django.db import models
from django.utils import timezone

from apps.accounts.choices import Presence, StatutInventaire, TypeMouvement





class Inventaire(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField(default=timezone.localdate)
    statut = models.CharField(max_length=10, choices=StatutInventaire.choices, default=StatutInventaire.EN_COURS)

    cree_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='+')
    date_creation = models.DateTimeField(auto_now_add=True)

    soumis_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    date_soumission = models.DateTimeField(null=True, blank=True)
    observation = models.TextField(blank=True)

    decide_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    date_decision = models.DateTimeField(null=True, blank=True)
    motif_revocation = models.TextField(blank=True)
    # Journal figé à la décision (la table temporaire, elle, est vidée)
    rapport = models.JSONField(default=dict, blank=True)

    email_envoye = models.BooleanField(default=False)
    email_erreur = models.TextField(blank=True)

    class Meta:
        db_table = 'inv_inventaire'
        ordering = ['-date_creation']

    def __str__(self):
        return f"Inventaire du {self.date:%d/%m/%Y}"

    @property
    def en_cours(self):
        return self.statut == StatutInventaire.EN_COURS


class LigneInventaire(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    vehicule = models.ForeignKey('vehicules.Vehicule', on_delete=models.CASCADE, related_name='+')
    entree = models.ForeignKey('guerite.EnregistrementEntree', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='+')
    presence = models.CharField(max_length=10, choices=Presence.choices, default=Presence.A_VERIFIER)
    verifie_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    date_verification = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'inv_ligne'
        ordering = ['vehicule__immatriculation']
        constraints = [models.UniqueConstraint(fields=['inventaire', 'vehicule'], name='uniq_inv_ligne_vehicule')]


class MouvementTemporaire(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='mouvements')
    type = models.CharField(max_length=6, choices=TypeMouvement.choices)
    vehicule = models.ForeignKey('vehicules.Vehicule', on_delete=models.CASCADE, related_name='+')
    matricule = models.CharField(max_length=30)                         # tel que saisi / enregistré
    chauffeur = models.CharField(max_length=120, blank=True)
    chauffeur_tel = models.CharField(max_length=30, blank=True)
    conducteur = models.ForeignKey('vehicules.Conducteur', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    motif = models.CharField(max_length=30, blank=True)
    entree = models.ForeignKey('guerite.EnregistrementEntree', on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='+')                         # SORTIE : l'entrée en cours à clôturer
    cree_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='+')
    date_creation = models.DateTimeField(auto_now_add=True)
    erreur = models.TextField(blank=True, help_text="Dernière erreur lors de l'application par l'administrateur")

    class Meta:
        db_table = 'inv_mouvement_temp'
        ordering = ['type', 'matricule']
        constraints = [models.UniqueConstraint(fields=['inventaire', 'vehicule'], name='uniq_inv_mouvement_vehicule')]

    def __str__(self):
        return f"{self.get_type_display()} — {self.matricule}"
