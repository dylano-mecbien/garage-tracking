"""
Service d'envoi d'emails pour les bons de sortie.
Appelé depuis guerite/views.py au moment de la création d'un bon.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.documents.pdf_generator import generer_pdf_bon_sortie
from apps.notifications.models import DestinataireEmail

logger = logging.getLogger(__name__)

EXPEDITEUR_PAR_DEFAUT = 'no-reply@garage.cm'
SIGNATURE = "— Système Garage Suivi (message automatique)"


# ─── Helpers ─────────────────────────────────────────────────────────────
def _expediteur():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', None) or EXPEDITEUR_PAR_DEFAUT


def _ajouter_email(emails, deja_vus, email):
    """Ajoute un email nettoyé à la liste, sans doublon (insensible à la casse)."""
    email = (email or '').strip()
    if email and email.lower() not in deja_vus:
        deja_vus.add(email.lower())
        emails.append(email)


def _email_client(bon):
    """Email du client propriétaire du véhicule du bon, ou None."""
    vehicule = getattr(bon, 'vehicule', None)
    client = getattr(vehicule, 'client', None) if vehicule else None
    return getattr(client, 'email', None) if client else None


def _envoyer(sujet, texte, destinataires, piece_jointe=None):
    """Construit et envoie l'email. piece_jointe = (nom, contenu, mimetype)."""
    email = EmailMessage(
        subject=sujet,
        body=texte,
        from_email=_expediteur(),
        to=destinataires,
    )
    if piece_jointe:
        email.attach(*piece_jointe)
    email.send(fail_silently=False)


# ─── Destinataires ───────────────────────────────────────────────────────
def get_destinataires_actifs(bon=None):
    """
    Emails des destinataires actifs (DestinataireEmail.actif=True).
    Si un bon est fourni, ajoute l'email du client propriétaire du véhicule.
    """
    emails, deja_vus = [], set()

    for email in (DestinataireEmail.objects
                  .filter(actif=True)
                  .values_list('email', flat=True)):
        _ajouter_email(emails, deja_vus, email)

    if bon is not None:
        _ajouter_email(emails, deja_vus, _email_client(bon))

    return emails


# ─── Notification de sortie ──────────────────────────────────────────────
def _texte_sortie(bon):
    vehicule = bon.vehicule
    immat = vehicule.immatriculation if vehicule else "Non précisé"
    marque_modele = (
        f"{vehicule.marque or ''} {vehicule.modele or ''}".strip() if vehicule else ""
    )
    date_ref = getattr(bon, 'date_validation', None) or bon.created_at
    date_str = timezone.localtime(date_ref).strftime("%d/%m/%Y à %H:%M")

    vehicule_str = f"{immat} ({marque_modele})" if marque_modele else immat

    lignes = [
        "Bonjour,",
        "",
        "Un bon de sortie vient d'être émis pour le véhicule ci-dessous.",
        "",
        f"N° Bon      : {bon.numero}",
        f"Véhicule    : {vehicule_str}",
        f"Demandeur   : {bon.nom_demandeur or '—'}",
        f"Date        : {date_str}",
        "",
        "Le bon de sortie est joint à cet email au format PDF.",
        "",
        SIGNATURE,
    ]
    return immat, "\n".join(lignes)


def envoyer_notification_sortie_vehicule(bon):
    """
    Envoie le PDF du bon de sortie à tous les destinataires actifs + le client.
    Retourne True si l'email est parti, False sinon (ne lève jamais d'exception,
    pour ne pas bloquer la création du bon).
    """
    destinataires = get_destinataires_actifs(bon)
    if not destinataires:
        logger.info("Bon %s : aucun destinataire actif, email non envoyé.", bon.numero)
        return False

    immat, texte = _texte_sortie(bon)
    sujet = f"[Garage] Sortie véhicule — {immat}"

    try:
        pdf_bytes = generer_pdf_bon_sortie(bon)
        _envoyer(
            sujet, texte, destinataires,
            piece_jointe=(f"bon-sortie-{bon.numero}.pdf", pdf_bytes, 'application/pdf'),
        )
    except Exception:
        # logger.exception garde la trace complète (PDF ou SMTP)
        logger.exception("Bon %s : échec de l'envoi email/PDF.", bon.numero)
        return False

    logger.info("Bon %s : email + PDF envoyé à %d destinataire(s) : %s",
                bon.numero, len(destinataires), ", ".join(destinataires))
    return True


# ─── Email de test ───────────────────────────────────────────────────────
def envoyer_email_test(email_test=None):
    """
    Envoie un email de test à tous les destinataires actifs, ou à email_test.
    Retourne (succès, message).
    """
    if email_test:
        destinataires, _vus = [], set()
        _ajouter_email(destinataires, _vus, email_test)
    else:
        destinataires = get_destinataires_actifs()

    if not destinataires:
        return False, "Aucun destinataire actif configuré."

    sujet = "[Garage] ✅ Test de notification — bon de sortie"
    texte = "\n".join([
        "Ceci est un email de test.",
        "",
        "Si vous recevez cet email, la configuration est correcte.",
        "Vous recevrez un email similaire (avec PDF joint) "
        "à chaque création de bon de sortie.",
        "",
        "— Système Garage Suivi",
    ])

    try:
        _envoyer(sujet, texte, destinataires)
    except Exception as e:
        logger.exception("Échec de l'email de test.")
        return False, str(e)

    return True, (f"Email de test envoyé à {len(destinataires)} adresse(s) : "
                  f"{', '.join(destinataires)}")
