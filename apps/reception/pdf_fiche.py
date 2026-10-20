"""
Générateur PDF - Fiches atelier
  - FicheTechnique  -> « FICHE DE DIAGNOSTIC MÉCANIQUE »
  - FicheControle   -> « FICHE ENTRÉE - SORTIE ATELIER »

Même charte que pdf_generator (COULEUR_PRIMAIRE / ACCENT ...).
Les signatures sont des TextField en base64 (avec ou sans préfixe data:image/...).
"""
import base64
import json
import logging
from html import escape
from io import BytesIO

from django.utils import timezone
from reportlab.graphics.shapes import (
    Drawing, Rect, Circle, Line, String, PolyLine, Polygon, Wedge, Ellipse,
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
    Flowable, KeepTogether,
)

# Si tu as déjà ces constantes dans pdf_generator.py, tu peux les importer :
# from .pdf_generator import COULEUR_PRIMAIRE, COULEUR_ACCENT, COULEUR_GRIS, COULEUR_TEXTE
COULEUR_PRIMAIRE = colors.HexColor('#1a3a5c')
COULEUR_ACCENT = colors.HexColor('#e67e22')
COULEUR_GRIS = colors.HexColor('#f5f5f5')
COULEUR_TEXTE = colors.HexColor('#2c3e50')
COULEUR_ENTETE = colors.HexColor('#e3e9f0')
COULEUR_BORD = colors.HexColor('#9aa7b4')
COULEUR_VIDE = colors.HexColor('#b8c2cc')
COULEUR_OK = colors.HexColor('#16a34a')
COULEUR_KO = colors.HexColor('#dc2626')

# Logo optionnel (chemin absolu vers un PNG/JPG). Si absent -> logo dessiné.
LOGO_PATH = None
# Images optionnelles du schéma carrosserie par type de véhicule
# ex: {'VOITURE': '/chemin/static/img/schema_voiture.png', ...}
# Les points de dégâts sont placés en % (ou fraction 0-1) de cette image.
SCHEMA_IMAGES = {}

PAGE_W, PAGE_H = A4
MARGE = 10 * mm
LARGEUR = PAGE_W - 2 * MARGE  # 190 mm

SERVICES = ("Tôlerie – Peinture – Freinage – Chaudronnerie – Mécanique Générale<br/>"
            "Électricité – Climatisation – Pneumatique – Tapisserie – Sérigraphie")
ADRESSE = "BP : 9060 Douala – Tél : (+237) 650 99 75 09"


# ════════════════════════════════════════════════════════════════
#  Utilitaires de valeurs
# ════════════════════════════════════════════════════════════════
def _get(obj, attr, default=None):
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _display(obj, champ):
    """Libellé d'un champ à choices (get_FOO_display) sinon valeur brute."""
    fn = _get(obj, f'get_{champ}_display')
    val = _get(obj, champ)
    if val in (None, ''):
        return ''
    if callable(fn):
        try:
            return str(fn())
        except Exception:
            pass
    return str(val)


def _etat(v):
    """Normalise une valeur Bon/Défaut -> 'ok' | 'ko' | None.
    Accepte 'BON'/'DEFAUT', 'B'/'D', 'OK'/'KO', True/False."""
    if v in (None, ''):
        return None
    if isinstance(v, bool):
        return 'ok' if v else 'ko'
    s = str(v).strip().upper()
    if s in ('BON', 'B', 'OK', 'OUI', 'TRUE', '1', 'INTACT', 'BONNE'):
        return 'ok'
    if s in ('DEFAUT', 'DÉFAUT', 'D', 'KO', 'NON', 'FALSE', '0',
             'FISSURE', 'CASSE', 'MAUVAIS'):
        return 'ko'
    if s.startswith('B'):
        return 'ok'
    if s.startswith('D'):
        return 'ko'
    return None


def _bool(v):
    """Oui / Non → True / False / None. Accepte les booléens et les champs on() ('OUI' / 'NON')."""
    if v is None or v == '':
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().upper()
    if s in ('OUI', 'TRUE', '1', 'O'):
        return True
    if s in ('NON', 'FALSE', '0', 'N'):
        return False
    return None


def _oui_non(v):
    b = _bool(v)
    if b is None:
        return ''
    return 'Oui' if b else 'Non'


def _date(d):
    if not d:
        return ''
    try:
        if hasattr(d, 'hour') and timezone.is_aware(d):
            d = timezone.localtime(d)
        return d.strftime('%d/%m/%Y')
    except Exception:
        return str(d)


def _num(v, suffixe='', decimales=None):
    if v in (None, ''):
        return ''
    try:
        if decimales is not None:
            txt = f"{float(v):,.{decimales}f}".replace(',', ' ').replace('.', ',')
        else:
            f = float(v)
            txt = (f"{int(f):,}" if f == int(f) else f"{f:,.1f}").replace(',', ' ')
            txt = txt.replace('.', ',') if '.' in txt else txt
        return f"{txt}{suffixe}"
    except (TypeError, ValueError):
        return f"{v}{suffixe}"


def _txt(v):
    """Texte utilisateur sûr pour Paragraph (échappement + retours ligne)."""
    if v in (None, ''):
        return ''
    return escape(str(v)).replace('\n', '<br/>')


# Correspondance des choix JAUGE / NIVEAU_HUILE -> fraction (0..1).
# ⚠️ Adapte les clés à tes constantes JAUGE et NIVEAU_HUILE si besoin.
FRACTIONS_JAUGE = {
    'VIDE': 0, 'E': 0, 'RESERVE': 0.06, 'RÉSERVE': 0.06,
    '1/8': 0.125, '1_8': 0.125,
    '1/4': 0.25, '1_4': 0.25, 'QUART': 0.25, 'UN_QUART': 0.25,
    '3/8': 0.375,
    '1/2': 0.5, '1_2': 0.5, 'MOITIE': 0.5, 'MOITIÉ': 0.5, 'DEMI': 0.5,
    '5/8': 0.625,
    '3/4': 0.75, '3_4': 0.75, 'TROIS_QUARTS': 0.75,
    '7/8': 0.875,
    'PLEIN': 1, 'F': 1, 'FULL': 1,
}
FRACTIONS_HUILE = {
    'SOUS_MINI': 0, 'INSUFFISANT': 0, 'BAS': 0.05, 'MINI': 0.05, 'MIN': 0.05,
    'MOYEN': 0.5, 'MILIEU': 0.5, 'NORMAL': 0.5, 'MOITIE': 0.5, 'OK': 0.5,
    'MAXI': 0.95, 'MAX': 0.95, 'HAUT': 0.95, 'PLEIN': 0.95,
    'SUR_MAXI': 1, 'TROP': 1, 'EXCES': 1,
}


def _fraction(v, table):
    if v in (None, ''):
        return None
    s = str(v).strip().upper()
    if s in table:
        return table[s]
    try:
        if '/' in s:
            a, b = s.split('/', 1)
            return max(0, min(1, float(a) / float(b)))
        f = float(s.replace('%', ''))
        return max(0, min(1, f / 100 if f > 1 else f))
    except (ValueError, ZeroDivisionError):
        return None


# ════════════════════════════════════════════════════════════════
#  Styles & briques de base
# ════════════════════════════════════════════════════════════════
def _style(size=6.5, bold=False, align=TA_LEFT, color=COULEUR_TEXTE, leading=None):
    return ParagraphStyle(
        '', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size,
        leading=leading or size * 1.18, alignment=align, textColor=color,
    )


def P(texte, size=6.5, bold=False, align=TA_LEFT, color=COULEUR_TEXTE):
    return Paragraph(texte or '', _style(size, bold, align, color))


def PC(texte, size=6.5, bold=True, color=COULEUR_PRIMAIRE):
    return P(texte, size, bold, TA_CENTER, color)


class Coche(Flowable):
    """Pastille : 'ok' (✔ vert), 'ko' (✘ rouge) ou None (cercle vide)."""

    def __init__(self, etat=None, taille=3.3 * mm):
        Flowable.__init__(self)
        self.etat, self.taille = etat, taille

    def wrap(self, *a):
        return self.taille, self.taille

    def draw(self):
        c, t = self.canv, self.taille
        r = t / 2
        if self.etat is None:
            c.setStrokeColor(COULEUR_VIDE)
            c.setLineWidth(0.6)
            c.circle(r, r, r * 0.78, stroke=1, fill=0)
            return
        coul = COULEUR_OK if self.etat == 'ok' else COULEUR_KO
        c.setFillColor(coul)
        c.setStrokeColor(coul)
        c.circle(r, r, r, stroke=0, fill=1)
        c.setStrokeColor(colors.white)
        c.setLineWidth(1.1)
        c.setLineCap(1)
        if self.etat == 'ok':
            p = c.beginPath()
            p.moveTo(t * 0.26, t * 0.52)
            p.lineTo(t * 0.43, t * 0.33)
            p.lineTo(t * 0.75, t * 0.70)
            c.drawPath(p, stroke=1, fill=0)
        else:
            d = t * 0.28
            c.line(d, d, t - d, t - d)
            c.line(d, t - d, t - d, d)


