"""
apps/reception/views_detail.py

Vue détail réception : affiche la progression de CHAQUE OR (un par
atelier sollicité) ainsi que le bon de sortie s'il existe. Le
réceptionniste peut faire sortir le véhicule à tout moment, quel que
soit l'état d'avancement des ateliers.
"""
from django.shortcuts import render, get_object_or_404
from apps.accounts.decorators import receptionniste_required
from .models import Reception


@receptionniste_required
def detail_reception(request, rec_id):
    rec = get_object_or_404(
        Reception.objects.select_related('vehicule', 'vehicule__client', 'entree'),
        id=rec_id
    )

    ordres = list(
        rec.ordres_reparation.select_related('atelier').prefetch_related('taches')
        .order_by('date_creation')
    )
    for o in ordres:
        o.a_fiche_controle  = hasattr(o, 'fiche_controle')
        o.a_fiche_technique = hasattr(o, 'fiche_technique')
        o.stats             = o.taches_stats

    # Bon de sortie associé, s'il existe (import tardif pour éviter
    # une dépendance circulaire avec apps.guerite)
    bon_sortie = None
    try:
        from apps.guerite.models import BonSortie
        bon_sortie = BonSortie.objects.filter(reception=rec).first()
    except Exception:
        pass

    return render(request, 'reception/detail_reception.html', {
        'rec': rec,
        'ordres_reparation': ordres,
        'bon_sortie': bon_sortie,
    })
