from django import template

register = template.Library()


@register.filter
def attr(obj, name):
    """{{ fiche|attr:name }} → getattr(fiche, name)"""
    if obj is None or not name:
        return None
    return getattr(obj, str(name), None)


@register.filter
def split(value, sep=','):
    """{{ 'a,b,c'|split:',' }} → ['a','b','c']"""
    if value is None:
        return []
    return [x.strip() for x in str(value).split(sep) if x.strip()]


@register.filter
def pneu_profondeur(fiche, code):
    """{{ fiche|pneu_profondeur:code }} → fiche.pneu_<code>_profondeur"""
    if fiche is None or not code:
        return None
    return getattr(fiche, f'pneu_{code}_profondeur', None)