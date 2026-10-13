"""
apps/accounts/views_user_stats.py

Détail d'un utilisateur pour l'admin, avec statistiques calculées sur
une période (par défaut les 30 derniers jours), différentes selon le
rôle : Réceptionniste / Guérite / Responsable atelier / Technicien.

⚠️ IMPORTANT — à vérifier avant mise en prod :
Certains noms de champs (ex: qui a créé une entrée guérite, qui a créé
ou validé un bon de sortie) ne m'ont pas été communiqués avec certitude.
La fonction `first_existing_field()` ci-dessous teste plusieurs noms
plausibles et utilise le premier qui existe réellement sur le modèle,
pour éviter un crash si le nom diffère de ce que j'ai supposé. Si un
champ n'est trouvé sous aucun des noms testés, la statistique
correspondante est affichée à "—" au lieu de planter — dans ce cas,
ajoutez le vrai nom de champ dans la liste `candidates` correspondante.
"""
import datetime
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from apps.accounts.choices import StatutTache
from apps.accounts.decorators import admin_required
from apps.atelier.models import Atelier, OrdreReparation, Tache
from apps.guerite.models import EnregistrementEntree
from apps.reception.models import Reception


def first_existing_field(model, candidates):
    """Retourne le premier nom de champ de `candidates` qui existe sur `model`."""
    field_names = {f.name for f in model._meta.get_fields()}
    for c in candidates:
        if c in field_names:
            return c
    return None


def parse_period(request):
    """Lit ?debut=YYYY-MM-DD&fin=YYYY-MM-DD, défaut = 30 derniers jours."""
    today = timezone.now().date()
    debut_raw = request.GET.get('debut', '').strip()
    fin_raw   = request.GET.get('fin', '').strip()
    try:
        debut = datetime.date.fromisoformat(debut_raw) if debut_raw else today - datetime.timedelta(days=30)
    except ValueError:
        debut = today - datetime.timedelta(days=30)
    try:
        fin = datetime.date.fromisoformat(fin_raw) if fin_raw else today
    except ValueError:
        fin = today
    return debut, fin


def format_duree(minutes):
    """Convertit des minutes en texte lisible : 45 → '45 min', 90 → '1 h 30 min'."""
    if minutes is None:
        return "—"
    try:
        m = int(round(float(minutes)))
    except (TypeError, ValueError):
        return "—"
    if m < 0:
        m = 0
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    if r == 0:
        return f"{h} h"
    return f"{h} h {r} min"

