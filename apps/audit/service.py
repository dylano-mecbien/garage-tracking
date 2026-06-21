"""
Service Audit - Logging centralisé
"""
from .models import AuditLog, ActionType


def log_action(request, action, module, objet=None, details=None):
    """Enregistre une action dans les logs d'audit."""
    user = request.user if request.user.is_authenticated else None
    ip = getattr(request, 'audit_ip', None)
    ua = getattr(request, 'audit_ua', '')

    objet_type = ''
    objet_id = ''
    objet_repr = ''
    if objet:
        objet_type = objet.__class__.__name__
        objet_id = str(objet.pk) if objet.pk else ''
        objet_repr = str(objet)[:200]

    AuditLog.objects.create(
        user=user,
        action=action,
        module=module,
        objet_type=objet_type,
        objet_id=objet_id,
        objet_repr=objet_repr,
        details=details,
        ip_address=ip,
        user_agent=ua,
    )
