"""
Hooks à appeler depuis les vues après la création d'un bon de sortie.
Usage dans guerite/views.py :

    from apps.notifications.hooks import notifier_bon_sortie_cree
    
    bon = BonSortie.objects.create(...)
    notifier_bon_sortie_cree(bon)
"""
import logging

from apps.notifications.services import envoyer_notification_bon_sortie

logger = logging.getLogger(__name__)


def notifier_bon_sortie_cree(bon):
    """
    Appeler cette fonction juste après la création de n'importe quel bon de sortie.
    Elle envoie automatiquement l'email aux destinataires actifs.
    """
    try:
        ok = envoyer_notification_bon_sortie(bon)
        if ok:
            logger.info(f"Notification envoyée pour bon {bon.numero}")
        else:
            logger.warning(f"Notification non envoyée pour bon {bon.numero} (aucun destinataire ?)")
    except Exception as e:
        # On ne fait jamais crasher la vue à cause de l'email
        logger.error(f"Erreur notification bon {bon.numero}: {e}")