"""
Middleware d'audit automatique
"""
from django.utils.deprecation import MiddlewareMixin


class AuditMiddleware(MiddlewareMixin):
    """Capture IP et user-agent pour les logs d'audit."""

    def process_request(self, request):
        request.audit_ip = self._get_client_ip(request)
        request.audit_ua = request.META.get('HTTP_USER_AGENT', '')[:500]

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
