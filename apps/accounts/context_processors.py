"""
Context processors — thème et langue accessibles dans tous les templates
"""


def theme_context(request):
    """Injecte le thème (dark/light) et la langue active dans tous les templates."""
    theme = request.session.get('theme', 'light')
    lang = request.session.get('django_language', request.LANGUAGE_CODE if hasattr(request, 'LANGUAGE_CODE') else 'fr')
    return {
        'current_theme': theme,
        'current_lang': lang,
        'is_dark': theme == 'dark',
    }