def _bd(v):
    """2 cellules [Bon, Défaut] pour une valeur bd()."""
    e = _etat(v)
    return [Coche('ok' if e == 'ok' else None), Coche('ko' if e == 'ko' else None)]


def _roue(v):
    """1 cellule par roue : ✔ / ✘ / vide."""
    return Coche(_etat(v))


def _grille(data, col_widths, entetes=1, extra=None, fond_entete=True):
    t = Table(data, colWidths=col_widths)
    cmds = [
        ('GRID', (0, 0), (-1, -1), 0.4, COULEUR_BORD),
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]
    if entetes and fond_entete:
        cmds.append(('BACKGROUND', (0, 0), (-1, entetes - 1), COULEUR_ENTETE))
    if extra:
        cmds.extend(extra)
    t.setStyle(TableStyle(cmds))
    return t


def _bandeau(texte, largeur=LARGEUR, size=10):
    """Bandeau de section foncé (VEHICULE AU SOL, ...)."""
    t = Table([[PC(texte, size, True, colors.white)]], colWidths=[largeur])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, COULEUR_ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _colonnes(cols, largeurs, gap=2 * mm, valign='TOP'):
    """Place plusieurs blocs (listes de flowables) côte à côte."""
    t = Table([cols], colWidths=largeurs)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), valign),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), gap),
        ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _champs(rows, largeurs, size=7.5):
    """Lignes « Libellé : ........ valeur » façon formulaire papier."""
    data = [[P(f"{lib} :", size, True), P(_txt(val), size + 0.5, False, color=colors.HexColor('#0b3d91'))]
            for lib, val in rows]
    t = Table(data, colWidths=largeurs)
    t.setStyle(TableStyle([
        ('LINEBELOW', (1, 0), (1, -1), 0.5, COULEUR_BORD, None, (1, 1.5)),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.2),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


# ════════════════════════════════════════════════════════════════
#  En-tête (logo + services + titre + N°)
# ════════════════════════════════════════════════════════════════
def _logo(largeur=62 * mm, hauteur=21 * mm):
    if LOGO_PATH:
        try:
            ir = ImageReader(LOGO_PATH)
            iw, ih = ir.getSize()
            k = min(largeur / iw, hauteur / ih)
            return Image(LOGO_PATH, width=iw * k, height=ih * k)
        except Exception as e:
            logging.warning("Logo introuvable (%s) : %s", LOGO_PATH, e)
    d = Drawing(largeur, hauteur)
    d.add(String(largeur / 2, hauteur - 6.5 * mm, "CENTRE AUTO", fontName='Helvetica-Bold',
                 fontSize=11, fillColor=COULEUR_PRIMAIRE, textAnchor='middle'))
    d.add(Ellipse(largeur / 2, hauteur / 2 - 3.2 * mm, largeur / 2 - 1, 6.4 * mm,
                  fillColor=COULEUR_PRIMAIRE, strokeColor=COULEUR_ACCENT, strokeWidth=1.2))
    d.add(String(largeur / 2, hauteur / 2 - 2.6 * mm, "La PRUDENCE+", fontName='Helvetica-Bold',
                 fontSize=14, fillColor=colors.white, textAnchor='middle'))
    d.add(String(largeur / 2, hauteur / 2 - 6.6 * mm, "Véhicules Légers / Poids Lourds",
                 fontName='Helvetica-Oblique', fontSize=6.5, fillColor=colors.white,
                 textAnchor='middle'))
    return d


def _entete(titre, numero, date_creation=None):
    haut = Table([[
        _logo(),
        P(f"<b>{SERVICES}</b><br/><font color='#e67e22'><b>{ADRESSE}</b></font>",
          8.3, False, TA_CENTER, COULEUR_PRIMAIRE),
    ]], colWidths=[66 * mm, LARGEUR - 66 * mm])
    haut.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    titre_t = Table([[P(f"<b>{titre}</b>", 12.5, True, TA_LEFT, colors.white)]],
                    colWidths=[110 * mm])
    titre_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, -1), 2, COULEUR_ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROUNDEDCORNERS', [4, 4, 0, 0]),
    ]))
    num_cell = [P(f"<font size=9 color='#2c3e50'><b>N°</b></font>&nbsp;&nbsp;"
                  f"<font color='#c0392b'><b>{escape(str(numero or ''))}</b></font>",
                  15, False, TA_CENTER)]
    if date_creation:
        num_cell.append(P(f"Créée le {_date(date_creation)}", 6.5, False, TA_CENTER, colors.HexColor('#6b7280')))
    num_t = Table([[num_cell]], colWidths=[62 * mm])
    num_t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, COULEUR_PRIMAIRE),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    bas = Table([[titre_t, '', num_t]], colWidths=[110 * mm, LARGEUR - 172 * mm, 62 * mm])
    bas.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return [haut, Spacer(1, 2.5 * mm), bas, Spacer(1, 2.5 * mm)]


def _pied_de_page(titre):
    def _draw(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(colors.HexColor('#6b7280'))
        maintenant = timezone.now()
        if timezone.is_aware(maintenant):
            maintenant = timezone.localtime(maintenant)
        canvas.drawString(MARGE, 6 * mm, f"{titre} – imprimée le {maintenant.strftime('%d/%m/%Y %H:%M')}")
        canvas.drawRightString(PAGE_W - MARGE, 6 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return _draw


# ════════════════════════════════════════════════════════════════
#  Dessins : légende, jauge carburant, niveau d'huile, schéma
# ════════════════════════════════════════════════════════════════
SYMBOLES_DEGATS = [('PIQURE', 'Piqûre'), ('RAYURE', 'Rayures'),
                   ('BOSSE', 'Bosses'), ('CASSE', 'Casses')]


def _symbole(d, type_, x, y, s=2.2 * mm, couleur=COULEUR_KO):
    t = (type_ or '').upper()
    if t.startswith('PIQ'):
        d.add(Line(x - s / 2, y - s / 2, x + s / 2, y + s / 2, strokeColor=couleur, strokeWidth=1.2))
        d.add(Line(x - s / 2, y + s / 2, x + s / 2, y - s / 2, strokeColor=couleur, strokeWidth=1.2))
    elif t.startswith('RAY'):
        for dy in (-s * 0.25, s * 0.25):
            d.add(PolyLine([x - s / 2, y + dy, x - s / 6, y + dy + s / 4, x + s / 6, y + dy - s / 4,
                            x + s / 2, y + dy], strokeColor=couleur, strokeWidth=0.9))
    elif t.startswith('BOS'):
        d.add(Circle(x, y, s / 2, strokeColor=couleur, strokeWidth=1.2, fillColor=None))
    else:  # CASSE
        for dx in (-s / 3, 0, s / 3):
            d.add(Line(x + dx - s / 5, y - s / 2, x + dx + s / 5, y + s / 2,
                       strokeColor=couleur, strokeWidth=1))


def _legende(largeur=40 * mm):
    rows = [[PC("LÉGENDE", 7, True, colors.white)]]
    for code, lib in SYMBOLES_DEGATS:
        d = Drawing(4 * mm, 3 * mm)
        _symbole(d, code, 2 * mm, 1.5 * mm, 2.4 * mm, COULEUR_PRIMAIRE)
        mini = Table([[d, P(f"<b>{lib}</b>", 7)]], colWidths=[6 * mm, largeur - 10 * mm])
        mini.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                  ('TOPPADDING', (0, 0), (-1, -1), 0.5),
                                  ('BOTTOMPADDING', (0, 0), (-1, -1), 0.5)]))
        rows.append([mini])
    t = Table(rows, colWidths=[largeur])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.2), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _jauge_carburant(valeur, libelle='', largeur=34 * mm, hauteur=21 * mm):
    """Cadran demi-cercle E ¼ ½ ¾ F avec aiguille."""
    import math
    d = Drawing(largeur, hauteur)
    cx, cy, r = largeur / 2, 5.5 * mm, min(largeur / 2 - 2 * mm, hauteur - 7.5 * mm)
    d.add(Wedge(cx, cy, r, 0, 180, fillColor=colors.white, strokeColor=COULEUR_PRIMAIRE, strokeWidth=1.2))
    d.add(Wedge(cx, cy, r, 157, 180, fillColor=colors.HexColor('#fde2e2'), strokeColor=None))
    for i, lab in enumerate(['E', '¼', '½', '¾', 'F']):
        a = math.radians(180 - i * 45)
        x1, y1 = cx + r * math.cos(a), cy + r * math.sin(a)
        x2, y2 = cx + (r - 2 * mm) * math.cos(a), cy + (r - 2 * mm) * math.sin(a)
        d.add(Line(x1, y1, x2, y2, strokeColor=COULEUR_PRIMAIRE, strokeWidth=1))
        xl, yl = cx + (r - 4 * mm) * math.cos(a), cy + (r - 4 * mm) * math.sin(a) - 1
        d.add(String(xl, yl, lab, fontName='Helvetica-Bold', fontSize=6,
                     fillColor=COULEUR_KO if lab == 'E' else COULEUR_PRIMAIRE, textAnchor='middle'))
    f = _fraction(valeur, FRACTIONS_JAUGE)
    if f is not None:
        a = math.radians(180 - f * 180)
        d.add(Line(cx, cy, cx + (r - 1.5 * mm) * math.cos(a), cy + (r - 1.5 * mm) * math.sin(a),
                   strokeColor=COULEUR_ACCENT, strokeWidth=1.8))
    d.add(Circle(cx, cy, 1.1 * mm, fillColor=COULEUR_PRIMAIRE, strokeColor=None))
    txt = libelle or (str(valeur) if valeur else 'Non renseignée')
    d.add(String(cx, 0.6 * mm, txt, fontName='Helvetica-Bold', fontSize=6.5,
                 fillColor=COULEUR_TEXTE, textAnchor='middle'))
    return d


