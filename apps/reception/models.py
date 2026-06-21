"""
Réception — Statuts clairs selon les 3 flux :

FLUX 1 : Entrée → Réception → Rapport → Bon de sortie (sortie directe)
FLUX 2 : Entrée → Réception → Rapport → Transfert atelier → Fiche contrôle 
         → Présent atelier → Fiche technique → Réparation → Bon de sortie
FLUX 3 : Entrée → Réception → Rapport → Transfert atelier → Fiche contrôle 
         → Si fiche technique existe → Réparation directe
"""
import uuid
from django.db import models
from django.utils import timezone


class StatutVehicule(models.TextChoices):
    # Étape 1 : en réception
    EN_COURS            = 'EN_COURS',           'Réception — En cours'
    RAPPORT_FAIT        = 'RAPPORT_FAIT',        'Réception — Rapport établi'
    # Étape 2 : atelier
    EN_ATELIER          = 'EN_ATELIER',          'Atelier — En transit'
    PRESENT_ATELIER     = 'PRESENT_ATELIER',     'Atelier — Présent (fiche contrôle OK)'
    FICHE_TECHNIQUE     = 'FICHE_TECHNIQUE',     'Atelier — Fiche technique établie'
    REPARATION_EN_COURS = 'REPARATION_EN_COURS', 'Atelier — Réparation en cours'
    TRAVAUX_TERMINES    = 'TRAVAUX_TERMINES',    'Atelier — Travaux terminés'
    # Étape 3 : sortie
    BON_SORTIE_FAIT     = 'BON_SORTIE_FAIT',     'Bon de sortie établi'
    SORTI               = 'SORTI',               'Véhicule sorti'


# Statuts qui bloquent la fiche contrôle (doit être la 1ère action en atelier)
STATUTS_AVANT_FICHE = {'EN_ATELIER'}
# Statuts qui permettent la fiche technique
STATUTS_AVANT_FICHE_TECH = {'PRESENT_ATELIER'}
# Statuts qui permettent de créer un OR / tâches
STATUTS_REPARATION = {'PRESENT_ATELIER', 'FICHE_TECHNIQUE', 'REPARATION_EN_COURS'}
# Statuts qui permettent le bon de sortie
STATUTS_BON_SORTIE = {'RAPPORT_FAIT', 'TRAVAUX_TERMINES'}


class Reception(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero         = models.CharField(max_length=20, unique=True)
    entree         = models.OneToOneField(
        'guerite.EnregistrementEntree', on_delete=models.PROTECT, related_name='reception'
    )
    vehicule       = models.ForeignKey(
        'vehicules.Vehicule', on_delete=models.PROTECT, related_name='receptions'
    )
    statut         = models.CharField(
        max_length=25, choices=StatutVehicule.choices,
        default=StatutVehicule.EN_COURS
    )
    receptionniste = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, related_name='receptions_gerees'
    )
    observations   = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'receptions'
        verbose_name = 'Réception'
        ordering = ['-created_at']

    def __str__(self):
        return f"REC-{self.numero} — {self.vehicule.immatriculation}"

    def save(self, *args, **kwargs):
        if not self.numero:
            now = timezone.now()
            count = Reception.objects.count() + 1
            self.numero = f"REC-{now.strftime('%Y%m')}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def flux_label(self):
        """Détermine le flux en cours selon le statut"""
        if self.statut in ('EN_COURS', 'RAPPORT_FAIT'):
            return 'reception'
        if self.statut in ('EN_ATELIER', 'PRESENT_ATELIER', 'FICHE_TECHNIQUE',
                           'REPARATION_EN_COURS', 'TRAVAUX_TERMINES'):
            return 'atelier'
        return 'sortie'

    @property
    def etapes(self):
        """Retourne la liste des étapes avec leur état (done/active/pending)"""
        s = self.statut
        rapport = getattr(self, 'rapport', None)
        vers_atelier = rapport and rapport.decision == 'VERS_ATELIER' if rapport else True

        if not vers_atelier:
            # FLUX 1 - Sortie directe
            return [
                {'label': 'Entrée',         'icon': '🚗', 'state': 'done'},
                {'label': 'Réception',      'icon': '📥', 'state': 'done'},
                {'label': 'Rapport',        'icon': '📝', 'state': 'done' if s != 'EN_COURS' else 'active'},
                {'label': 'Bon de sortie',  'icon': '📄', 'state': 'done' if s in ('BON_SORTIE_FAIT','SORTI') else ('active' if s == 'RAPPORT_FAIT' else 'pending')},
                {'label': 'Sorti',          'icon': '✅', 'state': 'done' if s == 'SORTI' else 'pending'},
            ]
        else:
            # FLUX 2/3 - Avec atelier
            return [
                {'label': 'Entrée',         'icon': '🚗', 'state': 'done'},
                {'label': 'Réception',      'icon': '📥', 'state': 'done'},
                {'label': 'Rapport',        'icon': '📝', 'state': 'done' if s not in ('EN_COURS',) else 'active'},
                {'label': 'Transfert',      'icon': '🏭', 'state': 'done' if s not in ('EN_COURS','RAPPORT_FAIT') else ('active' if s == 'RAPPORT_FAIT' else 'pending')},
                {'label': 'Fiche contrôle', 'icon': '📋', 'state': 'done' if s not in ('EN_COURS','RAPPORT_FAIT','EN_ATELIER') else ('active' if s == 'EN_ATELIER' else 'pending')},
                {'label': 'Fiche technique','icon': '🔬', 'state': 'done' if s in ('FICHE_TECHNIQUE','REPARATION_EN_COURS','TRAVAUX_TERMINES','BON_SORTIE_FAIT','SORTI') else ('active' if s == 'PRESENT_ATELIER' else 'pending')},
                {'label': 'Réparation',     'icon': '🔧', 'state': 'done' if s in ('TRAVAUX_TERMINES','BON_SORTIE_FAIT','SORTI') else ('active' if s in ('REPARATION_EN_COURS','FICHE_TECHNIQUE') else 'pending')},
                {'label': 'Bon de sortie',  'icon': '📄', 'state': 'done' if s in ('BON_SORTIE_FAIT','SORTI') else ('active' if s == 'TRAVAUX_TERMINES' else 'pending')},
                {'label': 'Sorti',          'icon': '✅', 'state': 'done' if s == 'SORTI' else 'pending'},
            ]

    @property
    def progression_pct(self):
        pct = {
            'EN_COURS': 5, 'RAPPORT_FAIT': 18, 'EN_ATELIER': 30,
            'PRESENT_ATELIER': 45, 'FICHE_TECHNIQUE': 58,
            'REPARATION_EN_COURS': 70, 'TRAVAUX_TERMINES': 83,
            'BON_SORTIE_FAIT': 92, 'SORTI': 100,
        }
        return pct.get(self.statut, 0)

    @property
    def prochaine_action(self):
        """Message indiquant ce qu'il faut faire maintenant"""
        s = self.statut
        rapport = getattr(self, 'rapport', None)
        actions = {
            'EN_COURS':            ('📝', 'Créer le rapport de réception', 'primary'),
            'RAPPORT_FAIT':        ('🏭', 'Transférer vers atelier(s) ou créer bon de sortie', 'accent'),
            'EN_ATELIER':          ('📋', 'En attente de la fiche de contrôle à l\'atelier', 'info'),
            'PRESENT_ATELIER':     ('🔬', 'En attente de la fiche technique à l\'atelier', 'info'),
            'FICHE_TECHNIQUE':     ('🔧', 'Réparation en cours à l\'atelier', 'warning'),
            'REPARATION_EN_COURS': ('🔧', 'Travaux en cours à l\'atelier', 'warning'),
            'TRAVAUX_TERMINES':    ('📄', 'Créer le bon de sortie', 'success'),
            'BON_SORTIE_FAIT':     ('🚗', 'Bon de sortie prêt — guérite peut libérer le véhicule', 'success'),
            'SORTI':               ('✅', 'Véhicule sorti du garage', 'secondary'),
        }
        return actions.get(s, ('?', '—', 'secondary'))


