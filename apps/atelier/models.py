

import uuid
from django.db import models
from django.utils import timezone

from apps.accounts.choices import PrioriteTache, StatutOR, StatutTache, TypeRetour, UrgenceOR






def _format_minutes(minutes):
    """Formate une durée en minutes : '3h45', '3h' ou '45 min'."""
    if not minutes:
        return '—'
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return '—'
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    return f"{m} min"

# ══════════════════════════════════════════════════════════════════
#  ATELIER
# ══════════════════════════════════════════════════════════════════
class Atelier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, verbose_name="Code")
    localisation = models.CharField(max_length=150, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    specialite = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    responsable = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='ateliers_diriges')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='ateliers_crees')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ateliers'
        verbose_name = "Atelier"
        ordering = ['nom']

    def __str__(self):
        return self.nom


# ══════════════════════════════════════════════════════════════════
#  ORDRE DE RÉPARATION (un seul, partagé entre plusieurs ateliers)
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
#  ORDRE DE RÉPARATION
# ══════════════════════════════════════════════════════════════════

class OrdreReparation(models.Model):
    id      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero  = models.CharField(max_length=25, unique=True, blank=True)

    reception = models.OneToOneField(
        'reception.Reception',
        on_delete=models.PROTECT,
        related_name='ordre_reparation',
    )
    vehicule = models.ForeignKey(
        'vehicules.Vehicule',
        on_delete=models.PROTECT,
        related_name='ordres_reparation',
    )
    ateliers = models.ManyToManyField(
        Atelier,
        related_name='ordres_reparation',
    )

    statut              = models.CharField(max_length=15, choices=StatutOR.choices, default=StatutOR.OUVERT)
    urgence             = models.CharField(max_length=10, choices=UrgenceOR.choices, default=UrgenceOR.NORMAL)
    description_travaux = models.TextField(blank=True)

    # Durées & dates
    date_fin_prevue     = models.DateField(null=True, blank=True, verbose_name="Fin prévue")
    duree_fin_prevu     = models.IntegerField(null=True, blank=True, verbose_name="Durée prévue (minutes)")
    duree_fin_reel      = models.IntegerField(null=True, blank=True, verbose_name="Durée réelle (minutes)")

    date_creation       = models.DateTimeField(auto_now_add=True)
    date_cloture        = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='ordres_reparation_crees',
    )

    class Meta:
        db_table = 'ordres_reparation'
        verbose_name = "Ordre de réparation"
        ordering = ['-date_creation']

    def save(self, *args, **kwargs):
        if not self.numero:
            now = timezone.now()
            self.numero = f"OR-{now.strftime('%Y%m')}-{OrdreReparation.objects.count() + 1:04d}"
        super().save(*args, **kwargs)
 
    def __str__(self):
        return f"{self.numero} — {self.vehicule.immatriculation}"
 
    # ── Verrou ───────────────────────────────────────────────────
 
    @property
    def est_cloture(self):
        """OR clôturé : plus aucune création / modification de tâche.
        Seule la réouverture (côté réception) le débloque."""
        return self.statut == StatutOR.CLOTURE
 
    # ── Réception ────────────────────────────────────────────────
 
    @property
    def reception_actuelle(self):
        """Réception de la dernière réouverture, sinon la réception d'origine."""
        derniere = self.reouvertures.exclude(reception__isnull=True).select_related('reception').first()
        return derniere.reception if derniere else self.reception
 
    # ── Durées ───────────────────────────────────────────────────
    # Durée prévue = somme des durées estimées des tâches
    #              + somme des durées prévues des réouvertures.
    # Durée réelle = somme des comptes rendus de toutes les tâches.
    # Les deux sont STOCKÉES (duree_fin_prevu / duree_fin_reel) et recalculées
    # à chaque changement : les labels ne refont plus de requête SUM.
 
    @property
    def duree_reelle_totale(self):
        from django.db.models import Sum
        total = (
            CompteRendu.objects
            .filter(tache__ordre_reparation=self)
            .aggregate(total=Sum('duree_minutes'))['total']
        )
        return total or 0
 
    @property
    def duree_reelle(self):
        """Valeur stockée ; calculée seulement si jamais enregistrée."""
        if self.duree_fin_reel is None:
            return self.duree_reelle_totale
        return self.duree_fin_reel
 
    @property
    def duree_prevue_label(self):
        return _format_minutes(self.duree_fin_prevu)
 
    @property
    def duree_reelle_label(self):
        return _format_minutes(self.duree_reelle)
 
    @property
    def ecart_duree_minutes(self):
        """Différence durée réelle - durée prévue."""
        if not self.duree_fin_prevu:
            return None
        return (self.duree_reelle or 0) - self.duree_fin_prevu
 
    @property
    def ecart_duree_label(self):
        ecart = self.ecart_duree_minutes
        if ecart is None:
            return '—'
        signe = '+' if ecart > 0 else ''
        return f"{signe}{_format_minutes(abs(ecart))}"
 
    @property
    def en_retard_duree(self):
        if not self.duree_fin_prevu:
            return False
        return (self.duree_reelle or 0) > self.duree_fin_prevu
 
    @property
    def duree_immobilisation_label(self):
        """Temps passé au garage : création → clôture (ou maintenant)."""
        fin = self.date_cloture or timezone.now()
        return _format_minutes(int((fin - self.date_creation).total_seconds() // 60))
 
    def recalculer_duree_prevue(self, save=True):
        """duree_fin_prevu = Σ durées estimées des tâches + Σ durées des réouvertures."""
        from django.db.models import Sum
        taches = self.taches.aggregate(t=Sum('duree_estimee_minutes'))['t'] or 0
        reouv = self.reouvertures.aggregate(r=Sum('duree_prevue_minutes'))['r'] or 0
        total = taches + reouv
        if self.duree_fin_prevu != total:
            self.duree_fin_prevu = total
            if save:
                self.save(update_fields=['duree_fin_prevu'])
        return total
 
    def recalculer_duree_reelle(self, save=True):
        """Recalcule duree_fin_reel à partir des comptes rendus."""
        total = self.duree_reelle_totale
        if self.duree_fin_reel != total:
            self.duree_fin_reel = total
            if save:
                self.save(update_fields=['duree_fin_reel'])
        return total
 
    def recalculer_toutes_durees(self, save=True):
        """Recalcule en cascade : chaque tâche, puis l'OR (prévue + réelle)."""
        from django.db import transaction
        with transaction.atomic():
            for t in self.taches.all():
                t.recalculer_duree_reelle(save=True)
            self.recalculer_duree_prevue(save=save)
            return self.recalculer_duree_reelle(save=save)
 
    # ── Dates ────────────────────────────────────────────────────
 
    def recalculer_date_fin_reelle(self):
        """Date de clôture, sinon dernière validation, sinon dernière date de fin."""
        from django.db.models import Max
        if self.date_cloture:
            return self.date_cloture
 
        derniere = (
            self.taches
            .exclude(date_validation__isnull=True)
            .aggregate(d=Max('date_validation'))['d']
        )
        if derniere:
            return derniere
 
        return (
            self.taches
            .exclude(date_fin__isnull=True)
            .aggregate(d=Max('date_fin'))['d']
        )
 
    @property
    def date_fin_reelle(self):
        return self.recalculer_date_fin_reelle()
 
    @property
    def en_retard(self):
        return bool(
            self.date_fin_prevue
            and self.statut != StatutOR.CLOTURE
            and timezone.localdate() > self.date_fin_prevue
        )
 
    # ── Stats ────────────────────────────────────────────────────
 
    @property
    def est_termine(self):
        return self.stats_globales()['cloturable']
 
    def stats_globales(self):
        """Toutes tâches de TOUS les ateliers — pour savoir si l'OR est clôturable."""
        taches = list(self.taches.all())
        total = len(taches)
        validees = sum(1 for t in taches if t.statut == StatutTache.VALIDEE)
        return {
            'total':      total,
            'validees':   validees,
            'pct_valide': int(validees / total * 100) if total else 0,
            'cloturable': total > 0 and validees == total,
        }
 
    def stats_pour_atelier(self, atelier):
        taches = list(self.taches.filter(atelier=atelier))
        total = len(taches)
        c = lambda s: sum(1 for t in taches if t.statut == s)
        validees = c(StatutTache.VALIDEE)
        return {
            'total':      total,
            'validees':   validees,
            'terminees':  c(StatutTache.TERMINEE),
            'en_cours':   c(StatutTache.EN_COURS),
            'a_faire':    c(StatutTache.A_FAIRE),
            'a_reprendre': sum(1 for t in taches if t.est_a_reprendre),
            'pct_valide': int(validees / total * 100) if total else 0,
        }
 
# ══════════════════════════════════════════════════════════════════
#  TÂCHE
# ══════════════════════════════════════════════════════════════════


class Tache(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ordre_reparation = models.ForeignKey(
        OrdreReparation, on_delete=models.CASCADE, related_name='taches',
    )
    atelier = models.ForeignKey(
        Atelier, on_delete=models.PROTECT, related_name='taches',
    )

    libelle     = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priorite    = models.CharField(max_length=10, choices=PrioriteTache.choices, default=PrioriteTache.NORMALE)
    statut      = models.CharField(max_length=10, choices=StatutTache.choices, default=StatutTache.A_FAIRE)

    techniciens = models.ManyToManyField(
        'accounts.User',
        related_name='taches_assignees',
        blank=True,
    )

    # Durées
    duree_estimee_minutes = models.IntegerField(null=True, blank=True, verbose_name="Durée prévue (min)")
    duree_reelle_minutes  = models.IntegerField(null=True, blank=True, verbose_name="Durée réelle (min)")

    # Dates
    date_assignation = models.DateTimeField(null=True, blank=True)
    date_debut       = models.DateTimeField(null=True, blank=True)
    date_fin         = models.DateTimeField(null=True, blank=True)
    date_validation  = models.DateTimeField(null=True, blank=True)

    # Validation
    valide_par               = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='taches_validees',
    )
    commentaire_validation   = models.TextField(blank=True)
    signature_chef           = models.TextField(blank=True, help_text="base64")
    cloturee_manuellement    = models.BooleanField(default=False)

    # Meta
    created_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='taches_creees',
    )

       # Retour au technicien (refus du responsable ou réouverture de l'OR)
    type_retour     = models.CharField(max_length=12, choices=TypeRetour.choices, default=TypeRetour.AUCUN, blank=True)
    motif_retour    = models.TextField(blank=True)
    date_retour     = models.DateTimeField(null=True, blank=True)
    nb_refus        = models.PositiveIntegerField(default=0)
    nb_reouvertures = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'taches_atelier'
        verbose_name = "Tâche"
        ordering = ['created_at']


    def __str__(self):
        return f"{self.libelle} ({self.atelier.nom})"
 
    # ── Retours ──────────────────────────────────────────────────
 
    @property
    def est_a_reprendre(self):
        """Tâche revenue au technicien (refus ou réouverture) et pas encore refaite."""
        return bool(self.type_retour) and self.statut in (StatutTache.A_FAIRE, StatutTache.EN_COURS)
 
    @property
    def est_refusee(self):
        return self.type_retour == TypeRetour.REFUS
 
    @property
    def est_reouverte(self):
        return self.type_retour == TypeRetour.REOUVERTURE
 
    @property
    def est_modifiable(self):
        """Le responsable peut modifier une tâche non démarrée d'un OR non clôturé."""
        return self.statut == StatutTache.A_FAIRE and not self.ordre_reparation.est_cloture
 
    @property
    def est_supprimable(self):
        """Non démarrée ET sans historique (pas de compte rendu, jamais réouverte)."""
        return (
            self.est_modifiable
            and self.nb_reouvertures == 0
            and not self.comptes_rendus.exists()
        )
 
    # ── Durées ───────────────────────────────────────────────────
 
    @property
    def duree_estimee_label(self):
        return _format_minutes(self.duree_estimee_minutes)
 
    @property
    def duree_technicien_minutes(self):
        """Somme des durées des comptes rendus."""
        from django.db.models import Sum
        total = self.comptes_rendus.aggregate(total=Sum('duree_minutes'))['total']
        return total or 0
 
    @property
    def duree_technicien_label(self):
        return _format_minutes(self.duree_technicien_minutes)
 
    @property
    def duree_reelle_label(self):
        return _format_minutes(self.duree_reelle_minutes)
 
    @property
    def ecart_minutes(self):
        if self.duree_estimee_minutes is None:
            return None
        return (self.duree_reelle_minutes or 0) - self.duree_estimee_minutes
 
    @property
    def ecart_label(self):
        ecart = self.ecart_minutes
        if ecart is None:
            return '—'
        signe = '+' if ecart > 0 else ''
        return f"{signe}{_format_minutes(abs(ecart))}"
 
    def recalculer_duree_reelle(self, save=True):
        """Met à jour duree_reelle_minutes = somme des comptes rendus."""
        total = self.duree_technicien_minutes
        if self.duree_reelle_minutes != total:
            self.duree_reelle_minutes = total
            if save:
                self.save(update_fields=['duree_reelle_minutes'])
        return total
 
    # ── Retard & délais ──────────────────────────────────────────
 
    @property
    def delai_avant_demarrage_minutes(self):
        if self.date_assignation and self.date_debut:
            return int((self.date_debut - self.date_assignation).total_seconds() / 60)
        return None
 
    @property
    def en_retard(self):
        if self.duree_reelle_minutes is not None and self.duree_estimee_minutes:
            return self.duree_reelle_minutes > self.duree_estimee_minutes
 
        if self.statut == StatutTache.EN_COURS and self.date_debut and self.duree_estimee_minutes:
            elapsed = (timezone.now() - self.date_debut).total_seconds() / 60
            return elapsed > self.duree_estimee_minutes
 
        return False
 

# ══════════════════════════════════════════════════════════════════
#  COMPTE RENDU
# ══════════════════════════════════════════════════════════════════

class CompteRendu(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tache = models.ForeignKey(
        Tache, on_delete=models.CASCADE, related_name='comptes_rendus',
    )
    technicien = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True,
        related_name='comptes_rendus',
    )

    description      = models.TextField()
    pieces_utilisees = models.TextField(blank=True)
    observations     = models.TextField(blank=True)
    duree_minutes    = models.IntegerField(default=0)

    saisie_par_chef = models.BooleanField(default=False)
    date_saisie     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'comptes_rendus_taches'
        ordering = ['-date_saisie']

    def __str__(self):
        return f"CR {self.tache.libelle} — {self.duree_minutes} min"

    @property
    def duree_label(self):
        return _format_minutes(self.duree_minutes)
    
    @property
    def get_full_name(self):
        return f"{self.technicien.nom} {self.technicien.prenom}".strip()





PRIORITE_RANK = {'URGENTE': 3, 'HAUTE': 2, 'NORMALE': 1, 'BASSE': 0}




class ReouvertureOR(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ordre_reparation = models.ForeignKey(OrdreReparation, on_delete=models.CASCADE, related_name='reouvertures')
 
    # Avant : tache = ForeignKey(Tache, ...)  → une seule tâche
    # Maintenant : plusieurs tâches à refaire
    taches = models.ManyToManyField(Tache, blank=True, related_name='reouvertures')

    reception = models.ForeignKey(
        'reception.Reception', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reouvertures_or',
    )
 
    # Durée générale attribuée à la réouverture (en minutes)
    duree_prevue_minutes = models.PositiveIntegerField(default=0)
 
    raison = models.TextField()
    reouvert_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                     related_name='reouvertures_effectuees')
    date_reouverture = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        db_table = 'reouvertures_or'
        ordering = ['-date_reouverture']
 
    @property
    def duree_prevue_label(self):
        m = self.duree_prevue_minutes or 0
        if not m:
            return '—'
        h, mn = divmod(m, 60)
        if h and mn:
            return f"{h}h{mn:02d}"
        return f"{h}h" if h else f"{mn} min"







# ══════════════════════════════════════════════════════════════════
#  apps/atelier/models.py — FICHES (à la place de FicheTechnique et FicheControle)
#
#  - FicheTechnique : ton modèle, inchangé.
#  - FicheControle  : mêmes colonnes qu'avant. Les éléments contrôlés sont
#    rangés dans une classe abstraite (ElementsControle) pour être partagés
#    avec la table temporaire. Ajouts : sièges (catégorie « Habitacle ») et
#    archive du contrôle de sortie.
#  - FicheControleTemporaire : table fiches_controle_temporaires, contrôle de
#    sortie en cours. La ligne est supprimée après la signature du client.
#
#  bd(), on(), mm(), JAUGE et NIVEAU_HUILE restent ceux de ton models.py.
# ══════════════════════════════════════════════════════════════════






BON_DEFAUT = [('BON', 'Bon'), ('DEFAUT', 'Défaut')]
OUI_NON = [('OUI', 'Oui'), ('NON', 'Non')]
NIVEAU_HUILE = [('MINI', 'Mini'), ('CORRECT', 'Correct'), ('MAXI', 'Maxi')]
JAUGE = [('E', 'Vide (E)'), ('QUART', '1/4'), ('DEMI', '1/2'), ('TROIS_QUARTS', '3/4'), ('F', 'Plein (F)')]


def bd():   # champ Bon / Défaut
    return models.CharField(max_length=10, choices=BON_DEFAUT, blank=True)


def on():   # champ Oui / Non
    return models.CharField(max_length=3, choices=OUI_NON, blank=True)


def mm():   # mesure en mm
    return models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True, help_text="mm")