def _niveau_huile(valeur, libelle='', largeur=60 * mm, hauteur=12.5 * mm):
    """Réglette Mini ---- Maxi avec repère."""
    d = Drawing(largeur, hauteur)
    x0, x1, y = 6 * mm, largeur - 6 * mm, 4.8 * mm
    d.add(Line(x0 - 3 * mm, y, x1 + 3 * mm, y, strokeColor=COULEUR_PRIMAIRE, strokeWidth=1))
    for x in (x0, (x0 + x1) / 2, x1):
        d.add(Line(x, y - 1.5 * mm, x, y + 1.5 * mm, strokeColor=COULEUR_PRIMAIRE, strokeWidth=1))
    d.add(String(x0, 0.6 * mm, "Mini", fontName='Helvetica', fontSize=6, textAnchor='middle',
                 fillColor=COULEUR_TEXTE))
    d.add(String(x1, 0.6 * mm, "Maxi", fontName='Helvetica', fontSize=6, textAnchor='middle',
                 fillColor=COULEUR_TEXTE))
    f = _fraction(valeur, FRACTIONS_HUILE)
    if f is not None:
        xm = x0 - 2 * mm + f * (x1 - x0 + 4 * mm)
        d.add(Polygon([xm, y + 0.3 * mm, xm - 1.6 * mm, y + 3.2 * mm, xm + 1.6 * mm, y + 3.2 * mm],
                      fillColor=COULEUR_ACCENT, strokeColor=None))
    texte = libelle or (str(valeur) if valeur else 'Non renseigné')
    d.add(String((x0 + x1) / 2, hauteur - 2.6 * mm, texte, fontName='Helvetica-Bold',
                 fontSize=6.5, textAnchor='middle', fillColor=COULEUR_ACCENT if valeur else COULEUR_VIDE))
    return d


def _contour_vehicule(d, x, y, w, h, type_vehicule):
    """Silhouette vue de dessus générique (avant à gauche)."""
    trait = dict(strokeColor=COULEUR_PRIMAIRE, strokeWidth=0.9, fillColor=None)
    roue = dict(fillColor=colors.HexColor('#cfd8e3'), strokeColor=COULEUR_PRIMAIRE, strokeWidth=0.6)
    t = (type_vehicule or 'VOITURE').upper()
    rw, rh = w * 0.13, h * 0.12
    for rx in (x + w * 0.14, x + w * 0.72):
        d.add(Rect(rx, y - rh * 0.55, rw, rh, rx=1, ry=1, **roue))
        d.add(Rect(rx, y + h - rh * 0.45, rw, rh, rx=1, ry=1, **roue))
    if t in ('CAMION_CITERNE', 'BENNE'):
        d.add(Rect(x, y, w * 0.24, h, rx=3, ry=3, **trait))                       # cabine
        d.add(Rect(x + w * 0.27, y + h * 0.04, w * 0.73, h * 0.92, rx=4 if t == 'CAMION_CITERNE' else 1,
                   ry=4 if t == 'CAMION_CITERNE' else 1, **trait))
        d.add(Rect(x + w * 0.84, y - rh * 0.55, rw, rh, rx=1, ry=1, **roue))
        d.add(Rect(x + w * 0.84, y + h - rh * 0.45, rw, rh, rx=1, ry=1, **roue))
    elif t == 'PICKUP':
        d.add(Rect(x, y, w, h, rx=6, ry=6, **trait))
        d.add(Rect(x + w * 0.22, y + h * 0.12, w * 0.32, h * 0.76, rx=3, ry=3, **trait))   # cabine
        d.add(Rect(x + w * 0.58, y + h * 0.1, w * 0.38, h * 0.8, rx=1, ry=1, **trait))     # benne
    elif t == 'FOURGON':
        d.add(Rect(x, y, w, h, rx=5, ry=5, **trait))
        d.add(Rect(x + w * 0.12, y + h * 0.12, w * 0.14, h * 0.76, rx=2, ry=2, **trait))
        d.add(Line(x + w * 0.3, y + h * 0.05, x + w * 0.3, y + h * 0.95, **trait))
    else:  # VOITURE
        d.add(Rect(x, y, w, h, rx=h * 0.3, ry=h * 0.3, **trait))
        d.add(Rect(x + w * 0.3, y + h * 0.13, w * 0.42, h * 0.74, rx=5, ry=5, **trait))  # habitacle
        d.add(Line(x + w * 0.3, y + h * 0.13, x + w * 0.22, y + h * 0.2, **trait))
        d.add(Line(x + w * 0.3, y + h * 0.87, x + w * 0.22, y + h * 0.8, **trait))
    d.add(String(x - 1.2 * mm, y + h / 2 - 2, "AV", fontName='Helvetica-Bold', fontSize=6,
                 fillColor=COULEUR_ACCENT, textAnchor='end'))
    d.add(String(x + w + 1.2 * mm, y + h / 2 - 2, "AR", fontName='Helvetica-Bold', fontSize=6,
                 fillColor=COULEUR_ACCENT, textAnchor='start'))


# Le schéma de la saisie est un canvas de 600 x 280 px : les points y sont enregistrés en pixels.
CANVAS_W, CANVAS_H = 600, 280
COULEURS_DEGATS = {k: colors.HexColor(v) for k, v in
                   {'PIQURE': '#6366f1', 'RAYURE': '#f59e0b', 'BOSSE': '#3b82f6', 'CASSE': '#ef4444'}.items()}


def _dessin_canvas(d, largeur, hauteur):
    """Même dessin que le canvas de saisie (drawCar), pour que les marques tombent au même endroit."""
    kx, ky = largeur / CANVAS_W, hauteur / CANVAS_H

    def rect(x, y, w, h, r, **kw):
        d.add(Rect(x * kx, hauteur - (y + h) * ky, w * kx, h * ky, rx=r * kx, ry=r * ky, **kw))

    rect(60, 25, 480, 225, 20, fillColor=colors.HexColor('#eef2f6'), strokeColor=colors.HexColor('#94a3b8'),
         strokeWidth=0.8)
    rect(140, 70, 320, 130, 12, fillColor=colors.HexColor('#e2e8f0'), strokeColor=colors.HexColor('#94a3b8'),
         strokeWidth=0.8)
    for x, y in ((55, 45), (55, 185), (505, 45), (505, 185)):
        rect(x, y, 20, 50, 5, fillColor=colors.HexColor('#475569'), strokeColor=None)
    gris = colors.HexColor('#64748b')
    d.add(String(largeur / 2, hauteur - 16 * ky, "AVANT", fontName='Helvetica', fontSize=5.5,
                 fillColor=gris, textAnchor='middle'))
    d.add(String(largeur / 2, (CANVAS_H - 274) * ky, "ARRIÈRE", fontName='Helvetica', fontSize=5.5,
                 fillColor=gris, textAnchor='middle'))


def _schema_carrosserie(fiche, largeur, hauteur=None):
    """Schéma + points de dégâts saisis sur le canvas (pixels 600 x 280, origine en haut à gauche)."""
    hauteur = hauteur or largeur * CANVAS_H / CANVAS_W
    points = _get(fiche, 'points_degats_carrosserie') or []
    if isinstance(points, str):
        try:
            points = json.loads(points)
        except ValueError:
            points = []

    d = Drawing(largeur, hauteur)
    d.add(Rect(0, 0, largeur, hauteur, fillColor=colors.white, strokeColor=COULEUR_BORD, strokeWidth=0.5))
    _dessin_canvas(d, largeur, hauteur)

    pts = [p for p in points if isinstance(p, dict) and p.get('x') is not None and p.get('y') is not None]
    # Anciennes données éventuelles en fractions (0-1) ; sinon pixels du canvas.
    fraction = bool(pts) and all(float(p['x']) <= 1 and float(p['y']) <= 1 for p in pts)
    ex, ey = (1, 1) if fraction else (CANVAS_W, CANVAS_H)
    for p in pts:
        try:
            px = float(p['x']) / ex * largeur
            py = hauteur - float(p['y']) / ey * hauteur
            t = str(p.get('type') or '').upper()
            _symbole(d, t, px, py, couleur=COULEURS_DEGATS.get(t, COULEUR_KO))
        except (TypeError, ValueError):
            continue
    lib_type = _display(fiche, 'type_vehicule') or 'Véhicule'
    d.add(String(2 * mm, hauteur - 3.5 * mm, lib_type, fontName='Helvetica-Bold', fontSize=6.5,
                 fillColor=COULEUR_PRIMAIRE))
    d.add(String(largeur - 2 * mm, 1.6 * mm, f"{len(pts)} dégât(s) relevé(s)", fontName='Helvetica',
                 fontSize=6, fillColor=COULEUR_TEXTE, textAnchor='end'))
    return [d]


