"""apps/atelier/utils.py"""


def entree_de(rec):
    """
    Entrée guérite d'une réception.

    Les fiches (contrôle / technique) et l'OR sont liés à l'ENTRÉE guérite. Une réception créée depuis la
    recherche de véhicule peut n'avoir AUCUNE entrée liée : on retrouve alors l'entrée encore ouverte de ce
    véhicule (non sortie, pas déjà rattachée à une autre réception) et on la rattache. Sinon → None.
    """
    if getattr(rec, 'entree_id', None):
        return rec.entree
    from apps.guerite.models import EnregistrementEntree
    e = (EnregistrementEntree.objects
         .filter(vehicule_id=rec.vehicule_id, reception__isnull=True)
         .exclude(statut='SORTI').order_by('-date_entree').first())
    if e is not None:
        rec.entree = e
        rec.save(update_fields=['entree', 'updated_at'])
    return e


MSG_SANS_ENTREE = ("Cette réception n'est liée à aucune entrée guérite et le véhicule n'a pas d'entrée en cours. "
                   "Il doit d'abord être enregistré à la guérite (entrée), puis la réception rattachée à cette entrée.")
