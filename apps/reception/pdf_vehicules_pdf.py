"""
PDF des listes (admin) : véhicules et clients.
Même charte que les fiches atelier et les exports guérite :
en-tête logo « CENTRE AUTO La PRUDENCE+ », bandeau titre bleu souligné orange,
encadré compteur, bandeau de répartition, tableau zébré, pied « Page x / y ».

Les signatures ne changent pas :
    generer_pdf_liste_vehicules(qs, today=None) -> bytes
    generer_pdf_liste_clients(qs)               -> bytes
"""
from collections import Counter
from html import escape
from io import BytesIO

from django.utils import timezone
from reportlab.graphics.shapes import Drawing, Ellipse, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.documents.pdf_generator import COULEUR_ACCENT, COULEUR_GRIS, COULEUR_PRIMAIRE, COULEUR_TEXTE

COULEUR_DISCRET = colors.HexColor('#6b7280')
COULEUR_LIGNE = colors.HexColor('#d5dbe1')
VERT, ROUGE, ORANGE, BLEU, GRIS = '#16a34a', '#dc2626', '#e67e22', '#2563eb', '#6b7280'

SERVICES = ("Tôlerie – Peinture – Freinage – Chaudronnerie – Mécanique Générale<br/>"
            "Électricité – Climatisation – Pneumatique – Tapisserie – Sérigraphie")
ADRESSE = "BP : 9060 Douala – Tél : (+237) 650 99 75 09"

PAGE_W, PAGE_H = landscape(A4)
MARGE = 10 * mm
LARGEUR = PAGE_W - 2 * MARGE  # 277 mm


# ════════════════════════════════════════════════════════════════
#  Briques communes
# ════════════════════════════════════════════════════════════════
def _maintenant():
    n = timezone.now()
    return timezone.localtime(n) if timezone.is_aware(n) else n


def _txt(v):
    return escape(str(v)) if v not in (None, '') else ''


def P(texte, size=7.5, bold=False, align=TA_LEFT, color=COULEUR_TEXTE):
    return Paragraph(texte or '', ParagraphStyle(
        '', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size,
        leading=size * 1.25, alignment=align, textColor=color))


def _vide_cell():
    return P('—', align=TA_CENTER, color=COULEUR_DISCRET)


def _badge(libelle, couleur, sous_texte=''):
    """Pastille colorée + libellé gras, avec éventuellement une 2e ligne grise."""
    txt = f"<font size=9 color='{couleur}'>•</font>&nbsp;<font color='{couleur}'><b>{escape(libelle)}</b></font>"
    if sous_texte:
        txt += f"<br/><font size=6.5 color='#6b7280'>{escape(sous_texte)}</font>"
    return P(txt, 7.5)


def _sans_marges(t):
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _logo(largeur=62 * mm, hauteur=21 * mm):
    d = Drawing(largeur, hauteur)
    d.add(String(largeur / 2, hauteur - 6.5 * mm, "CENTRE AUTO", fontName='Helvetica-Bold',
                 fontSize=11, fillColor=COULEUR_PRIMAIRE, textAnchor='middle'))
    d.add(Ellipse(largeur / 2, hauteur / 2 - 3.2 * mm, largeur / 2 - 1, 6.4 * mm,
                  fillColor=COULEUR_PRIMAIRE, strokeColor=COULEUR_ACCENT, strokeWidth=1.2))
    d.add(String(largeur / 2, hauteur / 2 - 2.6 * mm, "La PRUDENCE+", fontName='Helvetica-Bold',
                 fontSize=14, fillColor=colors.white, textAnchor='middle'))
    d.add(String(largeur / 2, hauteur / 2 - 6.6 * mm, "Véhicules Légers / Poids Lourds",
                 fontName='Helvetica-Oblique', fontSize=6.5, fillColor=colors.white, textAnchor='middle'))
    return d