# ════════════════════════════════════════════════════════════════
#  Signatures (base64)
# ════════════════════════════════════════════════════════════════
def _signature_brute(data):
    """Octets de l'image : dataURL / base64, ou chemin enregistré dans le storage (local ou MinIO)."""
    s = str(data).strip()
    if s.startswith('data:'):
        s = s.split(',', 1)[1]
    elif '/' in s or s.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        from django.core.files.storage import default_storage
        with default_storage.open(s, 'rb') as fh:
            return fh.read()
    s = ''.join(s.split())
    return base64.b64decode(s + '=' * (-len(s) % 4))


def _rogner_signature(raw):
    """Coupe les marges vides du canvas : le trait remplit ensuite la case au lieu d'y être minuscule."""
    from PIL import Image as PILImage, ImageChops
    im = PILImage.open(BytesIO(raw)).convert('RGBA')
    fond = PILImage.new('RGBA', im.size, (255, 255, 255, 255))
    fond.alpha_composite(im)                                  # transparent -> blanc
    gris = fond.convert('L')
    boite = ImageChops.invert(gris).point(lambda v: 255 if v > 40 else 0).getbbox()
    if boite:
        m = 6
        boite = (max(boite[0] - m, 0), max(boite[1] - m, 0),
                 min(boite[2] + m, im.width), min(boite[3] + m, im.height))
        fond = fond.crop(boite)
    out = BytesIO()
    fond.convert('RGB').save(out, 'PNG')
    return out.getvalue()


def _signature_b64(data, max_w=50 * mm, max_h=16 * mm):
    if not data:
        return None
    try:
        raw = _signature_brute(data)
        if not raw:
            return None
        try:
            raw = _rogner_signature(raw)
        except Exception as e:
            logging.warning("Signature non rognée : %s", e)
        iw, ih = ImageReader(BytesIO(raw)).getSize()
        k = min(max_w / iw, max_h / ih, 0.3 * mm)   # pas plus de 0,3 mm par pixel : évite l'effet escalier
        return Image(BytesIO(raw), width=iw * k, height=ih * k)
    except Exception as e:
        logging.warning("Signature illisible (%s) : %s", str(data)[:60], e)
        return None


def _case_signature(titre, nom, signature_b64, largeur, hauteur=22 * mm):
    """Titre en haut, signature centrée au milieu, nom en bas : même position dans toutes les cases."""
    h_titre, h_nom = 4.5 * mm, 4 * mm
    h_sig = hauteur - h_titre - h_nom
    img = _signature_b64(signature_b64, largeur - 6 * mm, h_sig - 1.5 * mm)
    t = Table([[PC(titre, 7, True)], [img or ''], [PC(_txt(nom) or '&nbsp;', 7, False, COULEUR_TEXTE)]],
              colWidths=[largeur], rowHeights=[h_titre, h_sig, h_nom])
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('ROUNDEDCORNERS', [4, 4, 4, 4]),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'TOP'),
        ('VALIGN', (0, 1), (-1, 1), 'MIDDLE'),
        ('VALIGN', (0, 2), (-1, 2), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('TOPPADDING', (0, 0), (-1, 0), 2), ('BOTTOMPADDING', (0, 2), (-1, 2), 2),
    ]))
    return t


def _bloc_texte(titre, texte, largeur, min_h=None, size=7):
    rows = [[P(f"<b>{titre}</b>", 7.2, True, color=COULEUR_PRIMAIRE)],
            [P(_txt(texte) or "<font color='#9aa7b4'>—</font>", size)]]
    t = Table(rows, colWidths=[largeur], rowHeights=[None, min_h] if min_h else None)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_ENTETE),
        ('BACKGROUND', (0, 1), (-1, -1), COULEUR_GRIS),
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('LINEBEFORE', (0, 0), (0, 0), 3, COULEUR_ACCENT),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _doc(buffer, titre):
    return SimpleDocTemplate(
        buffer, pagesize=A4, title=titre, author="Centre Auto La Prudence+",
        topMargin=8 * mm, bottomMargin=11 * mm, leftMargin=MARGE, rightMargin=MARGE,
    )


# ════════════════════════════════════════════════════════════════
#  FICHE ENTRÉE - SORTIE ATELIER  (FicheControle)
# ════════════════════════════════════════════════════════════════
# Types : 'S' = Bon/Défaut (STATUT_CHOICES) ; 'B' = booléen (Oui = Bon) ;
#         'I' = booléen inversé (Oui = Défaut) ; 'V' = Intact / Fissuré / Cassé
CONTROLE_COL1 = [
    ("*L'alarme fonctionne-t-elle ?", 'alarme_fonctionne', 'S'),
    ("*Verrouillage des portes (intérieur/extérieur) ?", 'verrouillage_portes', 'S'),
    ("*Télécommande ?", 'telecommande_ouverture', 'S'),
    ("*Trappe à carburant ?", 'trappe_carburant', 'S'),
    ("*Tirette de capot ?", 'tirette_capot', 'S'),
    ("*La climatisation fonctionne-t-elle ?", 'climatisation_fonctionne', 'S'),
    ("*Fait-elle du froid ?", 'climatisation_fait_froid', 'S'),
    ("*Voyant allumé au tableau de bord moteur tournant ?", 'voyant_moteur_tableau_bord', 'I'),
    ("*L'autoradio s'allume-t-il ?", 'autoradio_s_allume', 'S'),
    ("*Y a-t-il du son dans les baffles ?", 'son_dans_baffles', 'S'),
    ("*Le dossier du véhicule est-il complet ? (assurance, carte rose, carte grise, visite tech.)",
     'dossier_vehicule_complet', 'B'),
    ("*L'horloge est-elle à l'heure ?", 'horloge_a_heure', 'S'),
    ("*Y a-t-il les triangles de sécurité ?", ('triangles_securite_presents', 'triangles_securite_nombre'), 'N'),
    ("*Y a-t-il les cales métalliques ?", ('cales_metalliques_presentes', 'cales_metalliques_nombre'), 'N'),
    ("*Y a-t-il le gilet de sécurité ?", 'gilet_securite_present', 'B'),
    ("*Y a-t-il l'extincteur ?", 'extincteur_present', 'B'),
    ("*La boîte à pharmacie ?", 'boite_pharmacie_presente', 'B'),
    ("*Le bouton d'allumage de l'éclairage du plafonnier fonctionne-t-il ?", 'bouton_eclairage_plafonnier', 'B'),
    ("*La roue de secours est-elle gonflée ?", 'roue_secours_gonflee_et_remis_en_place', 'B'),
    ("*Y a-t-il le cric ? La manivelle ? La clé de roue ?",
     ('cric_present', 'manivelle_presente', 'cle_roue_presente'), 'M'),
    ("*Les joints de portières sont-ils propres ?", 'joints_portieres_propres', 'S'),
    ("*Les enjoliveurs et écrous de roues sont-ils présents ?", 'enjoliveurs_et_ecrous_roues_presents', 'S'),
    ("*Y a-t-il les plaques d'immatriculation avant &amp; arrière ?", 'plaques_immatriculation_avant_arriere', 'S'),
    ("*Les tares avant &amp; arrière sont-elles présentes ?", 'tares_avant_arriere_presentes', 'S'),
    ("*Les garde-boues sont-ils présents et bien montés ?", 'garde_boues_presents_bien_montes', 'S'),
    ("*Les agrafes ?", 'agrafes_presentes', 'S'),
]
CONTROLE_COL2 = [
    ("*Les bavettes de roues &amp; les goujons de roues sont-ils présents ?",
     'bavettes_et_goujons_roues_presents', 'B'),
    ("*Le pare-brise est-il fissuré ou intact ?", 'pare_brise_etat', 'V'),
    ("*La pression des pneus est-elle bonne ?", 'pression_pneus_bonne', 'S'),
    ("*Les balais d'essuie-glace avant et arrière sont-ils en bon état ?", 'balais_essuie_glace_avant_arriere', 'S'),
    ("*Le gicleur lave-glace &amp; le bocal de réserve d'eau sont-ils en bon état ?",
     'gicleur_lave_glace_bocal_reserve', 'S'),
    ("*Les miroirs des rétroviseurs sont-ils fissurés, cassés ou intacts ?", 'miroirs_retroviseurs_etat', 'V'),
    ("*Les rétroviseurs se rabattent-ils ?", 'retroviseurs_se_rabattent', 'S'),
    ("*Les phares avant sont-ils fissurés, cassés ou intacts ?", 'phares_avant_etat', 'V'),
    ("*La caméra de recul fonctionne-t-elle ?", 'camera_recul_fonctionne', 'S'),
    ("*Le klaxon fonctionne-t-il ?", 'klaxon_fonctionne', 'S'),
    ("*Les clignotants avant &amp; arrière fonctionnent-ils ?", 'clignotants_avant_arriere_fonctionnent', 'S'),
    ("*Les capteurs de position avant et arrière bipent-ils ?", 'capteurs_position_avant_arriere_bipent', 'S'),
    ("*Les antibrouillards &amp; les feux de jour sont-ils en bon état ?", 'antibrouillards_feux_jour_bon_etat', 'S'),
    ("*Les feux arrière sont-ils fissurés, cassés ou intacts ?", 'feux_arriere_etat', 'V'),
    ("*Le système de démarrage fonctionne-t-il ?", 'systeme_demarrage_fonctionne', 'S'),
    ("*Le voyant des ceintures de sécurité s'allume-t-il après le serrage des ceintures ?",
     'voyant_ceintures_securite_s_allume', 'S'),
]
CONTROLE_COL3 = [
    ("*Les 05 tapis de sol sièges sont-ils présents ?", 'tapis_sol_5_presents', 'B'),
    ("*Les vitres avant se baissent-elles ?", 'vitres_avant_se_baissent', 'B'),
    ("*Les vitres arrière se baissent-elles ?", 'vitres_arriere_se_baissent', 'B'),
    ("*La télécommande fonctionne-t-elle ?", 'telecommande_vitres_fonctionne', 'B'),
    ("*Les autocollants du pare-brise sont-ils présents ? (si pare-brise à remplacer)",
     'autocollants_pare_brise_presents', 'B'),
    ("*Y a-t-il des voiles de peinture sur les vitres ?", 'voiles_peinture_sur_vitres', 'I'),
    ("*Le réglage des rétroviseurs fonctionne-t-il ?", 'reglage_des_miroirs_retroviseurs_fonctionnel', 'B'),
    ("*La console d'ouverture / fermeture des portières fonctionne-t-elle ?",
     'console_fermeture_ouverture_portiere_fonctionnel', 'B'),
]
CONTROLE_CAPOT = [
    ("*Les cosses de batterie sont-elles serrées ?", 'cosses_batterie_serrées', 'B'),
    ("*Le dessous du capot moteur est-il propre ?", 'sous_capot_moteur_est_propre', 'B'),
    ("*L'isolant thermique du capot est-il présent ?", 'isolant_thermique_capot_present', 'B'),
    ("*Niveau du lave-glace bon ?", 'niveau_liquide_lave_glace_bon', 'B'),
    ("*Niveau d'huile bon ?", 'niveau_liquide_huile_bon', 'B'),
    ("*Niveau du liquide de refroidissement bon ?", 'niveau_liquide_refroisseur_bon', 'B'),
    ("*Niveau du liquide de frein bon ?", 'niveau_liquide_frein_bon', 'B'),
]
CONTROLE_PEINTURE = [
    ("*Rayures ?", 'qualite_rendu_peinture_rayures', 'I'),
    ("*Décollement ?", 'qualite_rendu_peinture_decollement', 'I'),
    ("*Couleur conforme ?", 'qualite_rendu_peinture_couleur', 'B'),
    ("*Éclat / brillance ?", 'qualite_rendu_peinture_eclat_brillance', 'B'),
    ("*Fissures ?", 'qualite_rendu_peinture_frissure', 'I'),
]


