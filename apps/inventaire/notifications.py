"""E-mail envoyé à l'administrateur quand la guérite valide l'inventaire."""
import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from django.utils.html import escape

from apps.accounts.models import User
from apps.notifications.models import DestinataireEmail

from . import adapters
from .models import TypeMouvement

log = logging.getLogger(__name__)



def destinataires_admin():
    """
    Emails des Users ADMIN actifs qui figurent aussi
    dans DestinataireEmail (actif=True).
    """
    fixes = getattr(settings, 'INVENTAIRE_EMAILS', None)
    if fixes:
        return sorted({e.strip() for e in fixes if e and e.strip()})

    # 1) Emails des admins actifs
    emails_admin = {
        (e or '').strip().lower()
        for e in User.objects
            .filter(role='ADMIN', is_active=True)
            .exclude(email__isnull=True)
            .exclude(email='')
            .values_list('email', flat=True)
        if e and e.strip()
    }
    if not emails_admin:
        return []

    # 2) Destinataires actifs dont l'email est un admin
    emails_dest = (
        DestinataireEmail.objects
        .filter(actif=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )

    result = {
        e.strip()
        for e in emails_dest
        if e and e.strip().lower() in emails_admin
    }

    return sorted(result)

def envoyer_inventaire_a_valider(inv):
    """Retourne (ok, nb_destinataires, erreur). Un échec n'empêche jamais la validation de l'inventaire."""
    dest = destinataires_admin()
    if not dest:
        return False, 0, "Aucun destinataire administrateur configuré."

    mv = list(inv.mouvements.all())
    entrees = [m for m in mv if m.type == TypeMouvement.ENTREE]
    sorties = [m for m in mv if m.type == TypeMouvement.SORTIE]
    par = inv.soumis_par.get_full_name() if inv.soumis_par else '—'

    lien = ''
    base = getattr(settings, 'SITE_URL', '').rstrip('/')
    if base:
        lien = base + reverse('inventaire_admin_detail', args=[inv.id])

    sujet = (
        f"[Garage] Inventaire du {inv.date:%d/%m/%Y} à valider — "
        f"{len(entrees)} entrée(s), {len(sorties)} sortie(s)"
    )

    # ──────────────────────────────────────────────────────────────
    #  VERSION TEXTE (fallback)
    # ──────────────────────────────────────────────────────────────
    txt = [f"Inventaire du {inv.date:%d/%m/%Y} validé par {par}.", ""]

    for titre, lst, fmt in (
        ("Entrées à faire valider", entrees,
         lambda m: f"{m.matricule} — chauffeur : {m.chauffeur} — motif : {adapters.libelle_motif(m.motif)}"),
        ("Sorties à faire valider (véhicules introuvables)", sorties,
         lambda m: f"{m.matricule}"),
    ):
        txt.append(f"{titre} ({len(lst)})")
        txt += [f"  - {fmt(m)}" for m in lst] or ["  (aucune)"]
        txt.append("")

    if inv.observation:
        txt += ["Observation de la guérite :", inv.observation, ""]

    if lien:
        txt.append(f"Consulter et valider : {lien}")

    # ──────────────────────────────────────────────────────────────
    #  VERSION HTML
    # ──────────────────────────────────────────────────────────────
    html = []
    html.append("<div style='font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1e293b;max-width:640px;'>")

    # Titre
    html.append(
        f"<h2 style='margin:0 0 8px;color:#1e293b;'>"
        f"Inventaire du {inv.date:%d/%m/%Y} à valider</h2>"
    )
    html.append(f"<p style='margin:0 0 16px;'>Validé par <b>{escape(par)}</b>.</p>")

    # Blocs entrées / sorties
    for titre, lst, fmt in (
        ("Entrées à faire valider", entrees,
         lambda m: f"{m.matricule} — chauffeur : {m.chauffeur} — motif : {adapters.libelle_motif(m.motif)}"),
        ("Sorties à faire valider (véhicules introuvables)", sorties,
         lambda m: f"{m.matricule}"),
    ):
        html.append(
            f"<h3 style='margin:14px 0 4px;color:#0f172a;'>{escape(titre)} ({len(lst)})</h3>"
        )
        html.append("<ul style='margin:0;padding-left:20px;'>")
        if lst:
            for m in lst:
                html.append(f"<li>{escape(fmt(m))}</li>")
        else:
            html.append("<li><i>aucune</i></li>")
        html.append("</ul>")

    # Observation
    if inv.observation:
        html.append(
            f"<div style='background:#fef3c7;padding:10px 14px;border-left:4px solid #f59e0b;"
            f"margin:16px 0;border-radius:4px;'>"
            f"<b>Observation de la guérite</b><br>{escape(inv.observation)}</div>"
        )

    # ══════════════════════════════════════════════════════════════
    #  🎯 LE BOUTON (technique "bulletproof button")
    # ══════════════════════════════════════════════════════════════
    if lien:
        html.append(
            "<table role='presentation' cellspacing='0' cellpadding='0' "
            "style='margin:24px auto;'><tr><td align='center'>"
            f"<a href='{escape(lien)}' "
            "style='display:inline-block;"
            "background:#2563a8;"
            "color:#ffffff;"
            "font-family:Arial,Helvetica,sans-serif;"
            "font-size:15px;"
            "font-weight:bold;"
            "text-decoration:none;"
            "padding:14px 32px;"
            "border-radius:8px;"
            "border:2px solid #2563a8;"
            "mso-padding-alt:0;"
            "'>"
            "✅ Consulter et valider l'inventaire"
            "</a>"
            "</td></tr></table>"
        )

        # Lien de secours si le bouton ne s'affiche pas
        html.append(
            f"<p style='font-size:12px;color:#64748b;margin-top:8px;'>"
            f"Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :<br>"
            f"<a href='{escape(lien)}' style='color:#2563a8;word-break:break-all;'>{escape(lien)}</a>"
            f"</p>"
        )

    html.append("</div>")

    # ──────────────────────────────────────────────────────────────
    #  ENVOI
    # ──────────────────────────────────────────────────────────────
    try:
        msg = EmailMultiAlternatives(
            sujet,
            "\n".join(txt),
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            dest,
        )
        msg.attach_alternative("".join(html), "text/html")
        msg.send(fail_silently=False)
        return True, len(dest), ""
    except Exception as exc:
        log.exception("Envoi e-mail inventaire impossible")
        return False, len(dest), str(exc)[:500]