from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count
from apps.accounts.decorators import admin_required
from apps.audit.service import log_action
from apps.audit.models import ActionType


@admin_required
def admin_conducteurs(request):
    from apps.vehicules.models import Conducteur
    from apps.guerite.models import EnregistrementEntree

    q         = request.GET.get('q', '').strip()
    categorie = request.GET.get('categorie', '')

    if request.method == 'POST':
        action  = request.POST.get('action')
        cond_id = request.POST.get('cond_id', '').strip()
        if action == 'creer':
            nom, prenom, tel = request.POST.get('nom','').strip(), request.POST.get('prenom','').strip(), request.POST.get('telephone','').strip()
            if not all([nom, prenom, tel]):
                messages.error(request, "Nom, prénom et téléphone sont obligatoires.")
            elif Conducteur.objects.filter(telephone=tel).exists():
                messages.error(request, f"Un conducteur avec le téléphone {tel} existe déjà.")
            else:
                c = Conducteur.objects.create(
                    nom=nom, prenom=prenom, telephone=tel,
                    telephone2=request.POST.get('telephone2','').strip(),
                    cni=request.POST.get('cni','').strip(),
                    permis=request.POST.get('permis','').strip(),
                    categorie_permis=request.POST.get('categorie_permis','').strip(),
                    created_by=request.user,
                )
                log_action(request, ActionType.CREATION, 'ADMIN', c)
                messages.success(request, f"Conducteur {c.prenom} {c.nom} créé.")
        elif action == 'modifier' and cond_id:
            c   = get_object_or_404(Conducteur, id=cond_id)
            nom = request.POST.get('nom','').strip()
            tel = request.POST.get('telephone','').strip()
            if not nom or not tel:
                messages.error(request, "Nom et téléphone sont obligatoires.")
            else:
                c.nom=nom; c.prenom=request.POST.get('prenom','').strip()
                c.telephone=tel; c.telephone2=request.POST.get('telephone2','').strip()
                c.cni=request.POST.get('cni','').strip()
                c.permis=request.POST.get('permis','').strip()
                c.categorie_permis=request.POST.get('categorie_permis','').strip()
                c.save()
                log_action(request, ActionType.MODIFICATION, 'ADMIN', c)
                messages.success(request, f"Conducteur {c.prenom} {c.nom} mis à jour.")
        return redirect('admin_conducteurs')

    qs = Conducteur.objects.all()
    if q:
        qs = qs.filter(Q(nom__icontains=q)|Q(prenom__icontains=q)|Q(telephone__icontains=q)|Q(cni__icontains=q)|Q(permis__icontains=q))
    if categorie:
        qs = qs.filter(categorie_permis__icontains=categorie)

    conducteurs = []
    for c in qs[:100]:
        c.nb_passages     = EnregistrementEntree.objects.filter(conducteur=c).count()
        c.dernier_passage = EnregistrementEntree.objects.filter(conducteur=c).select_related('vehicule').order_by('-date_entree').first()
        conducteurs.append(c)

    categories = list(Conducteur.objects.exclude(categorie_permis='').exclude(categorie_permis__isnull=True)
        .values_list('categorie_permis', flat=True).distinct().order_by('categorie_permis'))

    return render(request, 'admin_custom/conducteurs/liste.html', {
        'conducteurs': conducteurs, 'nb_total': Conducteur.objects.count(),
        'categories': categories, 'filters': {'q': q, 'categorie': categorie},
    })


@admin_required
def admin_supprimer_conducteur(request, cond_id):
    from apps.vehicules.models import Conducteur
    from apps.guerite.models import EnregistrementEntree
    c = get_object_or_404(Conducteur, id=cond_id)
    if EnregistrementEntree.objects.filter(conducteur=c).exists():
        messages.error(request, f"Impossible : {c.prenom} {c.nom} a des passages enregistrés.")
    elif request.method == 'POST':
        nom = f"{c.prenom} {c.nom}"
        log_action(request, ActionType.SUPPRESSION, 'ADMIN', details={'conducteur': nom})
        c.delete()
        messages.success(request, f"Conducteur {nom} supprimé.")
    return redirect('admin_conducteurs')


@admin_required
def admin_nettoyage(request):
    from apps.vehicules.models import Vehicule, Client, Conducteur
    vehicules_orphelins   = list(Vehicule.objects.filter(is_active=True).annotate(nb_entrees=Count('entrees')).filter(nb_entrees=0).select_related('client').order_by('immatriculation'))
    clients_orphelins     = list(Client.objects.filter(is_active=True).annotate(nb_veh=Count('vehicules')).filter(nb_veh=0).order_by('nom'))
    conducteurs_orphelins = list(Conducteur.objects.annotate(nb_pass=Count('entrees')).filter(nb_pass=0).order_by('nom'))
    return render(request, 'admin_custom/nettoyage.html', {
        'vehicules_orphelins': vehicules_orphelins,
        'clients_orphelins': clients_orphelins,
        'conducteurs_orphelins': conducteurs_orphelins,
    })


@admin_required
def admin_supprimer_vehicules_orphelins(request):
    from apps.vehicules.models import Vehicule
    if request.method != 'POST': return redirect('admin_nettoyage')
    ids = request.POST.getlist('vehicule_ids')
    if not ids: messages.warning(request, "Aucun véhicule sélectionné."); return redirect('admin_nettoyage')
    qs = Vehicule.objects.filter(id__in=ids).annotate(nb=Count('entrees')).filter(nb=0)
    count = qs.count()
    log_action(request, ActionType.SUPPRESSION, 'ADMIN', details={'type': 'vehicules_orphelins', 'count': count})
    qs.delete()
    messages.success(request, f"✅ {count} véhicule(s) supprimé(s).")
    return redirect('admin_nettoyage')


@admin_required
def admin_supprimer_clients_orphelins(request):
    from apps.vehicules.models import Client
    if request.method != 'POST': return redirect('admin_nettoyage')
    ids = request.POST.getlist('client_ids')
    if not ids: messages.warning(request, "Aucun client sélectionné."); return redirect('admin_nettoyage')
    qs = Client.objects.filter(id__in=ids).annotate(nb=Count('vehicules')).filter(nb=0)
    count = qs.count()
    log_action(request, ActionType.SUPPRESSION, 'ADMIN', details={'type': 'clients_orphelins', 'count': count})
    qs.delete()
    messages.success(request, f"✅ {count} client(s) supprimé(s).")
    return redirect('admin_nettoyage')


@admin_required
def admin_supprimer_conducteurs_orphelins(request):
    from apps.vehicules.models import Conducteur
    if request.method != 'POST': return redirect('admin_nettoyage')
    ids = request.POST.getlist('conducteur_ids')
    if not ids: messages.warning(request, "Aucun conducteur sélectionné."); return redirect('admin_nettoyage')
    qs = Conducteur.objects.filter(id__in=ids).annotate(nb=Count('entrees')).filter(nb=0)
    count = qs.count()
    log_action(request, ActionType.SUPPRESSION, 'ADMIN', details={'type': 'conducteurs_orphelins', 'count': count})
    qs.delete()
    messages.success(request, f"✅ {count} conducteur(s) supprimé(s).")
    return redirect('admin_nettoyage')