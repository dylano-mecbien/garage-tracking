"""
apps/inventaire/adapters.py — LE SEUL ENDROIT qui touche à tes modèles de la guérite.

Je n'ai pas le code exact de ton `EnregistrementEntree` : les champs sont donc renseignés seulement s'ils
existent. Si ton modèle exige un champ que je ne connais pas, l'application du mouvement échoue proprement
(message affiché à l'administrateur, le mouvement reste en attente) et il suffit d'ajouter ce champ ici.
"""
import re
from django.db.models import Value
from django.db.models.functions import Replace, Upper
from django.utils import timezone

DEFAUT_MOTIFS = [('REPARATION', 'Réparation'), ('VISITE', 'Visite'), ('LIVRAISON', 'Livraison'), ('AUTRE', 'Autre')]


def normaliser_plaque(texte):
    return re.sub(r'[^A-Z0-9]', '', (texte or '').upper())


def _champs(model):
    return {f.name for f in model._meta.get_fields()}


def motifs_entree():
    """Les motifs d'entrée de ton modèle (choices du champ `motif`), sinon une liste par défaut."""
    from apps.guerite.models import EnregistrementEntree
    try:
        ch = [c for c in EnregistrementEntree._meta.get_field('motif').choices if c[0]]
        return list(ch) or DEFAUT_MOTIFS
    except Exception:
        return DEFAUT_MOTIFS


def libelle_motif(code):
    return dict(motifs_entree()).get(code, code or '—')


def trouver_vehicule(plaque):
    """Véhicule dont la plaque correspond (insensible à la casse, aux espaces, tirets et points)."""
    from apps.vehicules.models import Vehicule
    norm = normaliser_plaque(plaque)
    if not norm:
        return None
    expr = Replace(Replace(Replace(Upper('immatriculation'), Value(' '), Value('')), Value('-'), Value('')),
                   Value('.'), Value(''))
    return Vehicule.objects.annotate(_plaque=expr).filter(_plaque=norm).first()


def entrees_ouvertes():
    """Une entrée (la plus récente) par véhicule que le SYSTÈME croit présent."""
    from apps.guerite.models import EnregistrementEntree
    qs = (EnregistrementEntree.objects.exclude(statut='SORTI')
          .select_related('vehicule', 'vehicule__client').order_by('vehicule_id', '-date_entree'))
    vus, out = set(), []
    for e in qs:
        if e.vehicule_id not in vus:
            vus.add(e.vehicule_id)
            out.append(e)
    return out


def conducteurs_noms():
    try:
        from apps.vehicules.models import Conducteur
        return [f"{(c.prenom or '').strip()} {c.nom}".strip() for c in Conducteur.objects.all().order_by('nom')[:500]]
    except Exception:
        return []


def trouver_conducteur(nom):
    """Conducteur existant dont « prénom nom » ou « nom prénom » correspond exactement au nom saisi."""
    try:
        from apps.vehicules.models import Conducteur
    except Exception:
        return None
    cible = ' '.join((nom or '').lower().split())
    if not cible:
        return None
    for c in Conducteur.objects.all():
        a = ' '.join(f"{c.prenom or ''} {c.nom}".lower().split())
        b = ' '.join(f"{c.nom} {c.prenom or ''}".lower().split())
        if cible in (a, b):
            return c
    return None


def _conducteur_pour(mv):
    if mv.conducteur_id:
        return mv.conducteur
    c = trouver_conducteur(mv.chauffeur)
    if c is None and mv.chauffeur and mv.chauffeur_tel:
        try:                                                    # on ne crée un conducteur que s'il a un téléphone
            from apps.vehicules.models import Conducteur
            parts = mv.chauffeur.split()
            c = Conducteur.objects.create(nom=parts[-1] if parts else mv.chauffeur,
                                          prenom=' '.join(parts[:-1]), telephone=mv.chauffeur_tel)
        except Exception:
            c = None
    return c


def creer_entree_definitive(mv, admin):
    """ENTRÉE validée → enregistrement DÉFINITIF d'entrée (EnregistrementEntree). Retourne l'entrée créée."""
    from apps.guerite import models as g
    E = g.EnregistrementEntree
    ch = _champs(E)
    kw = {'vehicule': mv.vehicule}
    if 'motif' in ch and mv.motif:
        kw['motif'] = mv.motif
    cond = _conducteur_pour(mv)
    if 'conducteur' in ch and cond is not None:
        kw['conducteur'] = cond
    for nom in ('cree_par', 'created_by', 'enregistre_par'):
        if nom in ch:
            kw[nom] = mv.cree_par or admin
            break
    if 'observations' in ch:
        kw['observations'] = (f"Entrée enregistrée via inventaire — chauffeur : {mv.chauffeur or '—'}"
                              f"{' (' + mv.chauffeur_tel + ')' if mv.chauffeur_tel else ''}")
    stat = getattr(g, 'StatutEntree', None)
    if 'statut' in ch and stat is not None and hasattr(stat, 'EN_COURS'):
        kw['statut'] = stat.EN_COURS
    return E.objects.create(**kw)


def cloturer_sortie_definitive(mv, admin):
    """SORTIE validée → enregistrement DÉFINITIF de sortie (entrée clôturée)."""
    from apps.guerite.models import EnregistrementEntree
    e = mv.entree or (EnregistrementEntree.objects.filter(vehicule=mv.vehicule).exclude(statut='SORTI')
                      .order_by('-date_entree').first())
    if e is None or e.statut == 'SORTI':
        raise ValueError("Ce véhicule n'a plus d'entrée en cours (déjà sorti ?).")
    e.statut = 'SORTI'
    update = ['statut']
    if 'date_sortie' in _champs(EnregistrementEntree):
        e.date_sortie = timezone.now()
        update.append('date_sortie')
    e.save(update_fields=update)
    try:                                                         # la réception liée passe aussi à « sorti »
        rec = e.reception
        if rec.statut != 'SORTI':
            rec.statut = 'SORTI'
            rec.save(update_fields=['statut', 'updated_at'])
    except Exception:
        pass
