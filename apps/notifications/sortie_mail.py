"""
Service d'envoi d'emails pour les bons de sortie.
Appelé depuis guerite/views.py au moment de la création d'un bon.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.notifications.models import DestinataireEmail
from apps.documents.pdf_generator import generer_pdf_bon_sortie
from apps.vehicules.models import Client  # adapte le chemin si besoin

logger = logging.getLogger(__name__)


def get_destinataires_actifs(bon=None):
    """
    Retourne les emails des destinataires actifs.
    Si un bon est fourni, ajoute l'email du client (valide_par = id Client).
    """
    emails = list(
        DestinataireEmail.objects
        .filter(actif=True)
        .values_list('email', flat=True) 
    )

    if bon is not None and bon.valide_par_id:
        # valide_par stocke l'id du Client
        client = Client.objects.filter(id=bon.vehicule.client).first()
        if client and client.email and client.email.strip():
            email = client.email.strip() 
            if email not in emails:
                emails.append(email)

    return emails



def get_destinataires_actifs(bon=None):
    """
    Retourne les emails des destinataires actifs.
    Si un bon est fourni, ajoute l'email du client propriétaire du véhicule.
    """

    emails = list(
        DestinataireEmail.objects
        .filter(actif=True)
        .values_list('email', flat=True) 
    )

    if bon is not None:
        # Le client est déjà un objet via la FK
        client = getattr(bon.vehicule, 'client', None) if bon.vehicule else None

        if client and client.email and client.email.strip():
            email = client.email.strip()
            if email not in emails:
                emails.append(email)

    return emails

def envoyer_notification_sortie_vehicule(bon):
    """
    Envoie un email avec le PDF du bon de sortie en pièce jointe
    à tous les destinataires actifs + client.
    """
    destinataires = get_destinataires_actifs(bon)
    if not destinataires:
        logger.info("Aucun destinataire actif — email sortie véhicule non envoyé.")
        return False

    immat = (
        bon.vehicule.immatriculation
        if bon.vehicule
        else "Non précisé"
    )
    marque_modele = ""
    if bon.vehicule:
        marque_modele = f"{bon.vehicule.marque or ''} {bon.vehicule.modele or ''}".strip()

    sujet = f"[Garage] Sortie véhicule — {immat}"

    date_str = timezone.localtime(
        bon.date_validation or bon.created_at
    ).strftime("%d/%m/%Y à %H:%M")

    texte = (
        f"Bonjour,\n\n"
        f"Un nouveau véhicule vient de sortir.\n\n"
        f"N° Bon     : {bon.numero}\n"
        f"Véhicule   : {immat}"
        + (f" ({marque_modele})" if marque_modele else "")
        + f"\n"
        f"Demandeur  : {bon.nom_demandeur or '—'}\n"
        f"Date sortie: {date_str}\n\n"
        f"Le bon de sortie est joint à cet email au format PDF.\n\n"
        f"— Système Garage Suivi (message automatique)"
    )

    try:
        pdf_bytes = generer_pdf_bon_sortie(bon)

        email = EmailMessage(
            subject=sujet,
            body=texte,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@garage.cm'),
            to=destinataires,
        )
        email.attach(
            filename=f"bon-sortie-{bon.numero}.pdf",
            content=pdf_bytes,
            mimetype='application/pdf',
        )
        email.send(fail_silently=False)

        logger.info(
            "Email + PDF sortie véhicule %s envoyé à %s destinataire(s): %s",
            bon.numero, len(destinataires), destinataires
        )
        return True

    except Exception as e:
        logger.error("Erreur envoi email/PDF sortie véhicule %s: %s", bon.numero, e)
        return False

def envoyer_email_test(email_test=None):
    """
    Envoie un email de test à tous les destinataires actifs (ou un seul si précisé).
    """
    if email_test:
        destinataires = [email_test]
    else:
        destinataires = get_destinataires_actifs()

    if not destinataires:
        return False, "Aucun destinataire actif configuré."

    sujet = "[Garage] ✅ Test de notification — bon de sortie"
    texte = (
        "Ceci est un email de test.\n\n"
        "Si vous recevez cet email, la configuration est correcte.\n"
        "Vous recevrez un email similaire (avec PDF joint) "
        "à chaque création de bon de sortie.\n\n"
        "— Système Garage Suivi"
    )

    try:
        email = EmailMessage(
            subject=sujet,
            body=texte,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@garage.cm'),
            to=destinataires,
        )
        email.send(fail_silently=False)
        return True, (
            f"Email de test envoyé à {len(destinataires)} adresse(s) : "
            f"{', '.join(destinataires)}"
        )
    except Exception as e:
        return False, str(e)