def _ligne_controle(fiche, libelle, champ, type_):
    """Retourne (libellé enrichi, état 'ok'|'ko'|None)."""
    if type_ == 'S':
        return libelle, _etat(_get(fiche, champ))
    if type_ in ('B', 'I'):
        v = _get(fiche, champ)
        if v is None or v == '':
            return libelle, None
        if type_ == 'I':
            v = not v
        rep = _oui_non(_get(fiche, champ))
        return f"{libelle} <b><font color='#0b3d91'>{rep}</font></b>", 'ok' if v else 'ko'
    if type_ == 'V':
        v = _get(fiche, champ)
        if not v:
            return libelle, None
        lib = _display(fiche, champ)
        return f"{libelle} <b><font color='#0b3d91'>{escape(lib)}</font></b>", ('ok' if str(v).upper() == 'INTACT' else 'ko')
    if type_ == 'N':
        present, nombre = (_get(fiche, c) for c in champ)
        if present is None:
            return libelle, None
        extra = _oui_non(present)
        if present and nombre:
            extra += f" – {nombre}"
        return f"{libelle} <b><font color='#0b3d91'>{extra}</font></b>", 'ok' if present else 'ko'
    if type_ == 'M':
        noms = ('Cric', 'Manivelle', 'Clé')
        vals = [bool(_get(fiche, c)) for c in champ]
        detail = ' / '.join(f"{n} {'oui' if v else 'non'}" for n, v in zip(noms, vals))
        return f"{libelle} <b><font color='#0b3d91'>{detail}</font></b>", 'ok' if all(vals) else 'ko'
    return libelle, None


def _table_bon_defaut(fiche, lignes, largeur, size=6.3):
    cw = 8.5 * mm
    data = [[P(''), PC('Bon', 6.5), PC('Défaut', 5.6)]]
    for lib, champ, type_ in lignes:
        texte, e = _ligne_controle(fiche, lib, champ, type_)
        data.append([P(texte, size), Coche('ok' if e == 'ok' else None), Coche('ko' if e == 'ko' else None)])
    return _grille(data, [largeur - 2 * cw, cw, cw])


def _table_oui_non(fiche, lignes, largeur, size=6.3, titre=''):
    data = [[PC(titre, 6.5) if titre else P('', 6.5), PC('Réponse', 5.8)]]
    for lib, champ, type_ in lignes:
        v = _get(fiche, champ)
        rep = _oui_non(v)
        bon = None if v is None else (bool(v) if type_ == 'B' else not v)
        coul = '#16a34a' if bon else '#dc2626'
        data.append([P(lib, size), P(f"<b><font color='{coul}'>{rep}</font></b>" if rep else '', 7, align=TA_CENTER)])
    return _grille(data, [largeur - 11 * mm, 11 * mm])


class _VueSortie:
    """La fiche vue avec les valeurs du contrôle de sortie (etat_sortie) une fois la sortie archivée.
    Un élément non relevé à la sortie garde sa valeur d'entrée."""

    def __init__(self, fiche, etat):
        self._fiche, self._etat = fiche, etat

    def _sortie(self, champ):
        v = self._etat.get(champ)
        return None if v in (None, '', []) else v

    def __getattr__(self, name):
        if name.startswith('get_') and name.endswith('_display'):
            champ = name[4:-8]
            v = self._sortie(champ)
            if v is not None:
                try:
                    choix = dict(self._fiche._meta.get_field(champ).flatchoices)
                except Exception:
                    choix = {}
                return lambda: str(choix.get(v, v))
        elif name in self._etat:
            v = self._sortie(name)
            if v is not None:
                return v
        return getattr(self._fiche, name)


def _kilometrage(fiche):
    entree, sortie = _get(fiche, 'kilometrage'), _get(fiche, 'kilometrage_sortie')
    if sortie in (None, ''):
        return _num(entree or None, ' km')
    return f"Entrée : {_num(entree or 0, ' km')}   –   Sortie : {_num(sortie, ' km')}"