def _entete(titre, total, unite):
    haut = _sans_marges(Table([[
        _logo(),
        P(f"<b>{SERVICES}</b><br/><font color='#e67e22'><b>{ADRESSE}</b></font>",
          8.5, False, TA_CENTER, COULEUR_PRIMAIRE),
    ]], colWidths=[66 * mm, LARGEUR - 66 * mm]))

    titre_t = Table([[P(f"<b>{escape(titre)}</b>", 13, True, TA_LEFT, colors.white)]], colWidths=[150 * mm])
    titre_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, -1), 2, COULEUR_ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROUNDEDCORNERS', [4, 4, 0, 0]),
    ]))
    compteur = Table([[[
        P(f"<font color='#c0392b'><b>{total}</b></font>&nbsp;&nbsp;"
          f"<font size=9 color='#2c3e50'><b>{unite}</b></font>", 15, False, TA_CENTER),
        P(f"Édité le {_maintenant().strftime('%d/%m/%Y à %H:%M')}", 6.5, False, TA_CENTER, COULEUR_DISCRET),
    ]]], colWidths=[62 * mm])
    compteur.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, COULEUR_PRIMAIRE),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    bas = _sans_marges(Table([[titre_t, '', compteur]], colWidths=[150 * mm, LARGEUR - 212 * mm, 62 * mm]))
    return [haut, Spacer(1, 3 * mm), bas, Spacer(1, 3 * mm)]


def _bandeau_repartition(lignes):
    """lignes = [(titre, [(libellé, nombre, couleur), ...]), ...]"""
    morceaux = []
    for titre, items in lignes:
        items = [i for i in items if i[1]]
        if not items:
            continue
        puces = '&nbsp;&nbsp;&nbsp;'.join(
            f"<font size=9 color='{c}'>•</font>&nbsp;{escape(lib)}&nbsp;<b>{n}</b>" for lib, n, c in items)
        morceaux.append(f"<font color='#1a3a5c'><b>{escape(titre)} :</b></font>&nbsp;&nbsp;{puces}")
    if not morceaux:
        return []
    t = Table([[P('<br/>'.join(morceaux), 8)]], colWidths=[LARGEUR])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
        ('LINEBEFORE', (0, 0), (0, -1), 3, COULEUR_ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return [t, Spacer(1, 3 * mm)]


def _tableau(entetes, largeurs_mm, lignes, centrer=()):
    """entetes : libellés ; largeurs_mm : proportions ; centrer : index des colonnes centrées."""
    k = LARGEUR / (sum(largeurs_mm) * mm)
    data = [[P(f"<b>{escape(h)}</b>", 8, True, TA_CENTER, colors.white) for h in entetes]] + lignes
    t = Table(data, colWidths=[w * mm * k for w in largeurs_mm], repeatRows=1)
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, COULEUR_ACCENT),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COULEUR_GRIS]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, COULEUR_LIGNE),
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 5), ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 1), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    for i in centrer:
        cmds.append(('ALIGN', (i, 1), (i, -1), 'CENTER'))
    t.setStyle(TableStyle(cmds))
    return t


def _message_vide(texte):
    t = Table([[P(texte, 9.5, True, TA_CENTER, COULEUR_DISCRET)]], colWidths=[LARGEUR])
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#9aa7b4')),
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
        ('TOPPADDING', (0, 0), (-1, -1), 14), ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
    ]))
    return t


class _CanvasNumerote(rl_canvas.Canvas):
    """Pied de page avec le nombre total de pages (« Page 2 / 5 »)."""
    titre = ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for etat in self._pages:
            self.__dict__.update(etat)
            self.saveState()
            self.setStrokeColor(COULEUR_ACCENT)
            self.setLineWidth(0.8)
            self.line(MARGE, 9 * mm, PAGE_W - MARGE, 9 * mm)
            self.setFont('Helvetica', 6.5)
            self.setFillColor(COULEUR_DISCRET)
            self.drawString(MARGE, 5.5 * mm, f"Centre Auto La Prudence+ – {self.titre} – imprimé le "
                                             f"{_maintenant().strftime('%d/%m/%Y %H:%M')}")
            self.drawRightString(PAGE_W - MARGE, 5.5 * mm, f"Page {self._pageNumber} / {total}")
            self.restoreState()
            super().showPage()
        super().save()


def _construire(titre, elements):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), title=titre, author="Centre Auto La Prudence+",
        topMargin=8 * mm, bottomMargin=13 * mm, leftMargin=MARGE, rightMargin=MARGE,
    )
    doc.build(elements, canvasmaker=type('Canvas', (_CanvasNumerote,), {'titre': titre}))
    return buffer.getvalue()


def _nom_client(c):
    if c is None:
        return ''
    if c.type_client == 'PARTICULIER':
        return f"{c.prenom or ''} {c.nom or ''}".strip()
    return c.nom or ''