# ══════════════════════════════════════════════════════════════════
#  FICHE TECHNIQUE  — TON MODÈLE, INCHANGÉ
# ══════════════════════════════════════════════════════════════════
class FicheTechnique(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_fiche = models.CharField(max_length=20, blank=True, verbose_name="N° fiche")
    entree = models.OneToOneField(
        'guerite.EnregistrementEntree',
        on_delete=models.PROTECT,
        related_name='fiche_technique',
        db_column='entree_id',          # ← colonne réelle en base
    )

    # --- En-tête ---
    entree_le = models.DateField(null=True, blank=True)
    sortie_le = models.DateField(null=True, blank=True)
    nom_client = models.CharField(max_length=100, blank=True)
    immatriculation = models.CharField(max_length=20, blank=True)
    vehicule = models.CharField(max_length=100, blank=True, verbose_name="Véhicule")
    kilometrage = models.IntegerField(default=0)
    preconisation_courroie_distribution = models.DateField(null=True, blank=True)
    rendre_pieces = on()
    ecrou_antivol = on()
    alarme = on()

    # === VEHICULE AU SOL ===
    eclairage_av_veilleuses = bd()
    eclairage_av_croisement = bd()
    eclairage_av_route = bd()
    eclairage_av_antibrouillard = bd()
    eclairage_av_clignotants = bd()

    eclairage_ar_feux_position = bd()
    eclairage_ar_stop = bd()
    eclairage_ar_clignotants = bd()
    eclairage_ar_recul = bd()
    eclairage_ar_antibrouillard = bd()
    eclairage_ar_feu_plaque = bd()
    eclairage_ar_3eme_feu_stop = bd()

    controle_hauteur_phare = bd()

    voyant_tableau_bord = bd()
    code_defaut = bd()
    sieges = bd()

    bougies_faisceau = bd()
    sonde_lamda = bd()

    course_pedale_frein = bd()
    course_frein_main = bd()
    liquide_frein_temperature = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="°C")
    liquide_frein_etat = bd()
    maitre_cylindre_fuite = bd()

    climatisation_temperature_soufflage = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="°C")
    climatisation_filtre_habitacle = bd()

    niveau_huile_prise_en_charge = models.CharField(max_length=10, choices=NIVEAU_HUILE, blank=True)

    balais_essuie_glace_av = bd()
    balais_essuie_glace_ar = bd()
    pare_brise_impact = on()
    pare_brise_fissure = on()
    pare_brise_fissure_appeler_le = models.CharField(max_length=20, blank=True)

    jauge_carburant = models.CharField(max_length=15, choices=JAUGE, blank=True)

    plaques_immatriculation_av = bd()
    plaques_immatriculation_ar = bd()

    batterie = bd()
    alternateur_demarreur = bd()
    liquide_refroidissement = bd()

    # --- Habitacle : sièges ---
    siege_conducteur_etat = bd()
    siege_passager_etat = bd()
    sieges_arriere_etat = bd()
    ceintures_securite_etat = bd()

    # === VEHICULE MI HAUTEUR ===
    pneu_av_g_profondeur = mm()
    pneu_av_d_profondeur = mm()
    pneu_ar_g_profondeur = mm()
    pneu_ar_d_profondeur = mm()
    pneu_roue_secours_profondeur = mm()

    pneu_av_g_usure = bd()
    pneu_av_d_usure = bd()
    pneu_ar_g_usure = bd()
    pneu_ar_d_usure = bd()
    ecrou_goujons_av_g = bd()
    ecrou_goujons_av_d = bd()
    ecrou_goujons_ar_g = bd()
    ecrou_goujons_ar_d = bd()

    geometrie_necessaire = on()

    susp_amortisseurs_av_g = bd()
    susp_amortisseurs_av_d = bd()
    susp_amortisseurs_ar_g = bd()
    susp_amortisseurs_ar_d = bd()
    susp_coupelles_av_g = bd()
    susp_coupelles_av_d = bd()
    susp_coupelles_ar_g = bd()
    susp_coupelles_ar_d = bd()
    susp_ressorts_av_g = bd()
    susp_ressorts_av_d = bd()
    susp_ressorts_ar_g = bd()
    susp_ressorts_ar_d = bd()
    susp_kit_protection_av_g = bd()
    susp_kit_protection_av_d = bd()
    susp_kit_protection_ar_g = bd()
    susp_kit_protection_ar_d = bd()
    susp_butees_av_g = bd()
    susp_butees_av_d = bd()
    susp_butees_ar_g = bd()
    susp_butees_ar_d = bd()
    susp_biellettes_av_g = bd()
    susp_biellettes_av_d = bd()
    susp_biellettes_ar_g = bd()
    susp_biellettes_ar_d = bd()

    roulements_av_g = bd()
    roulements_av_d = bd()
    roulements_ar_g = bd()
    roulements_ar_d = bd()

    rotules_av_g = bd()
    rotules_av_d = bd()
    rotules_ar_g = bd()
    rotules_ar_d = bd()

    bras_de_suspension_av_g = bd()
    bras_de_suspension_av_d = bd()
    bras_de_suspension_ar_g = bd()
    bras_de_suspension_ar_d = bd()

    silent_bloc_s_av_g = bd()
    silent_bloc_s_av_d = bd()
    silent_bloc_s_ar_g = bd()
    silent_bloc_s_ar_d = bd()

    frein_flexibles_av_g = bd()
    frein_flexibles_av_d = bd()
    frein_flexibles_ar_g = bd()
    frein_flexibles_ar_d = bd()
    frein_disques_av_g = bd()
    frein_disques_av_d = bd()
    frein_disques_ar_g = bd()
    frein_disques_ar_d = bd()
    frein_disques_epaisseur_mm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    frein_plaquettes_av_g = bd()
    frein_plaquettes_av_d = bd()
    frein_plaquettes_ar_g = bd()
    frein_plaquettes_ar_d = bd()
    frein_kit_frein_ar_g = bd()
    frein_kit_frein_ar_d = bd()
    frein_tambours_ar_g = bd()
    frein_tambours_ar_d = bd()
    frein_tambours_diametre_mm = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    train_flexibles_av_g = bd()
    train_flexibles_av_d = bd()
    train_flexibles_ar_g = bd()
    train_flexibles_ar_d = bd()
    train_disques_av_g = bd()
    train_disques_av_d = bd()
    train_disques_ar_g = bd()
    train_disques_ar_d = bd()
    train_plaquettes_av_g = bd()
    train_plaquettes_av_d = bd()
    train_plaquettes_ar_g = bd()
    train_plaquettes_ar_d = bd()
    train_kit_frein_av_g = bd()
    train_kit_frein_av_d = bd()
    train_tambours_av_g = bd()
    train_tambours_av_d = bd()
    train_tambours_ar_g = bd()
    train_tambours_ar_d = bd()

    # === VEHICULE LEVE ===
    echap_catalyseur_filtre_particules = models.CharField(max_length=10, blank=True, help_text="'/' si non applicable")
    echap_partie_avant = bd()
    echap_partie_intermediaire = bd()
    echap_partie_arriere = bd()
    echap_fixations = bd()

    transmission_soufflets_g = bd()
    transmission_soufflets_d = bd()
    transmission_cardans_g = bd()
    transmission_cardans_d = bd()

    frein_canalisation = bd()
    frein_cable_frein_main = bd()
    frein_repartiteur_fuite = bd()

    fuite_moteur = on()

    # === POST-CONTRÔLES ET MISES A NIVEAU ===
    niveau_huile_apres_intervention = models.CharField(max_length=10, choices=NIVEAU_HUILE, blank=True)
    ok_lave_glace = models.BooleanField(default=False, verbose_name="Lave-glace *Ok")
    ok_liquide_refroidissement = models.BooleanField(default=False, verbose_name="Liquide de refroidissement *Ok")
    ok_kit_securite = models.BooleanField(default=False, verbose_name="Kit sécurité (cales, extincteur, triangles) *Ok")
    ok_boite_ampoules = models.BooleanField(default=False, verbose_name="Boîte d'ampoules (boîte à pharmacie) *Ok")
    ok_etiquette_vidange = models.BooleanField(default=False, verbose_name="Mise en place étiquette vidange *Ok")
    ok_etiquette_monte_pneumatique = models.BooleanField(default=False, verbose_name="Mise en place étiquette monte pneumatique *Ok")
    ok_remise_a_zero_maintenance = models.BooleanField(default=False, verbose_name="Remise à zéro indicateur de maintenance *Ok")
    ok_pression_des_pneus = models.BooleanField(default=False, verbose_name="Pression des pneus *Ok")

    # === Diagnostic, chiffrage & synthèse ===
    diagnostic = models.TextField(verbose_name="Diagnostic technique")

    # --- Signatures ---
    nom_controleur = models.CharField(max_length=100, blank=True)
    signature_controleur = models.TextField(blank=True, help_text="base64")
    nom_client_signataire = models.CharField(max_length=100, blank=True)
    signature_client = models.TextField(blank=True, help_text="base64")

    cree_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                 related_name='fiches_techniques')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fiches_techniques'
        verbose_name = "Fiche technique"
        verbose_name_plural = "Fiches techniques"

    @property
    def terminee(self):
        """Terminée = page 3 validée avec la signature du technicien."""
        return bool(self.signature_controleur)

    # ⚠️ total_estime retiré : il lisait main_oeuvre_estimee et pieces_estimees,
    # qui n'existent plus dans le modèle (AttributeError à l'affichage).

    def __str__(self):
        return f"Fiche diagnostic {self.numero_fiche or self.id} - {self.immatriculation}"


