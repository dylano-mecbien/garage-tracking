# garage/middleware.py
import time
import logging
from django.http import HttpResponse

logger = logging.getLogger(__name__)

class SlowRequestMiddleware:
    """
    Middleware qui enregistre les requêtes prenant plus de 10 secondes.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration = time.time() - start
        if duration > 10:  # seuil de 10 secondes
            logger.warning(
                f"Requête lente : {request.method} {request.path} "
                f"({duration:.2f}s) depuis {request.META.get('REMOTE_ADDR')}"
            )
        return response