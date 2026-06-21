from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Vehicule

@login_required
def liste_vehicules(request):
    q = request.GET.get('q', '')
    vehicules = Vehicule.objects.select_related('client').order_by('immatriculation')
    if q:
        vehicules = vehicules.filter(
            Q(immatriculation__icontains=q) | Q(marque__icontains=q) |
            Q(modele__icontains=q) | Q(client__nom__icontains=q)
        )
    return render(request, 'vehicules/liste.html', {'vehicules': vehicules[:100], 'q': q})

@login_required
def detail_vehicule(request, vehicule_id):
    vehicule = get_object_or_404(Vehicule.objects.select_related('client'), id=vehicule_id)
    return render(request, 'vehicules/detail.html', {
        'vehicule': vehicule,
        'historique_entrees': vehicule.entrees.order_by('-date_entree')[:20],
        'historique_or': vehicule.ordres_reparation.order_by('-date_creation')[:10],
    })