# ══════════════════════════════════════════════════════════════════
#  ÉLÉMENTS CONTRÔLÉS — partagés par la fiche (entrée) et la table temporaire (sortie)
#  Classe abstraite : aucune table, les colonnes restent dans fiches_controle.
# ══════════════════════════════════════════════════════════════════
class ElementsControle(models.Model):
    STATUT_CHOICES = [('BON', 'Bon'), ('DEFAUT', 'Défaut')]
    ETAT_VITRE_CHOICES = [('INTACT', 'Intact'), ('FISSURE', 'Fissuré'), ('CASSE', 'Cassé')]
    TYPE_VEHICULE_CHOICES = [
        ('VOITURE', 'Voiture'), ('PICKUP', 'Pick-up'),
        ('CAMION_CITERNE', 'Camion-citerne'), ('BENNE', 'Camion benne'),
        ('FOURGON', 'Fourgon / Van'),
    ]
    JAUGE_CHOICES = JAUGE
    ETAT_GENERAL_CHOICES = [('BON', 'Bon'), ('MOYEN', 'Moyen'), ('MAUVAIS', 'Mauvais')]

    # --- Colonne 1 ---
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
    roue_secours_gonflee_et_remis_en_place = models.BooleanField(null=True, blank=True)

    cric_present = models.BooleanField(default=False)
    manivelle_presente = models.BooleanField(default=False)
    cle_roue_presente = models.BooleanField(default=False)

    joints_portieres_propres = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    enjoliveurs_et_ecrous_roues_presents = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    plaques_immatriculation_avant_arriere = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    tares_avant_arriere_presentes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    garde_boues_presents_bien_montes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)
    agrafes_presentes = models.CharField(max_length=10, choices=STATUT_CHOICES, blank=True)

    # --- Colonne 2 ---
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

    # --- Colonne 3 ---
    tapis_sol_5_presents = models.BooleanField(null=True, blank=True)
    vitres_avant_se_baissent = models.BooleanField(null=True, blank=True)
    vitres_arriere_se_baissent = models.BooleanField(null=True, blank=True)
    telecommande_vitres_fonctionne = models.BooleanField(null=True, blank=True)
    autocollants_pare_brise_presents = models.BooleanField(null=True, blank=True, help_text="Si pare-brise à remplacer")
    voiles_peinture_sur_vitres = models.BooleanField(null=True, blank=True)

    jauge_carburant = models.CharField(max_length=15, choices=JAUGE_CHOICES, blank=True)

    cosses_batterie_serrées = models.BooleanField(null=True, blank=True)
    reglage_des_miroirs_retroviseurs_fonctionnel = models.BooleanField(null=True, blank=True)
    console_fermeture_ouverture_portiere_fonctionnel = models.BooleanField(null=True, blank=True)
    sous_capot_moteur_est_propre = models.BooleanField(null=True, blank=True)
    isolant_thermique_capot_present = models.BooleanField(null=True, blank=True)
    niveau_liquide_lave_glace_bon = models.BooleanField(null=True, blank=True)
    niveau_liquide_huile_bon = models.BooleanField(null=True, blank=True)
    niveau_liquide_refroisseur_bon = models.BooleanField(null=True, blank=True)
    niveau_liquide_frein_bon = models.BooleanField(null=True, blank=True)

    qualite_rendu_peinture_rayures = models.BooleanField(null=True, blank=True)
    qualite_rendu_peinture_decollement = models.BooleanField(null=True, blank=True)
    qualite_rendu_peinture_couleur = models.BooleanField(null=True, blank=True)
    qualite_rendu_peinture_eclat_brillance = models.BooleanField(null=True, blank=True)
    qualite_rendu_peinture_frissure = models.BooleanField(null=True, blank=True)

    # --- Schéma carrosserie ---
    type_vehicule = models.CharField(max_length=20, choices=TYPE_VEHICULE_CHOICES, blank=True)
    points_degats_carrosserie = models.JSONField(
        default=list, blank=True,
        help_text="Liste de points sur le schéma: [{'x':.., 'y':.., 'type':'PIQURE|RAYURE|BOSSE|CASSE'}, ...]")

    # --- Synthèse ---
    etat_general = models.CharField(max_length=20, choices=ETAT_GENERAL_CHOICES, default='BON')
    commentaires = models.TextField(blank=True)

    class Meta:
        abstract = True


