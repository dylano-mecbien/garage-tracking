import re
from django import template

register = template.Library()


@register.filter
def split_articles(value):
    """
    Découpe un texte d'observations en liste d'articles, en se basant
    sur les séparateurs ';' ou saut de ligne. Filtre les entrées vides
    et les espaces superflus.

    Usage dans un template :
        {{ bon.observations|split_articles }}
    """
    if not value:
        return []
    items = re.split(r'[;\n]+', value)
    return [item.strip() for item in items if item.strip()]