class RapportReception(models.Model):
    id                = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reception         = models.OneToOneField(Reception, on_delete=models.CASCADE, related_name='rapport')
    constat           = models.TextField(verbose_name="Constat visuel à l'arrivée")
    probleme_declare  = models.TextField(verbose_name="Problème déclaré par le client")
    kilometrage       = models.IntegerField(default=0)
    niveau_carburant  = models.IntegerField(default=0, help_text="0-100%")
    decision          = models.CharField(max_length=20, choices=[
        ('SORTIE_DIRECTE', 'Sortie directe — sans réparation'),
        ('VERS_ATELIER',   'Transfert vers atelier(s)'),
    ], default='VERS_ATELIER')
    observations      = models.TextField(blank=True)
    cree_par          = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='rapports_crees'
    )
    created_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'rapports_reception'

    def __str__(self):
        return f"Rapport — {self.reception.numero}"


class TransfertAtelier(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reception      = models.ForeignKey(Reception, on_delete=models.CASCADE, related_name='transferts')
    atelier        = models.ForeignKey(
        'atelier.Atelier', on_delete=models.PROTECT, related_name='transferts_recus'
    )
    motif          = models.TextField(verbose_name="Travaux demandés")
    date_transfert = models.DateTimeField(default=timezone.now)
    effectue_par   = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, related_name='transferts_effectues'
    )

    class Meta:
        db_table = 'transferts_atelier'
        ordering = ['-date_transfert']

    def __str__(self):
        return f"{self.reception.numero} → {self.atelier.nom}"


class Notification(models.Model):
    TYPE = [
        ('NOUVEAU_VEHICULE',   '🚗 Nouveau véhicule'),
        ('FICHE_CONTROLE_OK',  '📋 Fiche contrôle complétée'),
        ('FICHE_TECHNIQUE_OK', '🔬 Fiche technique établie'),
        ('TRAVAUX_TERMINES',   '✅ Travaux terminés'),
        ('OR_CLOTURE',         '🔒 OR clôturé'),
        ('OR_REOUVERT',        '🔓 OR réouvert'),
    ]
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_notif   = models.CharField(max_length=25, choices=TYPE)
    titre        = models.CharField(max_length=200)
    message      = models.TextField()
    reception    = models.ForeignKey(
        Reception, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True
    )
    destinataire = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='notifications_recues'
    )
    lue          = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications_reception'
        ordering = ['-created_at']
