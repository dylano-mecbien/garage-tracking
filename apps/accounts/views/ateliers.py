"""
Ateliers : liste + création / modification / suppression.
"""
import re

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.choices import StatutOR, StatutTache
from apps.atelier.models import Atelier, CompteRendu, OrdreReparation, ReouvertureOR, Tache
from apps.audit.models import ActionType
from apps.audit.service import log_action

from ..decorators import admin_required
from ..models import Role, User
from ._utils import STATUTS_OR_ACTIFS, post_str

import datetime
from collections import Counter, defaultdict

from django.db.models import Count, Q, Sum


EN_COURS = [StatutOR.OUVERT, StatutOR.REOUVERT]


def _prochain_code():
    """ATL-001, ATL-002… basé sur le plus grand numéro existant."""
    nums = [int(m.group(1)) for code in Atelier.objects.values_list('code', flat=True)
            if (m := re.fullmatch(r'ATL-(\d+)', code or ''))]
    return f"ATL-{(max(nums) + 1) if nums else 1:03d}"


def _remplir(atelier, request):
    """Champs communs création / modification."""
    chef_id = post_str(request, 'chef_id')
    atelier.nom = post_str(request, 'nom')
    atelier.localisation = post_str(request, 'localisation')
    atelier.description = post_str(request, 'description')
    atelier.responsable = User.objects.filter(id=chef_id, role=Role.RESP_ATELIER).first() if chef_id else None
    atelier.is_active = 'is_active' in request.POST


def _creer(request):
    if not post_str(request, 'nom'):
        return messages.error(request, "Le nom de l'atelier est obligatoire.")

    with transaction.atomic():
        code = post_str(request, 'code').upper() or _prochain_code()
        if Atelier.objects.filter(code=code).exists():
            return messages.error(request, f"Le code « {code} » existe déjà.")
        a = Atelier(code=code)
        _remplir(a, request)
        a.save()

    log_action(request, ActionType.CREATION, 'ADMIN', a)
    messages.success(request, f"✅ Atelier « {a.nom} » créé.")


def _modifier(request, atelier_id):
    a = get_object_or_404(Atelier, id=atelier_id)
    if not post_str(request, 'nom'):
        return messages.error(request, "Le nom est obligatoire.")
    _remplir(a, request)
    a.save()
    log_action(request, ActionType.MODIFICATION, 'ADMIN', a)
    messages.success(request, f"✅ Atelier « {a.nom} » mis à jour.")


def _supprimer(request, atelier_id):
    a = get_object_or_404(Atelier, id=atelier_id)
    nb_actifs = a.ordres_reparation.filter(statut__in=STATUTS_OR_ACTIFS).count()
    if nb_actifs:
        return messages.error(request, f"Impossible : l'atelier « {a.nom} » a {nb_actifs} "
                                       "OR actif(s). Clôturez-les d'abord.")
    nom = a.nom
    log_action(request, ActionType.SUPPRESSION, 'ADMIN', details={'atelier': nom, 'id': str(a.id)})
    a.delete()
    messages.success(request, f"✅ Atelier « {nom} » supprimé.")


@admin_required
def admin_ateliers(request):
    if request.method == 'POST':
        action = request.POST.get('action', '')
        atelier_id = post_str(request, 'atelier_id')

        if action == 'creer':
            _creer(request)
        elif action == 'modifier' and atelier_id:
            _modifier(request, atelier_id)
        elif action == 'supprimer' and atelier_id:
            _supprimer(request, atelier_id)
        else:
            messages.error(request, "Action invalide.")
        return redirect('admin_ateliers')

    ateliers = list(
        Atelier.objects
        .select_related('responsable')
        .annotate(
            nb_or_en_cours=Count('ordres_reparation',
                                 filter=Q(ordres_reparation__statut__in=STATUTS_OR_ACTIFS),
                                 distinct=True),
            nb_or_total=Count('ordres_reparation', distinct=True),
            nb_techniciens=Count('employes', distinct=True),
        )
        .order_by('is_active', 'nom')
    )

    return render(request, 'admin_custom/ateliers/liste.html', {
        'ateliers': ateliers,
        'stats': {
            'total': len(ateliers),
            'actifs': sum(a.is_active for a in ateliers),
            'inactifs': sum(not a.is_active for a in ateliers),
            'nb_techniciens': sum(a.nb_techniciens for a in ateliers),
            'or_en_cours': sum(a.nb_or_en_cours for a in ateliers),
        },
        'chefs_disponibles': User.objects.filter(role=Role.RESP_ATELIER, is_active=True).order_by('nom', 'prenom'),
    })


