from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings

def envoyer_email_validation(bon):
    """
    Envoie un email au valideur pour signaler qu'un bon de sortie
    est en attente de validation.
    """
    sujet = f"Bon de sortie {bon.numero} en attente de validation"
    lien = f"{settings.BASE_URL}{reverse('valider_bon_sortie', args=[bon.id])}"
    message = (
        f"Bonjour,\n\n"
        f"Le bon de sortie n° {bon.numero} a été créé par {bon.cree_par.full_name}.\n"
        f"Type : {bon.get_types_display()}\n"
        f"Demandeur : {bon.nom_demandeur}\n\n"
        f"Veuillez cliquer sur le lien ci-dessous pour le valider :\n"
        f"{lien}\n\n"
        f"Cordialement,\n"
        f"Application Garage Suivi"
    )
    send_mail(
        sujet,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [settings.VALIDATEUR_EMAIL],
        fail_silently=False,
    )