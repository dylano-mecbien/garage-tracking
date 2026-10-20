from django import template

register = template.Library()


@register.filter
def duree(minutes):
    """90 → « 1 h 30 » ; 45 → « 45 min » ; None / 0 → « — »."""
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return '—'
    if m <= 0:
        return '—'
    h, r = divmod(m, 60)
    if h and r:
        return f"{h} h {r:02d}"
    return f"{h} h" if h else f"{r} min"