def generer_pdf_fiche_controle(fiche):
    etat = _get(fiche, 'etat_sortie')
    if isinstance(etat, dict) and etat:
        fiche = _VueSortie(fiche, etat)      # fiche finale : valeurs de sortie
    buffer = BytesIO()
    titre = "FICHE ENTRÉE - SORTIE ATELIER"
    doc = _doc(buffer, titre)
    el = []

    entree = _get(fiche, 'entree')
    numero = (_get(entree, 'numero') or _get(entree, 'numero_entree')
              or str(_get(fiche, 'id', '')).split('-')[0].upper())
    el += _entete(titre, numero, _get(fiche, 'date_inspection'))

    # ── Infos véhicule ──
    gauche = _champs([
        ("Travail à effectuer", _get(fiche, 'travail_a_effectuer')),
        ("Entrée le", _date(_get(fiche, 'entree_le'))),
        ("Sortie le", _date(_get(fiche, 'sortir_le'))),
    ], [28 * mm, 62 * mm])
    droite = _champs([
        ("Immatriculation", _get(fiche, 'immatriculation')),
        ("Marque / Modèle", f"{_get(fiche, 'marque') or ''} {_get(fiche, 'modele') or ''}".strip()),
        ("Kilométrage", _kilometrage(fiche)),
        ("Téléphone", _get(fiche, 'telephone')),
    ], [26 * mm, 70 * mm])
    info = _colonnes([gauche, droite], [92 * mm, LARGEUR - 92 * mm], gap=2 * mm)
    info_box = Table([[info]], colWidths=[LARGEUR])
    info_box.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
                                  ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                                  ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]))
    el += [info_box, Spacer(1, 2 * mm)]

    # ── 3 colonnes ──
    w1, w2 = 64 * mm, 66 * mm
    w3 = LARGEUR - w1 - w2 - 4 * mm
    col1 = [_table_bon_defaut(fiche, CONTROLE_COL1, w1)]

    col2 = _schema_carrosserie(fiche, w2) + [Spacer(1, 1.5 * mm),
                                             _table_bon_defaut(fiche, CONTROLE_COL2, w2),
                                             Spacer(1, 1.5 * mm),
                                             _table_oui_non(fiche, CONTROLE_PEINTURE, w2, titre='QUALITÉ PEINTURE')]

    jauge = _jauge_carburant(_get(fiche, 'jauge_carburant'), _display(fiche, 'jauge_carburant'), w3, 22 * mm)
    jauge_t = Table([[PC("JAUGE CARBURANT", 7, True, colors.white)], [jauge]], colWidths=[w3])
    jauge_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    etat_g = str(_get(fiche, 'etat_general') or '').upper()
    coul_eg = {'BON': '#16a34a', 'MOYEN': '#d97706', 'MAUVAIS': '#dc2626'}.get(etat_g, '#2c3e50')
    eg = Table([[P("<b>ÉTAT GÉNÉRAL</b>", 7.2, True, color=COULEUR_PRIMAIRE),
                 P(f"<b><font color='{coul_eg}'>{escape(_display(fiche, 'etat_general'))}</font></b>",
                   8.5, align=TA_RIGHT)]], colWidths=[w3 * 0.55, w3 * 0.45])
    eg.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
                            ('BACKGROUND', (0, 0), (-1, -1), COULEUR_ENTETE),
                            ('LINEBEFORE', (0, 0), (0, 0), 3, COULEUR_ACCENT),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    col3 = [
        _legende(w3), Spacer(1, 1.5 * mm), jauge_t, Spacer(1, 1.5 * mm),
        _table_oui_non(fiche, CONTROLE_COL3, w3, titre='HABITACLE'), Spacer(1, 1.5 * mm),
        _table_oui_non(fiche, CONTROLE_CAPOT, w3, titre='SOUS LE CAPOT'), Spacer(1, 1.5 * mm),
        eg,
    ]
    el.append(_colonnes([col1, col2, col3], [w1 + 2 * mm, w2 + 2 * mm, w3]))
    el.append(Spacer(1, 2.5 * mm))

    # ── Commentaires : grande zone horizontale, juste avant les signatures ──
    el.append(_bloc_texte("COMMENTAIRES", _get(fiche, 'commentaires'), LARGEUR, min_h=20 * mm, size=8))
    el.append(Spacer(1, 2.5 * mm))

    # ── Signatures : les 5 sur une seule ligne ──
    cases = [
        ("Réceptionniste", 'nom_receptionniste', 'signature_receptionniste'),
        ("Client avant réparation", 'nom_client_avant', 'signature_client_avant'),
        ("Client après réparation", 'nom_client_apres', 'signature_client_apres'),
        ("Technicien", 'nom_technicien', 'signature_technicien'),
        ("Contrôleur", 'nom_controleur', 'signature_controleur'),
    ]
    ws = (LARGEUR - 4 * 1.5 * mm) / 5
    el.append(_colonnes(
        [_case_signature(lib, _get(fiche, nom), _get(fiche, sig), ws, 19 * mm) for lib, nom, sig in cases],
        [ws + 1.5 * mm] * 4 + [ws]))

    pied = _pied_de_page(f"Fiche entrée-sortie atelier N° {numero}")
    doc.build(el, onFirstPage=pied, onLaterPages=pied)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# ════════════════════════════════════════════════════════════════
#  FICHE DE DIAGNOSTIC MÉCANIQUE  (FicheTechnique)
# ════════════════════════════════════════════════════════════════
def _titre_tableau(texte, n_col):
    return [PC(texte, 6.8)] + [''] * (n_col - 1)


def _t_eclairage(f, w):
    cw = 8.2 * mm
    av = [('Veilleuses', 'veilleuses'), ('Croisement', 'croisement'), ('Route', 'route'),
          ('Anti-brouillard', 'antibrouillard'), ('Clignotants', 'clignotants')]
    ar = [('Feux de position', 'feux_position'), ('Stop', 'stop'), ('Clignotants', 'clignotants'),
          ('Recul', 'recul'), ('Anti-brouillard', 'antibrouillard'), ('Feu de plaque', 'feu_plaque'),
          ('3<super>e</super> feu stop', '3eme_feu_stop')]
    data = [[PC('ÉCLAIRAGE', 6.8), '', PC('Bon', 6.3), PC('Défaut', 5.6)]]
    for i, (lib, c) in enumerate(av):
        data.append([P(lib), PC('AV', 7) if i == 0 else ''] + _bd(_get(f, f'eclairage_av_{c}')))
    for i, (lib, c) in enumerate(ar):
        data.append([P(lib), PC('AR', 7) if i == 0 else ''] + _bd(_get(f, f'eclairage_ar_{c}')))
    data.append([P('Contrôle hauteur de phare'), ''] + _bd(_get(f, 'controle_hauteur_phare')))
    n = len(data)
    return _grille(data, [w - 2 * cw - 9 * mm, 9 * mm, cw, cw], extra=[
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (1, 1), (1, 5)), ('SPAN', (1, 6), (1, 12)),
        ('SPAN', (0, n - 1), (1, n - 1)),
        ('LINEABOVE', (0, 6), (-1, 6), 1, COULEUR_PRIMAIRE),
        ('LINEABOVE', (0, n - 1), (-1, n - 1), 1, COULEUR_PRIMAIRE),
    ])


def _t_simple(titre, lignes, f, w, entete=('Bon', 'Défaut')):
    cw = 8.2 * mm
    data = [[PC(titre, 6.8), PC(entete[0], 6.3), PC(entete[1], 5.6)]]
    for lib, champ in lignes:
        data.append([P(lib)] + _bd(_get(f, champ)))
    return _grille(data, [w - 2 * cw, cw, cw])


def _t_freinage_sol(f, w):
    cw = 8.2 * mm
    t_liq = _num(_get(f, 'liquide_frein_temperature'), ' °C')
    data = [
        [PC('FREINAGE', 6.8), '', PC('Bon', 6.3), PC('Défaut', 5.6)],
        [P('Course pédale de frein'), ''] + _bd(_get(f, 'course_pedale_frein')),
        [P('Course frein à main'), ''] + _bd(_get(f, 'course_frein_main')),
        [P('Liquide de frein'), P(f"<b>{t_liq or '……… °C'}</b>", 6.3, align=TA_CENTER)]
        + _bd(_get(f, 'liquide_frein_etat')),
        [P('Maître-cylindre (fuite)'), ''] + _bd(_get(f, 'maitre_cylindre_fuite')),
    ]
    return _grille(data, [w - 2 * cw - 16 * mm, 16 * mm, cw, cw], extra=[
        ('SPAN', (0, 0), (1, 0)), ('SPAN', (0, 1), (1, 1)), ('SPAN', (0, 2), (1, 2)), ('SPAN', (0, 4), (1, 4)),
    ])


def _t_clim(f, w):
    cw = 8.2 * mm
    t = _num(_get(f, 'climatisation_temperature_soufflage'), ' °C')
    data = [
        [PC('CLIMATISATION', 6.8), '', ''],
        [P('T° soufflage'), P(f"<b>{t or '……… °C'}</b>", 6.5, align=TA_CENTER), ''],
        [P('Filtre d\'habitacle')] + _bd(_get(f, 'climatisation_filtre_habitacle')),
        [P('<i>Préconisation : 1 fois / an</i>'), '', ''],
    ]
    return _grille(data, [w - 2 * cw, cw, cw], extra=[
        ('SPAN', (0, 0), (-1, 0)), ('SPAN', (1, 1), (2, 1)), ('SPAN', (0, 3), (-1, 3)),
    ])


def _t_niveau(titre, valeur, libelle, w):
    t = Table([[PC(titre, 6.8)], [_niveau_huile(valeur, libelle, w - 4 * mm)]], colWidths=[w])
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_ENTETE),
        ('LINEBELOW', (0, 0), (-1, 0), 0.4, COULEUR_BORD),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))
    return t


def _oui_non_cells(v):
    """2 cellules Oui / Non (la réponse est pastillée)."""
    v = _bool(v)
    if v is None:
        return [PC('Oui', 6.3, False, COULEUR_VIDE), PC('Non', 6.3, False, COULEUR_VIDE)]
    return [PC('Oui', 6.8, True, COULEUR_ACCENT) if v else PC('Oui', 6.3, False, COULEUR_VIDE),
            PC('Non', 6.8, True, COULEUR_ACCENT) if not v else PC('Non', 6.3, False, COULEUR_VIDE)]


def _t_pare_brise(f, w):
    cw = 8.2 * mm
    appeler = _get(f, 'pare_brise_fissure_appeler_le')
    data = [
        [PC('PARE-BRISE', 6.8), '', PC('Bon', 6.3), PC('Défaut', 5.6)],
        [P('Balais essuie-glace'), PC('AV', 6.5)] + _bd(_get(f, 'balais_essuie_glace_av')),
        ['', PC('AR', 6.5)] + _bd(_get(f, 'balais_essuie_glace_ar')),
        [P('Impact'), ''] + _oui_non_cells(_get(f, 'pare_brise_impact')),
        [P(f"Fissure (si oui, appeler le <b>{_txt(appeler) or '………'}</b>)", 6.2), '']
        + _oui_non_cells(_get(f, 'pare_brise_fissure')),
    ]
    return _grille(data, [w - 2 * cw - 8 * mm, 8 * mm, cw, cw], extra=[
        ('SPAN', (0, 0), (1, 0)), ('SPAN', (0, 1), (0, 2)), ('SPAN', (0, 3), (1, 3)), ('SPAN', (0, 4), (1, 4)),
    ])