def _agg_taches(**filtres):
    return Tache.objects.filter(**filtres).aggregate(
        total=Count('id'), validees=Count('id', filter=Q(statut=StatutTache.VALIDEE)),
        est=Sum('duree_estimee_minutes'), reel=Sum('duree_reelle_minutes'))



@admin_required
def detail_atelier(request, atelier_id):
    # ── 1) Charger l'atelier + son responsable ──
    a = get_object_or_404(
        Atelier.objects.select_related('responsable'),
        id=atelier_id,
    )

    statut = request.GET.get('statut', '')
    debut  = request.GET.get('debut', '')
    fin    = request.GET.get('fin', '')

    # ── 2) Réouvertures liées à cet atelier ──
    reouv_pairs = list(
        ReouvertureOR.objects
        .filter(taches__atelier=a)
        .values_list('id', 'ordre_reparation_id')
        .distinct()
    )
    reouv_par_or = Counter(or_id for _, or_id in reouv_pairs)

    # ── 3) OR de l'atelier ──
    qs = (
        OrdreReparation.objects
        .filter(ateliers=a)
        .select_related('vehicule', 'vehicule__client')
    )

    if statut == 'cours':
        qs = qs.filter(statut__in=EN_COURS)
    elif statut == 'clos':
        qs = qs.filter(statut=StatutOR.CLOTURE)
    elif statut == 'reouverts':
        qs = qs.filter(id__in=list(reouv_par_or))

    try:
        if debut:
            qs = qs.filter(date_creation__date__gte=datetime.date.fromisoformat(debut))
        if fin:
            qs = qs.filter(date_creation__date__lte=datetime.date.fromisoformat(fin))
    except ValueError:
        pass

    # ⚠️ Attention aux Sum() sur M2M qui peuvent doubler
    # Utilisez plutôt une agrégation via une sous-requête ou un .values() distinct
    ors = list(
        qs.annotate(
            nb_taches=Count(
                'taches',
                filter=Q(taches__atelier=a),
                distinct=True,
            ),
            nb_validees=Count(
                'taches',
                filter=Q(taches__atelier=a, taches__statut=StatutTache.VALIDEE),
                distinct=True,
            ),
        )
        .order_by('-date_creation')
    )

    # ── 4) Calculer durées par OR en Python (évite les doublons M2M) ──
    for o in ors:
        taches_atelier = [
            t for t in o.taches.all()
            if t.atelier_id == a.id
        ]
        o.est_atelier  = sum(t.duree_estimee_minutes or 0 for t in taches_atelier)
        o.reel_atelier = sum(t.duree_reelle_minutes  or 0 for t in taches_atelier)
        o.nb_reouv     = reouv_par_or.get(o.id, 0)
        o.taches_atelier = taches_atelier
        o.reouvrables  = [
            t for t in taches_atelier
            if t.statut in (StatutTache.VALIDEE, StatutTache.TERMINEE)
        ]

    # ── 5) Réouvertures (détail) ──
    reouvertures = list(
        ReouvertureOR.objects
        .filter(taches__atelier=a)
        .distinct()
        .select_related('ordre_reparation__vehicule', 'reouvert_par')   # ✅
        .prefetch_related('taches')
        .order_by('-date_reouverture')                                    # ✅
    )
    for r in reouvertures:
        r.taches_atelier = [t for t in r.taches.all() if t.atelier_id == a.id]

    # ── 6) Techniciens ──
    techniciens = (
        CompteRendu.objects
        .filter(tache__atelier=a)
        .values(
            'technicien__id',
            'technicien__nom',        # ✅
            'technicien__prenom',     # ✅
            'technicien__email',
        )
        .annotate(
            nb_taches=Count('tache', distinct=True),
            temps=Sum('duree_minutes'),
        )
        .order_by('-temps')
    )

    # ── 7) KPI ──
    tous = OrdreReparation.objects.filter(ateliers=a)

    kpi = {
        'nb_or':     tous.count(),
        'en_cours':  tous.filter(statut__in=EN_COURS).count(),
        'clotures':  tous.filter(statut=StatutOR.CLOTURE).count(),
        'reouverts': len(reouv_par_or),
        **_agg_taches(atelier=a),
    }

    return render(request, 'atelier/admin/admin_atelier_detail.html', {
        'a':            a,
        'ors':          ors,
        'reouvertures': reouvertures,
        'techniciens':  techniciens,
        'statut':       statut,
        'debut':        debut,
        'fin':          fin,
        'kpi':          kpi,
    }) 