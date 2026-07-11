"""
Service d'envoi d'emails pour les bons de sortie.
Appelé depuis guerite/views.py au moment de la création d'un bon.
"""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
import logging

from apps.notifications.models import DestinataireEmail

logger = logging.getLogger(__name__)


def get_destinataires_actifs():
    """Retourne la liste des emails actifs."""
    
    return list(
        DestinataireEmail.objects
        .filter(actif=True)
        .values_list('email', flat=True)
    )


def envoyer_notification_bon_sortie(bon):
    """
    Envoie un email de notification à tous les destinataires actifs
    lorsqu'un bon de sortie est créé.
    """
    destinataires = get_destinataires_actifs()
    if not destinataires:
        logger.info("Aucun destinataire actif — email bon de sortie non envoyé.")
        return False

    # Infos véhicule
    
    objet_str = f"{bon.observations or 'Non précisé'}"

    sujet = f"[Garage] Bon de sortie {bon.numero} — validation requise"

    # Corps HTML
    html_message = _build_email_html(bon, objet_str)

    # Corps texte (fallback)
    texte = (
        f"Bonjour,\n\n"
        f"Un nouveau bon de sortie vient d'être créé et nécessite votre validation.\n\n"
        f"N° Bon   : {bon.numero}\n"
        f"Type     : {'Divers'}\n"
        f"Objet    : {objet_str}\n"
        f"Demandeur: {bon.nom_demandeur or '—'}\n"
        f"Créé par : {bon.cree_par.full_name if bon.cree_par else '—'}\n\n"
        f"Merci de valider ce bon.\n\n"
        f"— Système Garage Suivi (message automatique)"
    )

    try:
        send_mail(
            subject=sujet,
            message=texte,
            html_message=html_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@garage.cm'),
            recipient_list=destinataires,
            fail_silently=False,
        )
        logger.info(f"Email bon {bon.numero} envoyé à {len(destinataires)} destinataire(s): {destinataires}")
        return True
    except Exception as e:
        logger.error(f"Erreur envoi email bon {bon.numero}: {e}")
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
        "Vous recevrez un email similaire à chaque création de bon de sortie.\n\n"
        "— Système Garage Suivi"
    )
    html = _build_email_html_test()

    try:
        send_mail(
            subject=sujet,
            message=texte,
            html_message=html,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@garage.cm'),
            recipient_list=destinataires,
            fail_silently=False,
        )
        return True, f"Email de test envoyé à {len(destinataires)} adresse(s) : {', '.join(destinataires)}"
    except Exception as e:
        return False, str(e)


def _build_email_html(bon, objet_str):
    """Génère le corps HTML de l'email de notification."""
    type_label =  "📦 Divers"
    couleur    = "#7c3aed"

    cree_par   = bon.cree_par.full_name if bon.cree_par else "—"
    from django.utils import timezone
    date_str   = timezone.now().strftime("%d/%m/%Y à %H:%M")

    return f"""
<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 0;">
  <tr><td align="center">
  <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);">

    <!-- Header -->
    <tr><td style="background:{couleur};padding:24px 32px;">
      <div style="color:#fff;font-size:22px;font-weight:800;">🚗 Garage Suivi</div>
      <div style="color:rgba(255,255,255,.8);font-size:13px;margin-top:4px;">Notification — Bon de sortie</div>
    </td></tr>

    <!-- Body -->
    <tr><td style="padding:28px 32px;">
      <p style="margin:0 0 8px;font-size:15px;color:#1e293b;">Bonjour,</p>
      <p style="margin:0 0 20px;font-size:14px;color:#475569;line-height:1.6;">
        Un nouveau <strong>bon de sortie</strong> vient d'être créé et nécessite votre validation.
        
      </p>

      <!-- Recap -->
      <table width="100%" cellpadding="12" cellspacing="0"
             style="background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;font-size:13px;margin-bottom:24px;">
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="color:#64748b;font-weight:600;width:40%;">N° Bon</td>
          <td style="color:#0f172a;font-weight:800;font-size:15px;">{bon.numero}</td>
        </tr>
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="color:#64748b;font-weight:600;">Type</td>
          <td><span style="background:{couleur}15;color:{couleur};padding:3px 10px;border-radius:20px;font-weight:700;">{type_label}</span></td>
        </tr>
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="color:#64748b;font-weight:600;">Objet</td>
          <td style="color:#0f172a;font-weight:600;">{objet_str}</td>
        </tr>
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="color:#64748b;font-weight:600;">Demandeur</td>
          <td style="color:#0f172a;">{bon.nom_demandeur or '—'}</td>
        </tr>
        {'<tr style="border-bottom:1px solid #e2e8f0;"><td style="color:#64748b;font-weight:600;">Origine</td><td style="color:#0f172a;">' + (bon.Origine_demande or '—') + '</td></tr>' if bon.Origine_demande else ''}
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="color:#64748b;font-weight:600;">Créé par</td>
          <td style="color:#0f172a;">{cree_par}</td>
        </tr>
        <tr>
          <td style="color:#64748b;font-weight:600;">Date</td>
          <td style="color:#0f172a;">{date_str}</td>
        </tr>
      </table>

      <!-- CTA -->
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr><td align="center" style="padding:8px 0 24px;">
          <div style="background:{couleur};color:#fff;padding:14px 32px;border-radius:8px;font-size:15px;font-weight:700;display:inline-block;">
            📋 Accepter la sortie
          </div>
        </td></tr>
      </table>

      <p style="font-size:12px;color:#94a3b8;margin:0;">
        Ce message est généré automatiquement par le système Garage Suivi. Merci de ne pas y répondre.
      </p>
    </td></tr>

    <!-- Footer -->
    <tr><td style="background:#f8fafc;padding:16px 32px;border-top:1px solid #e2e8f0;text-align:center;">
      <span style="color:#94a3b8;font-size:12px;">© Garage Suivi — Système de gestion de garage</span>
    </td></tr>

  </table>
  </td></tr>
</table>
</body>
</html>
"""


def _build_email_html_test():
    return """
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f1f5f9;padding:32px;">
<div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08);">
  <div style="background:#059669;padding:20px 28px;color:#fff;font-size:20px;font-weight:800;">✅ Test de notification</div>
  <div style="padding:24px 28px;">
    <p style="font-size:14px;color:#374151;">Bonjour,</p>
    <p style="font-size:14px;color:#374151;">Cet email confirme que votre adresse est correctement configurée dans le système <strong>Garage Suivi</strong>.</p>
    <p style="font-size:14px;color:#374151;">Vous recevrez un email similaire à chaque création de bon de sortie.</p>
    <p style="font-size:12px;color:#9ca3af;margin-top:24px;">— Système Garage Suivi (message automatique)</p>
  </div>
</div>
</body></html>
"""