# ══════════════════════════════════════════════════════════════════
#  FICHE DE CONTRÔLE — définitive (état d'entrée + archive de la sortie)
# ══════════════════════════════════════════════════════════════════
class FicheControle(ElementsControle):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entree = models.OneToOneField(
        'guerite.EnregistrementEntree',
        on_delete=models.PROTECT,
        related_name='fiche_controle',
        db_column='entree_id',
    )

    # --- En-tête ---
    travail_a_effectuer = models.TextField(blank=True, verbose_name="Travail à effectuer")
    entree_le = models.DateField(null=True, blank=True, verbose_name="Entrée le")
    sortir_le = models.DateField(null=True, blank=True, verbose_name="Sortie le")
    immatriculation = models.CharField(max_length=20, blank=True)
    marque = models.CharField(max_length=50, blank=True)
    modele = models.CharField(max_length=50, blank=True)
    kilometrage = models.IntegerField(default=0, verbose_name="Kilométrage")
    telephone = models.CharField(max_length=20, blank=True)

    # --- Signatures (5 blocs) ---
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

    inspecte_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                     related_name='fiches_controle')
    date_inspection = models.DateTimeField(auto_now_add=True)

    # ➕ NOUVEAU — archive du contrôle de sortie (remplie à la signature du client)
    kilometrage_sortie = models.IntegerField(null=True, blank=True, verbose_name="Kilométrage à la sortie")
    etat_sortie = models.JSONField(default=dict, blank=True,
                                   help_text="Valeurs relevées à la sortie : {champ: valeur}")
    differences_sortie = models.JSONField(
        default=list, blank=True,
        help_text="Différences confirmées : [{champ, libelle, categorie, avant, apres, explication}]")
    controle_sortie_par = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
                                            related_name='fiches_controle_sortie')
    date_controle_sortie = models.DateTimeField(null=True, blank=True,
                                                verbose_name="Contrôle de sortie validé le")
    date_signature_sortie = models.DateTimeField(null=True, blank=True,
                                                 verbose_name="Signé par le client le")

    class Meta:
        db_table = 'fiches_controle'
        verbose_name = "Fiche de contrôle"
        verbose_name_plural = "Fiches de contrôle"

    @property
    def terminee(self):
        """Terminée = page 3 validée avec la signature du technicien."""
        return bool(self.signature_technicien)

    @property
    def signee_client(self):
        """Le client a signé l'état d'entrée."""
        return bool(self.signature_client_avant)

    @property
    def sortie_signee(self):
        """Contrôle de sortie archivé et signé par le client."""
        return bool(self.signature_client_apres and self.date_signature_sortie)

    def __str__(self):
        return f"Fiche contrôle - {self.immatriculation or self.entree_id}"