@admin_required
def detail_utilisateur(request, user_id):
    from apps.accounts.models import User

    user = get_object_or_404(User, id=user_id)
    debut, fin = parse_period(request)
    # Bornes datetime pour filtrer les DateTimeField
    debut_dt = timezone.make_aware(datetime.datetime.combine(debut, datetime.time.min))
    fin_dt   = timezone.make_aware(datetime.datetime.combine(fin, datetime.time.max))

    stats = {}
    role = user.role

    # ═══════════════════════════════════════════════════════
    #  RÉCEPTIONNISTE
    # ═══════════════════════════════════════════════════════
    if role == 'RECEPTIONNISTE' or role == 'SUPER_RECEPTIONNISTE':
        try:
            nb_receptions = Reception.objects.filter(
                receptionniste=user, created_at__range=(debut_dt, fin_dt)
            ).count()
        except Exception:
            nb_receptions = None

        nb_bons_crees = None
        nb_bons_signes = None
        try:
            from apps.guerite.models import BonSortie
            f_created = first_existing_field(BonSortie, ['created_by', 'cree_par'])
            f_date    = first_existing_field(BonSortie, ['created_at', 'date_creation'])
            if f_created and f_date:
                nb_bons_crees = BonSortie.objects.filter(**{
                    f_created: user, f'{f_date}__range': (debut_dt, fin_dt)
                }).count()

            f_valid_by = first_existing_field(BonSortie, ['valide_par', 'validated_by', 'created_by'])
            f_valid_dt = first_existing_field(BonSortie, ['date_validation', 'updated_at'])
            if f_valid_by and f_valid_dt:
                nb_bons_signes = BonSortie.objects.filter(**{
                    'statut': 'VALIDER', f_valid_by: user, f'{f_valid_dt}__range': (debut_dt, fin_dt)
                }).count()
        except Exception:
            pass

        stats = {
            'nb_receptions':  nb_receptions,
            'nb_bons_crees':  nb_bons_crees,
            'nb_bons_signes': nb_bons_signes,
        }

    # ═══════════════════════════════════════════════════════
    #  GUÉRITE
    # ═══════════════════════════════════════════════════════
    elif role == 'GUERITE':
        nb_entrees = nb_sorties = nb_vehicules = nb_clients = None
        try:
            f_created = first_existing_field(EnregistrementEntree, ['cree_par', 'created_by'])
            if f_created:
                nb_entrees = EnregistrementEntree.objects.filter(**{
                    f_created: user, 'date_entree__range': (debut_dt, fin_dt)
                }).count()
                nb_sorties = EnregistrementEntree.objects.filter(**{
                    f_created: user, 'statut': 'SORTI', 'date_sortie__range': (debut_dt, fin_dt)
                }).count()
        except Exception:
            pass
        try:
            from apps.vehicules.models import Vehicule, Client
            nb_vehicules = Vehicule.objects.filter(
                created_by=user, created_at__range=(debut_dt, fin_dt)
            ).count()
            nb_clients = Client.objects.filter(
                created_by=user, created_at__range=(debut_dt, fin_dt)
            ).count()
        except Exception:
            pass

        stats = {
            'nb_entrees':  nb_entrees,
            'nb_sorties':  nb_sorties,
            'nb_vehicules': nb_vehicules,
            'nb_clients':  nb_clients,
        }

    # ═══════════════════════════════════════════════════════
    #  RESPONSABLE ATELIER / TECHNICIEN
    # ═══════════════════════════════════════════════════════
    elif role in ('RESP_ATELIER', 'TECHNICIEN'):

        taches_effectuees = Tache.objects.filter(
            techniciens=user,
            statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE],
            date_fin__range=(debut_dt, fin_dt),
        )
        durees = [t.duree_reelle_minutes for t in taches_effectuees if t.duree_reelle_minutes]
        delais = [
            int((t.date_debut - t.date_assignation).total_seconds() / 60)
            for t in taches_effectuees
            if t.date_debut and t.date_assignation
        ]
        nb_retard = sum(
            1 for t in taches_effectuees
            if t.duree_reelle_minutes and t.duree_reelle_minutes > t.duree_estimee_minutes
        )
        taches_restantes = (
                Tache.objects
                .filter(techniciens=user, statut__in=[StatutTache.A_FAIRE, StatutTache.EN_COURS])
                .select_related('ordre_reparation__vehicule', 'atelier')
                .order_by('-priorite')
            )
        taches_faites = (
        Tache.objects
        .filter(techniciens=user, statut__in=[StatutTache.TERMINEE, StatutTache.VALIDEE])
        .select_related('ordre_reparation__vehicule', 'atelier')
        .order_by('-date_fin')
    )

        duree_totale = sum(durees) if durees else 0
        duree_moyenne = round(sum(durees) / len(durees), 1) if durees else 0
        delai_moyen = round(sum(delais) / len(delais), 1) if delais else 0

        stats = {
    'nb_taches': taches_effectuees.count(),
    'duree_totale': duree_totale,
    'duree_totale_label': format_duree(duree_totale),
    'duree_moyenne': duree_moyenne,
    'duree_moyenne_label': format_duree(duree_moyenne),
    'nb_en_retard': nb_retard,
    'taches_faites': taches_faites,
    'taches_restantes': taches_restantes,
    'delai_moyen_demarrage': delai_moyen,
    'delai_moyen_demarrage_label': format_duree(delai_moyen),
}

        if role == 'RESP_ATELIER':
            atelier = Atelier.objects.filter(responsable=user).first()
            if atelier:
                stats['atelier']       = atelier
                stats['nb_or_traites'] = OrdreReparation.objects.filter(
                    ateliers=atelier, date_creation__range=(debut_dt, fin_dt)
                ).count()
                stats['nb_or_clotures'] = OrdreReparation.objects.filter(
                    ateliers=atelier, statut='CLOTURE', date_cloture__range=(debut_dt, fin_dt)
                ).count()
                stats['nb_taches_validees_par_moi'] = Tache.objects.filter(
                    ordre_reparation__atelier=atelier, valide_par=user,
                    date_validation__range=(debut_dt, fin_dt)
                ).count()

    return render(request, 'admin_custom/utilisateurs/detail.html', {
        'u': user, 'role': role, 'stats': stats,
        'debut': debut, 'fin': fin,
    })
