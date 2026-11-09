# ─────────────────────────────────────────────────────────────────────────
#  Impression groupée : tous les bons de la liste filtrée, 1 bon par page.
#  À coller dans le fichier views où se trouve export_bons_liste_pdf.
# ─────────────────────────────────────────────────────────────────────────
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone

from apps.documents.pdf_generator import generer_pdf_bons_sortie
from apps.guerite.models import BonSortie
# from .models import BonSortie   # déjà importé chez toi

# Garde-fou : au-delà, on demande de filtrer davantage (un PDF de 1000 pages
# bloquerait le serveur et l'imprimante).
MAX_BONS_IMPRESSION = 300


def filtrer_bons(request, qs):
    """Applique les mêmes filtres GET que la liste : q, type, etat, periode,
    date_debut, date_fin, sort.

    ⚠️ Si ta vue liste (ou export_bons_liste_pdf) a déjà une fonction de
    filtrage, utilise-la à la place pour être sûr d'avoir exactement les
    mêmes bons que ceux affichés.
    """
    g = request.GET
    q = (g.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(numero__icontains=q)
            | Q(vehicule__immatriculation__icontains=q)
            | Q(nom_demandeur__icontains=q)
        )
    if g.get('type'):
        qs = qs.filter(types=g['type'])
    if g.get('etat'):
        qs = qs.filter(etats=g['etat'])

    periode = g.get('periode')
    aujourd_hui = timezone.localdate()
    if periode == 'today':
        qs = qs.filter(created_at__date=aujourd_hui)
    elif periode == 'week':
        qs = qs.filter(created_at__date__gte=aujourd_hui - timedelta(days=aujourd_hui.weekday()))
    elif periode == 'month':
        qs = qs.filter(created_at__date__gte=aujourd_hui.replace(day=1))
    elif periode == 'custom':
        for cle, lookup in (('date_debut', 'created_at__date__gte'),
                            ('date_fin', 'created_at__date__lte')):
            try:
                qs = qs.filter(**{lookup: datetime.strptime(g.get(cle, ''), '%Y-%m-%d').date()})
            except ValueError:
                pass

    return qs.order_by('numero' if g.get('sort') == 'numero' else '-created_at')


@login_required
def imprimer_bons_sortie(request):
    """PDF avec chaque bon de la liste filtrée sur sa propre page."""
    bons = filtrer_bons(
        request,
        BonSortie.objects.select_related(
            'vehicule', 'vehicule__client', 'cree_par', 'valide_par', 'approuve_par'),
    )

    nb = bons.count()
    if nb > MAX_BONS_IMPRESSION:
        messages.warning(
            request,
            f"{nb} bons correspondent aux filtres : l'impression est limitée à "
            f"{MAX_BONS_IMPRESSION}. Affinez les filtres (période, état...).")
        return redirect(request.META.get('HTTP_REFERER') or 'liste_bons_sortie')

    pdf = generer_pdf_bons_sortie(bons, titre=f"Bons de sortie ({nb})")

    nom = f"bons-sortie-{timezone.localdate():%Y-%m-%d}.pdf"
    response = HttpResponse(pdf, content_type='application/pdf')
    # inline : s'ouvre dans le navigateur, prêt à imprimer (Ctrl+P)
    response['Content-Disposition'] = f'inline; filename="{nom}"'
    return response