# ══════════════════════════════════════════════════════════════════
#  CONTRÔLE DE SORTIE EN COURS — table temporaire
# ══════════════════════════════════════════════════════════════════
class FicheControleTemporaire(ElementsControle):
    class Statut(models.TextChoices):
        SAISIE = 'SAISIE', "Saisie en cours"
        VERIFICATION = 'VERIFICATION', "Vérification des différences"
        A_SIGNER = 'A_SIGNER', "Validée, en attente de la signature du client"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fiche_controle = models.OneToOneField(
        FicheControle,
        on_delete=models.CASCADE,
        related_name='controle_sortie_temp',
    )
    kilometrage_sortie = models.IntegerField(null=True, blank=True, verbose_name="Kilométrage à la sortie")
    statut = models.CharField(max_length=15, choices=Statut.choices, default=Statut.SAISIE)
    # {champ: {'apres': valeur confirmée, 'explication': '...', 'par': id, 'le': iso}}
    confirmations = models.JSONField(default=dict, blank=True)

    technicien = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True,
                                   related_name='controles_sortie_en_cours')
    date_debut = models.DateTimeField(auto_now_add=True)
    date_maj = models.DateTimeField(auto_now=True)
    date_validation = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'fiches_controle_temporaires'
        verbose_name = "Contrôle de sortie en cours"
        verbose_name_plural = "Contrôles de sortie en cours"

    def __str__(self):
        return f"Contrôle de sortie en cours - {self.fiche_controle}"