def _t_plaques(f, w):
    cw = 8.2 * mm
    data = [
        [PC('', 6.8), '', PC('Bon', 6.3), PC('Défaut', 5.6)],
        [P("Plaques d'immatriculation"), PC('AV', 6.5)] + _bd(_get(f, 'plaques_immatriculation_av')),
        ['', PC('AR', 6.5)] + _bd(_get(f, 'plaques_immatriculation_ar')),
    ]
    return _grille(data, [w - 2 * cw - 8 * mm, 8 * mm, cw, cw], extra=[
        ('SPAN', (0, 0), (1, 0)), ('SPAN', (0, 1), (0, 2))])


def _t_roues(titre, lignes, f, w, prefixe, notes=None, mesures=None):
    """Table AV G / AV D / AR G / AR D (1 pastille par roue).
    lignes : [(libellé, suffixe_champ, roues_disponibles)] avec roues ⊂ {'av_g','av_d','ar_g','ar_d'}."""
    roues = ['av_g', 'av_d', 'ar_g', 'ar_d']
    mesures = mesures or {}
    lw = w - 4 * 9 * mm
    has_mes = bool(mesures)
    lib_w = lw - (14 * mm if has_mes else 0)
    data = [
        [PC(titre, 6.8)] + ([''] if has_mes else []) + [PC('AV', 6.5), '', PC('AR', 6.5), ''],
        [''] + ([''] if has_mes else []) + [PC('G', 6.3), PC('D', 6.3), PC('G', 6.3), PC('D', 6.3)],
    ]
    for lib, suffixe, dispo in lignes:
        row = [P(lib)]
        if has_mes:
            m = mesures.get(suffixe)
            row.append(P(f"<b>{m}</b>" if m else '', 6.3, align=TA_RIGHT) if m is not None else '')
        for r in roues:
            champ = f'{prefixe}_{suffixe}_{r}' if prefixe else f'{suffixe}_{r}'
            row.append(_roue(_get(f, champ)) if r in dispo else '')
        data.append(row)
    off = 1 if has_mes else 0
    extra = [
        ('SPAN', (0, 0), (off, 1)),
        ('SPAN', (1 + off, 0), (2 + off, 0)), ('SPAN', (3 + off, 0), (4 + off, 0)),
        ('BACKGROUND', (0, 0), (-1, 1), COULEUR_ENTETE),
        ('LINEAFTER', (2 + off, 0), (2 + off, -1), 1, COULEUR_PRIMAIRE),
    ]
    for i, (_, _, dispo) in enumerate(lignes, start=2):
        for j, r in enumerate(roues):
            if r not in dispo:
                extra.append(('BACKGROUND', (1 + off + j, i), (1 + off + j, i), colors.HexColor('#eceff3')))
    cws = ([lib_w, 14 * mm] if has_mes else [lw]) + [9 * mm] * 4
    return _grille(data, cws, entetes=2, extra=extra)


TOUTES = ('av_g', 'av_d', 'ar_g', 'ar_d')


def _t_pneus(f, w):
    lw = w - 5 * 10 * mm
    pr = [_get(f, f'pneu_{r}_profondeur') for r in ('av_g', 'av_d', 'ar_g', 'ar_d', 'roue_secours')]
    data = [
        [PC('PNEUMATIQUES', 6.8), PC('AV', 6.5), '', PC('AR', 6.5), '', PC('Roue de<br/>secours', 5.5)],
        ['', PC('G', 6.3), PC('D', 6.3), PC('G', 6.3), PC('D', 6.3), ''],
        [P('Profondeur')] + [P(f"<b>{_num(v, ' mm')}</b>" if v not in (None, '') else '…… mm', 6.3,
                               align=TA_CENTER) for v in pr],
        [P('Usure*')] + [_roue(_get(f, f'pneu_{r}_usure')) for r in TOUTES] + [''],
        [P('Écrous / goujons')] + [_roue(_get(f, f'ecrou_goujons_{r}')) for r in TOUTES] + [''],
        [P('Géométrie nécessaire')] + _oui_non_geo(_get(f, 'geometrie_necessaire')),
    ]
    return _grille(data, [lw] + [10 * mm] * 5, entetes=2, extra=[
        ('SPAN', (0, 0), (0, 1)), ('SPAN', (1, 0), (2, 0)), ('SPAN', (3, 0), (4, 0)), ('SPAN', (5, 0), (5, 1)),
        ('SPAN', (1, 5), (2, 5)), ('SPAN', (3, 5), (4, 5)),
        ('BACKGROUND', (0, 0), (-1, 1), COULEUR_ENTETE),
        ('BACKGROUND', (5, 3), (5, 5), colors.HexColor('#eceff3')),
    ])


def _oui_non_geo(v):
    oui, non = _oui_non_cells(v)
    return [oui, '', non, '', '']


def _t_echappement(f, w):
    cw = 8.2 * mm
    cat = _get(f, 'echap_catalyseur_filtre_particules') or ''
    data = [
        [PC('ÉCHAPPEMENT', 6.8), PC('Bon', 6.3), PC('Défaut', 5.6)],
        [P('Catalyseur / Filtre à particules'), PC(_txt(cat) or '/', 6.5, True, COULEUR_TEXTE), ''],
        [P('Partie avant')] + _bd(_get(f, 'echap_partie_avant')),
        [P('Partie intermédiaire')] + _bd(_get(f, 'echap_partie_intermediaire')),
        [P('Partie arrière')] + _bd(_get(f, 'echap_partie_arriere')),
        [P('Fixations')] + _bd(_get(f, 'echap_fixations')),
    ]
    return _grille(data, [w - 2 * cw, cw, cw], extra=[('SPAN', (1, 1), (2, 1))])


def _t_transmission(f, w):
    cw = 8.2 * mm
    data = [
        [PC('TRANSMISSION', 6.8), PC('G', 6.3), '', PC('D', 6.3), ''],
        ['', PC('Bon', 5.8), PC('Déf.', 5.8), PC('Bon', 5.8), PC('Déf.', 5.8)],
        [P('Soufflets')] + _bd(_get(f, 'transmission_soufflets_g')) + _bd(_get(f, 'transmission_soufflets_d')),
        [P('Cardans')] + _bd(_get(f, 'transmission_cardans_g')) + _bd(_get(f, 'transmission_cardans_d')),
    ]
    return _grille(data, [w - 4 * cw] + [cw] * 4, entetes=2, extra=[
        ('SPAN', (0, 0), (0, 1)), ('SPAN', (1, 0), (2, 0)), ('SPAN', (3, 0), (4, 0))])


def _t_moteur(f, w):
    cw = 8.2 * mm
    data = [[PC('MOTEUR', 6.8), '', ''],
            [P('Fuite moteur')] + _oui_non_cells(_get(f, 'fuite_moteur'))]
    return _grille(data, [w - 2 * cw, cw, cw], extra=[('SPAN', (0, 0), (-1, 0))])


POST_CONTROLES = [
    ('Lave-glace', 'ok_lave_glace'),
    ('Liquide de refroidissement', 'ok_liquide_refroidissement'),
    ('Kit sécurité (cales, extincteur, triangles)', 'ok_kit_securite'),
    ("Boîte d'ampoules (boîte à pharmacie)", 'ok_boite_ampoules'),
    ('Mise en place étiquette vidange', 'ok_etiquette_vidange'),
    ('Mise en place étiquette monte pneumatique', 'ok_etiquette_monte_pneumatique'),
    ('Remise à zéro indicateur de maintenance', 'ok_remise_a_zero_maintenance'),
    ('Pression des pneus', 'ok_pression_des_pneus'),
]


def _t_post_controles(f, w):
    cw = 9 * mm
    data = [[PC("NIVEAU D'HUILE APRÈS INTERVENTION", 6.8), ''],
            [_niveau_huile(_get(f, 'niveau_huile_apres_intervention'),
                           _display(f, 'niveau_huile_apres_intervention'), w - 6 * mm), '']]
    for lib, champ in POST_CONTROLES:
        v = bool(_get(f, champ))
        data.append([P(f"<b>{lib}</b>"), Coche('ok') if v else PC('Ok', 6.3, False, COULEUR_VIDE)])
    t = _grille(data, [w - cw, cw], extra=[('SPAN', (0, 0), (-1, 0)), ('SPAN', (0, 1), (-1, 1)),
                                           ('ALIGN', (0, 1), (-1, 1), 'CENTER')])
    return [t, P("<i>* Coché si effectué</i>", 6)]


def _case_oui_non_entete(f, w):
    data = [[P(''), PC('Oui', 6.5), PC('Non', 6.5)]]
    for lib, champ in (('Rendre pièces', 'rendre_pieces'), ('Écrou antivol', 'ecrou_antivol'),
                       ('Alarme', 'alarme')):
        v = _bool(_get(f, champ))
        data.append([P(lib, 7)] + [Coche('ok') if v is True else Coche(None),
                                   Coche('ko') if v is False else Coche(None)])
    return _grille(data, [w - 18 * mm, 9 * mm, 9 * mm])