# ════════════════════════════════════════════════════════════════
#  LISTE DES VÉHICULES
# ════════════════════════════════════════════════════════════════
def _presence(v):
    local, atelier = getattr(v, 'en_local', False), getattr(v, 'en_atelier', False)
    if local and atelier:
        return "Local + Atelier", '#7c3aed'
    if local:
        return "Présent sur site", ROUGE
    if atelier:
        return "En atelier", ORANGE
    return "Hors garage", GRIS


def _echeance(date, today, ok, ko):
    if not date:
        return None
    if date < today:
        return ko, ROUGE, date.strftime('%d/%m/%Y')
    if (date - today).days <= 30:
        return "Bientôt", ORANGE, date.strftime('%d/%m/%Y')
    return ok, VERT, date.strftime('%d/%m/%Y')


def generer_pdf_liste_vehicules(qs, today=None):
    """Génère le PDF de la liste des véhicules (A4 paysage)."""
    today = today or timezone.localdate()
    if hasattr(qs, 'select_related'):
        qs = qs.select_related('client', 'client__parent')
    vehicules = list(qs)

    presences, assurances_exp, visites_exp = Counter(), 0, 0
    lignes = []
    for v in vehicules:
        lib, coul = _presence(v)
        presences[(lib, coul)] += 1

        # Véhicule
        modele = _txt(f"{v.marque or ''} {v.modele or ''}".strip()) or '—'
        details = " · ".join(x for x in [str(v.annee or ''), _txt(getattr(v, 'couleur', ''))] if x)
        veh = f"<b>{modele}</b>" + (f"<br/><font size=6.5 color='#6b7280'>{details}</font>" if details else '')

        # Propriétaire (entreprise + centre si c'est un centre)
        c = v.client
        if c is None:
            prop = _vide_cell()
        else:
            parent = getattr(c, 'parent', None)
            nom = _txt(parent.nom if parent else _nom_client(c))
            sous = [f"Centre : {_txt(c.nom)}" if parent else '', _txt(c.telephone)]
            prop = P(f"<b>{nom}</b>" + ''.join(
                f"<br/><font size=6.5 color='#6b7280'>{s}</font>" for s in sous if s))

        # Carburant
        try:
            carb = v.get_type_carburant_display() if v.type_carburant not in (None, '', 'NON_DEFINI') else ''
        except Exception:
            carb = v.type_carburant or ''

        # Assurance / visite
        ass = _echeance(v.expiry_assurance, today, "Valide", "Expirée")
        vis = _echeance(v.date_visite, today, "OK", "À renouveler")
        if ass and ass[0] == "Expirée":
            assurances_exp += 1
        if vis and vis[0] == "À renouveler":
            visites_exp += 1

        nb = getattr(v, 'nb_passages', None)
        if nb is None:
            nb = v.entrees.count() if hasattr(v, 'entrees') else 0

        lignes.append([
            _badge(lib, coul),
            P(f"<b>{_txt(v.immatriculation) or '—'}</b>", 8.5, True, TA_CENTER, COULEUR_PRIMAIRE),
            P(veh),
            prop,
            P(_txt(carb)) if carb else _vide_cell(),
            _badge(*ass) if ass else _vide_cell(),
            _badge(*vis) if vis else _vide_cell(),
            P(f"<b>{nb}</b>", 9, True, TA_CENTER, COULEUR_PRIMAIRE if nb else COULEUR_DISCRET),
        ])

    titre = "Liste des véhicules"
    elements = _entete(titre.upper(), len(vehicules), "véhicule(s)")
    elements += _bandeau_repartition([
        ("Présence", [(lib, n, c) for (lib, c), n in presences.most_common()]),
        ("Alertes", [("Assurances expirées", assurances_exp, ROUGE),
                     ("Visites techniques à renouveler", visites_exp, ORANGE)]),
    ])
    if lignes:
        elements.append(_tableau(
            ['Présence', 'Immatriculation', 'Véhicule', 'Propriétaire', 'Carburant',
             'Assurance', 'Visite technique', 'Passages'],
            [32, 30, 44, 50, 22, 28, 30, 18], lignes, centrer=(4, 7)))
    else:
        elements.append(_message_vide("Aucun véhicule ne correspond à ces critères."))
    return _construire(titre, elements)