def generer_pdf_fiche_technique(fiche):
    buffer = BytesIO()
    titre = "FICHE DE DIAGNOSTIC MÉCANIQUE"
    doc = _doc(buffer, titre)
    el = []
    f = fiche
    numero = _get(f, 'numero_fiche') or str(_get(f, 'id', '')).split('-')[0].upper()
    el += _entete(titre, numero, _get(f, 'date_creation'))

    # ── En-tête véhicule ──
    dates = _champs([("Entrée le", _date(_get(f, 'entree_le'))), ("Sortie le", _date(_get(f, 'sortie_le')))],
                    [18 * mm, 30 * mm])
    infos = _champs([
        ("Nom client", _get(f, 'nom_client')),
        ("Immatriculation", _get(f, 'immatriculation')),
        ("Véhicule", _get(f, 'vehicule')),
        ("Kilométrage", _num(_get(f, 'kilometrage') or None, ' km')),
        ("Préconisation courroie de distribution", _date(_get(f, 'preconisation_courroie_distribution'))),
    ], [48 * mm, 52 * mm])
    w_on = LARGEUR - 50 * mm - 102 * mm - 4 * mm
    el.append(_colonnes([[dates], [infos], [_case_oui_non_entete(f, w_on)]],
                        [50 * mm + 2 * mm, 102 * mm + 2 * mm, w_on], valign='TOP'))
    el.append(Spacer(1, 2 * mm))

    # ── VÉHICULE AU SOL ──
    wc = (LARGEUR - 4 * mm) / 3
    c1 = [_t_eclairage(f, wc), Spacer(1, 1.5 * mm),
          _t_simple('ÉLECTRONIQUE', [('Voyant tableau de bord', 'voyant_tableau_bord'),
                                     ('Code défaut', 'code_defaut')], f, wc),
          Spacer(1, 1.5 * mm),
          _t_simple('HABITACLE', [('Sièges', 'sieges'),
                                  ('Siège conducteur', 'siege_conducteur_etat'),
                                  ('Siège passager', 'siege_passager_etat'),
                                  ('Sièges arrière / banquette', 'sieges_arriere_etat'),
                                  ('Ceintures de sécurité', 'ceintures_securite_etat')], f, wc)]
    c2 = [_t_simple('ALLUMAGE', [('Bougies / Faisceau', 'bougies_faisceau'), ('Sonde lambda', 'sonde_lamda')], f, wc),
          Spacer(1, 1.5 * mm), _t_freinage_sol(f, wc),
          P("* Liquide DOT4 doit être supérieur à 165 °C<br/>* Liquide DOT5 doit être supérieur à 185 °C", 5.6),
          Spacer(1, 1.2 * mm), _t_clim(f, wc), Spacer(1, 1.5 * mm),
          _t_niveau("NIVEAU D'HUILE À LA PRISE EN CHARGE", _get(f, 'niveau_huile_prise_en_charge'),
                    _display(f, 'niveau_huile_prise_en_charge'), wc)]
    jauge = Table([[PC('Jauge carburant', 6.8)],
                   [_jauge_carburant(_get(f, 'jauge_carburant'), _display(f, 'jauge_carburant'), wc - 4 * mm,
                                     20 * mm)]], colWidths=[wc])
    jauge.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), 1),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 1)]))
    c3 = [_t_pare_brise(f, wc), jauge, _t_plaques(f, wc), Spacer(1, 1.5 * mm),
          _t_simple('CHARGE*** / DÉMARRAGE', [('Batterie', 'batterie'),
                                             ('Alternateur / Démarreur**', 'alternateur_demarreur'),
                                             ('Liquide de refroidissement***', 'liquide_refroidissement')], f, wc),
          P("*** La valeur doit être comprise entre -15° et -40°<br/>"
            "** La valeur doit être comprise entre 13,5 et 14,9 volts. Voir ticket agrafé", 5.6)]
    el += [_bandeau("VÉHICULE AU SOL"), Spacer(1, 1.5 * mm),
           _colonnes([c1, c2, c3], [wc + 2 * mm, wc + 2 * mm, wc]), Spacer(1, 2 * mm)]

    # ── VÉHICULE MI-HAUTEUR ──
    wg = 88 * mm
    wd = LARGEUR - wg - 2 * mm
    susp = [(lib, c, TOUTES) for lib, c in (
        ('Amortisseurs', 'amortisseurs'), ('Coupelles', 'coupelles'), ('Ressorts', 'ressorts'),
        ('Kit de protection', 'kit_protection'), ('Butées', 'butees'),
        ('Biellettes suspension', 'biellettes'))]
    liaisons = [(lib, c, TOUTES) for lib, c in (
        ('Roulements', 'roulements'), ('Rotules', 'rotules'), ('Bras de suspension', 'bras_de_suspension'),
        ('Silent-blocs', 'silent_bloc_s'))]
    gauche = [_t_pneus(f, wg), P("* La profondeur minimum autorisée par la loi est de 2,6 millimètres", 5.6),
              Spacer(1, 1.5 * mm), _t_roues('SUSPENSION', susp, f, wg, 'susp'),
              Spacer(1, 1.5 * mm), _t_roues('ROULEMENTS ET LIAISONS AU SOL', liaisons, f, wg, '')]
    ep = _num(_get(f, 'frein_disques_epaisseur_mm'), ' mm')
    diam = _num(_get(f, 'frein_tambours_diametre_mm'), ' mm')
    freins = [('Flexibles', 'flexibles', TOUTES), ('Disques', 'disques', TOUTES),
              ('Plaquettes', 'plaquettes', TOUTES), ('Kit frein', 'kit_frein', ('ar_g', 'ar_d')),
              ('Tambours', 'tambours', ('ar_g', 'ar_d'))]
    train = [('Flexibles', 'flexibles', TOUTES), ('Disques', 'disques', TOUTES),
             ('Plaquettes', 'plaquettes', TOUTES), ('Kit frein', 'kit_frein', ('av_g', 'av_d')),
             ('Tambours', 'tambours', TOUTES)]
    droite = [_t_roues('FREINAGE', freins, f, wd, 'frein',
                       mesures={'disques': ep or '…… mm', 'tambours': diam or '…… mm'}),
              Spacer(1, 1.5 * mm), _t_roues('TRAIN ROULANT', train, f, wd, 'train')]
    legende = Table([[Coche('ok', 2.6 * mm), P('Bon', 6), Coche('ko', 2.6 * mm), P('Défaut', 6),
                      Coche(None, 2.6 * mm), P('Non contrôlé', 6)]],
                    colWidths=[4 * mm, 8 * mm, 4 * mm, 10 * mm, 4 * mm, 16 * mm], hAlign='RIGHT')
    legende.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                 ('LEFTPADDING', (0, 0), (-1, -1), 0.5), ('RIGHTPADDING', (0, 0), (-1, -1), 0.5),
                                 ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    el += [KeepTogether([_bandeau("VÉHICULE MI-HAUTEUR"), Spacer(1, 1.5 * mm),
                         _colonnes([gauche, droite], [wg + 2 * mm, wd]), legende])]
    el.append(Spacer(1, 2 * mm))

    # ── VÉHICULE LEVÉ / POST-CONTRÔLES ──
    w1 = 62 * mm
    w2 = 64 * mm
    w3 = LARGEUR - w1 - w2 - 4 * mm
    leve = [_bandeau("VÉHICULE LEVÉ", w1, 9), Spacer(1, 1.5 * mm), _t_echappement(f, w1), Spacer(1, 1.2 * mm),
            _t_transmission(f, w1), Spacer(1, 1.2 * mm),
            _t_simple('FREINAGE', [('Canalisation', 'frein_canalisation'),
                                   ('Câble frein à main', 'frein_cable_frein_main'),
                                   ('Répartiteur (fuite)', 'frein_repartiteur_fuite')], f, w1),
            Spacer(1, 1.2 * mm), _t_moteur(f, w1)]
    post = [_bandeau("POST-CONTRÔLES ET MISES À NIVEAU", w2, 8), Spacer(1, 1.5 * mm)] + _t_post_controles(f, w2)
    post += [Spacer(1, 1.5 * mm),
             _case_signature("Signature Contrôleur", _get(f, 'nom_controleur'), _get(f, 'signature_controleur'),
                             w2, 20 * mm),
             Spacer(1, 1.5 * mm),
             _case_signature("Signature Client", _get(f, 'nom_client_signataire'), _get(f, 'signature_client'),
                             w2, 20 * mm)]
    comm = [_bandeau("DIAGNOSTIC TECHNIQUE", w3, 8), Spacer(1, 1.5 * mm),
            _bloc_texte("Diagnostic technique", _get(f, 'diagnostic'), w3, min_h=88 * mm, size=7.5)]
    el.append(KeepTogether(_colonnes([leve, post, comm], [w1 + 2 * mm, w2 + 2 * mm, w3])))

    pied = _pied_de_page(f"Fiche de diagnostic mécanique N° {numero}")
    doc.build(el, onFirstPage=pied, onLaterPages=pied)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
