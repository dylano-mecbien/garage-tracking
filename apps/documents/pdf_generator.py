"""
Générateur PDF - Devis, Factures, Bons de sortie
Charte « CENTRE AUTO La PRUDENCE+ » : logo, bandeau titre bleu souligné orange,
encadré référence, sections à liseré orange, pied de page numéroté.
"""
from io import BytesIO
import logging
import re
from html import escape

from reportlab.graphics.shapes import Drawing, Ellipse, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
from django.utils import timezone


COULEUR_PRIMAIRE = colors.HexColor('#1a3a5c')
COULEUR_ACCENT = colors.HexColor('#e67e22')
COULEUR_GRIS = colors.HexColor('#f5f5f5')
COULEUR_TEXTE = colors.HexColor('#2c3e50')

COULEUR_VALIDE_BG = colors.HexColor('#d1fae5')
COULEUR_VALIDE_TEXTE = colors.HexColor('#065f46')
COULEUR_APPROBATION_BG = colors.HexColor('#fef3c7')
COULEUR_APPROBATION_TEXTE = colors.HexColor('#92400e')
COULEUR_CREER_BG = colors.HexColor('#e5e7eb')
COULEUR_CREER_TEXTE = colors.HexColor('#374151')

COULEUR_DISCRET = colors.HexColor('#6b7280')
COULEUR_BORDURE = colors.HexColor('#d5dbe1')

SERVICES = ("Tôlerie – Peinture – Freinage – Chaudronnerie – Mécanique Générale<br/>"
            "Électricité – Climatisation – Pneumatique – Tapisserie – Sérigraphie")
ADRESSE = "BP : 9060 Douala – Tél : (+237) 650 99 75 09"

MARGE = 12 * mm
LARGEUR = A4[0] - 2 * MARGE   # 186 mm


# ════════════════════════════════════════════════════════════════
#  Utilitaires
# ════════════════════════════════════════════════════════════════
class BottomSpacer(Flowable):
    """Pousse le contenu suivant vers le bas de la page courante."""

    def __init__(self, reserve=85 * mm):
        Flowable.__init__(self)
        self.reserve = reserve

    def wrap(self, availWidth, availHeight):
        h = max(0, availHeight - self.reserve)
        return (availWidth, h)

    def draw(self):
        pass


def format_datetime(dt):
    if not dt:
        return "—"
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime('%d/%m/%Y %H:%M')


def _txt(v):
    return escape(str(v)) if v not in (None, '') else ''


def _P(texte, size=8.5, bold=False, align=TA_LEFT, color=COULEUR_TEXTE, leading=None):
    return Paragraph(texte or '', ParagraphStyle(
        '', fontName='Helvetica-Bold' if bold else 'Helvetica', fontSize=size,
        leading=leading or size * 1.3, alignment=align, textColor=color))


def _sans_marges(t, valign='MIDDLE'):
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), valign),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def _logo(largeur=58 * mm, hauteur=20 * mm):
    d = Drawing(largeur, hauteur)
    d.add(String(largeur / 2, hauteur - 6 * mm, "CENTRE AUTO", fontName='Helvetica-Bold',
                 fontSize=10.5, fillColor=COULEUR_PRIMAIRE, textAnchor='middle'))
    d.add(Ellipse(largeur / 2, hauteur / 2 - 3 * mm, largeur / 2 - 1, 6.2 * mm,
                  fillColor=COULEUR_PRIMAIRE, strokeColor=COULEUR_ACCENT, strokeWidth=1.2))
    d.add(String(largeur / 2, hauteur / 2 - 2.4 * mm, "La PRUDENCE+", fontName='Helvetica-Bold',
                 fontSize=13.5, fillColor=colors.white, textAnchor='middle'))
    d.add(String(largeur / 2, hauteur / 2 - 6.4 * mm, "Véhicules Légers / Poids Lourds",
                 fontName='Helvetica-Oblique', fontSize=6.3, fillColor=colors.white, textAnchor='middle'))
    return d


# ════════════════════════════════════════════════════════════════
#  Briques de mise en page (aussi utilisées par devis / factures)
# ════════════════════════════════════════════════════════════════
def _badge_etat(etat):
    if etat == 'VALIDER':
        texte, bg, fg = "VALIDÉ", COULEUR_VALIDE_BG, COULEUR_VALIDE_TEXTE
    elif etat == 'APPROBATION':
        texte, bg, fg = "EN ATTENTE D'APPROBATION", COULEUR_APPROBATION_BG, COULEUR_APPROBATION_TEXTE
    else:
        texte, bg, fg = "EN ATTENTE DE VALIDATION", COULEUR_CREER_BG, COULEUR_CREER_TEXTE

    t = Table([[_P(f"<font size=13>•</font>&nbsp;&nbsp;{escape(texte)}", 9.5, True, TA_CENTER, fg)]],
              colWidths=[78 * mm], hAlign='RIGHT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('BOX', (0, 0), (-1, -1), 0.8, fg),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),
    ]))
    return t


def _header_table(titre, numero, date, vehicule=None, client=None):
    """En-tête complet : logo + services, bandeau titre + encadré N°/date, bande véhicule/client."""
    haut = _sans_marges(Table([[
        _logo(),
        _P(f"<b>{SERVICES}</b><br/><font color='#e67e22'><b>{ADRESSE}</b></font>",
           7.8, False, TA_CENTER, COULEUR_PRIMAIRE),
    ]], colWidths=[62 * mm, LARGEUR - 62 * mm]))

    bandeau = Table([[_P(f"<b>{escape(titre)}</b>", 15, True, TA_LEFT, colors.white)]],
                    colWidths=[112 * mm])
    bandeau.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, -1), 2.5, COULEUR_ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('ROUNDEDCORNERS', [4, 4, 0, 0]),
    ]))
    reference = Table([
        [_P("N°", 7, False, TA_LEFT, COULEUR_DISCRET),
         _P(f"<b>{_txt(numero) or '—'}</b>", 11, True, TA_RIGHT, colors.HexColor('#c0392b'))],
        [_P("Créé le", 7, False, TA_LEFT, COULEUR_DISCRET),
         _P(f"<b>{format_datetime(date)}</b>", 8, True, TA_RIGHT)],
    ], colWidths=[18 * mm, 48 * mm])
    reference.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1, COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, 0), 0.3, COULEUR_BORDURE),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    milieu = _sans_marges(Table([[bandeau, '', reference]],
                                colWidths=[112 * mm, LARGEUR - 178 * mm, 66 * mm]))

    lignes = [haut, Spacer(1, 3 * mm), milieu]

    if vehicule or client:
        gauche = droite = ''
        if vehicule:
            modele = _txt(f"{vehicule.marque or ''} {vehicule.modele or ''}".strip())
            gauche = (f"<font color='#6b7280'>Véhicule</font>&nbsp;&nbsp;"
                      f"<font color='#1a3a5c'><b>{_txt(vehicule.immatriculation)}</b></font>"
                      + (f"&nbsp;·&nbsp;{modele}" if modele else ''))
        if client:
            droite = f"<font color='#6b7280'>Client</font>&nbsp;&nbsp;<b>{_txt(client)}</b>"
        bande = Table([[_P(gauche, 8.5), _P(droite, 8.5, align=TA_RIGHT)]],
                      colWidths=[LARGEUR / 2, LARGEUR / 2])
        bande.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
            ('LINEBEFORE', (0, 0), (0, -1), 3, COULEUR_ACCENT),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        lignes += [Spacer(1, 3 * mm), bande]

    return _sans_marges(Table([[x] for x in lignes], colWidths=[LARGEUR]), valign='TOP')


def _section_titre(texte, largeur=LARGEUR):
    t = Table([[_P(f"<b>{escape(texte).upper()}</b>", 9, True, TA_LEFT, COULEUR_PRIMAIRE)]],
              colWidths=[largeur])
    t.setStyle(TableStyle([
        ('LINEBEFORE', (0, 0), (0, 0), 3, COULEUR_ACCENT),
        ('LINEBELOW', (0, 0), (-1, -1), 0.6, COULEUR_PRIMAIRE),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _info_simple_table(rows, largeur=LARGEUR, largeur_label=None):
    """Tableau libellé / valeur. `rows` = [(libellé, valeur), ...]."""
    largeur_label = largeur_label or min(50 * mm, largeur * 0.38)
    data = [[
        _P(escape(str(label)), 7.8, False, TA_LEFT, COULEUR_DISCRET),
        _P(f"<b>{_txt(valeur) or '—'}</b>", 8.3, True),
    ] for label, valeur in rows] or [[_P('—'), _P('—')]]
    t = Table(data, colWidths=[largeur_label, largeur - largeur_label])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), COULEUR_GRIS),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, COULEUR_BORDURE),
        ('BOX', (0, 0), (-1, -1), 0.6, COULEUR_BORDURE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _description_verticale(label, contenu, largeur=LARGEUR):
    data = []
    if label:
        data.append([_P(f"<b>{escape(label)}</b>", 8.5, True, TA_LEFT, COULEUR_PRIMAIRE)])

    if isinstance(contenu, (list, tuple)):
        if contenu:
            for i, item in enumerate(contenu, 1):
                data.append([_P(f"<font color='#e67e22'><b>{i}.</b></font>&nbsp;&nbsp;{_txt(item)}", 8.5)])
        else:
            data.append([_P("—", 8.5, color=COULEUR_DISCRET)])
    else:
        texte = _txt(contenu).replace('\n', '<br/>') if contenu else '—'
        data.append([_P(texte, 8.5, leading=12)])

    t = Table(data, colWidths=[largeur])
    cmds = [
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
        ('LINEBEFORE', (0, 0), (0, -1), 2, COULEUR_ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, 0), 6), ('BOTTOMPADDING', (0, -1), (-1, -1), 6),
    ]
    if isinstance(contenu, (list, tuple)) and len(contenu) > 1:
        start = 1 if label else 0
        cmds.append(('LINEBELOW', (0, start), (-1, -2), 0.3, COULEUR_BORDURE))
    t.setStyle(TableStyle(cmds))
    return t


def _parse_articles(texte):
    if not texte:
        return []
    items = re.split(r'[;\n]+', texte)
    return [item.strip() for item in items if item.strip()]


def _signature_image(signature_field, width=60 * mm, height=26 * mm):
    if not signature_field:
        return None
    try:
        if not getattr(signature_field, 'name', None):
            return None
        signature_field.open('rb')
        try:
            data = signature_field.read()
        finally:
            signature_field.close()
        if not data:
            logging.warning("Signature vide : %s", signature_field.name)
            return None
        img = Image(BytesIO(data))
        # Respecte les proportions dans le cadre width × height
        ratio = min(width / img.imageWidth, height / img.imageHeight)
        img.drawWidth, img.drawHeight = img.imageWidth * ratio, img.imageHeight * ratio
        return img
    except FileNotFoundError:
        logging.warning("Signature introuvable : %s", getattr(signature_field, 'name', '?'))
        return None
    except Exception as e:
        logging.warning("Impossible de charger la signature %s : %s",
                        getattr(signature_field, 'name', '?'), e)
        return None


def _cadre_signature(titre, image, nom, largeur):
    zone = image if image else Spacer(1, 26 * mm)
    t = Table([
        [_P(f"<b>{escape(titre)}</b>", 8.5, True, TA_CENTER, colors.white)],
        [zone],
        [_P(f"<b>{_txt(nom) or '—'}</b>", 8.3, True, TA_CENTER)],
        [_P("Nom, date et signature", 6.5, False, TA_CENTER, COULEUR_DISCRET)],
    ], colWidths=[largeur], rowHeights=[None, 28 * mm, None, None])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, COULEUR_ACCENT),
        ('BOX', (0, 0), (-1, -1), 0.8, COULEUR_PRIMAIRE),
        ('LINEBELOW', (0, 1), (-1, 1), 0.5, COULEUR_BORDURE, 0, (2, 2)),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 1), (-1, 1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 4), ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        ('TOPPADDING', (0, 2), (-1, -1), 2), ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
    ]))
    return t


def _bloc_signatures(bon):
    """
    Deux cadres côte à côte : garage à gauche, client / demandeur à droite.
    - VEHICULE : garage = approuvé par, signatures admin et client
    - DIVERS   : garage = validé par, le cadre client reste vierge pour signer à la main
    """
    if bon.types == 'VEHICULE':
        nom_admin = bon.approuve_par.full_name if bon.approuve_par else ""
        img_client = _signature_image(getattr(bon, 'signature_client', None))
    else:
        nom_admin = bon.valide_par.full_name if bon.valide_par else ""
        img_client = None

    largeur = (LARGEUR - 10 * mm) / 2
    t = Table([[
        _cadre_signature("Signature Garage", _signature_image(bon.signature_admin), nom_admin, largeur),
        '',
        _cadre_signature("Signature Client", img_client, bon.nom_demandeur, largeur),
    ]], colWidths=[largeur, 10 * mm, largeur])
    return _sans_marges(t, valign='TOP')


def _add_row(rows, label, value, default=None):
    if value not in (None, "", []):
        rows.append((label, value))
    elif default is not None:
        rows.append((label, default))


def _pied_de_page(texte):
    def dessiner(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(COULEUR_ACCENT)
        canvas.setLineWidth(0.8)
        canvas.line(MARGE, 10 * mm, A4[0] - MARGE, 10 * mm)
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(COULEUR_DISCRET)
        canvas.drawString(MARGE, 6.5 * mm, f"Centre Auto La Prudence+ – {texte} – généré le "
                                          f"{format_datetime(timezone.now())}")
        canvas.drawRightString(A4[0] - MARGE, 6.5 * mm, f"Page {doc.page}")
        canvas.restoreState()
    return dessiner


# ════════════════════════════════════════════════════════════════
#  BON DE SORTIE
# ════════════════════════════════════════════════════════════════
def generer_pdf_bon_sortie(bon):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=f"Bon de sortie {bon.numero}", author="Centre Auto La Prudence+",
        topMargin=10 * mm, bottomMargin=15 * mm, leftMargin=MARGE, rightMargin=MARGE,
    )
    elements = []

    vehicule = bon.vehicule if bon.types == 'VEHICULE' and bon.vehicule else None
    client = vehicule.client if vehicule else None

    elements.append(_header_table(
        titre="BON DE SORTIE",
        numero=bon.numero,
        date=bon.created_at,
        vehicule=vehicule,
        client=client,
    ))
    elements.append(Spacer(1, 4 * mm))
    elements.append(_badge_etat(getattr(bon, 'etats', 'CREER')))
    elements.append(Spacer(1, 4 * mm))

    # ── Informations ──
    info_rows = [
        ("Type", "Véhicule" if bon.types == 'VEHICULE' else "Divers"),
        ("Demandeur", bon.nom_demandeur or "—"),
        ("Créé par", bon.cree_par.full_name if bon.cree_par else "—"),
    ]
    if bon.types == 'VEHICULE':
        entree = bon.entrees_liees.first()
        if entree:
            info_rows.append(("Date entrée", format_datetime(entree.date_entree)))
            info_rows.append(("Date sortie", format_datetime(entree.date_sortie)))
    if bon.est_valide:
        if bon.types == 'DIVERS':
            info_rows.append(("Validé par", bon.valide_par.full_name if bon.valide_par else "—"))
        else:
            info_rows.append(("Approuvé par", bon.approuve_par.full_name if bon.approuve_par else "—"))

    if vehicule:
        # Informations | Véhicule côte à côte
        v = vehicule
        vehicule_rows = [
            ("Immatriculation", v.immatriculation),
            ("Marque / Modèle", f"{v.marque or ''} {v.modele or ''}".strip()),
        ]
        _add_row(vehicule_rows, "Année", v.annee)
        _add_row(vehicule_rows, "Couleur", v.couleur)
        _add_row(vehicule_rows, "Propriétaire", str(v.client) if v.client else "", default="—")
        _add_row(vehicule_rows, "Téléphone", v.client.telephone if v.client else "", default="—")

        col = (LARGEUR - 6 * mm) / 2
        bloc = Table([[
            [_section_titre("Informations", col), Spacer(1, 2 * mm),
             _info_simple_table(info_rows, col, 30 * mm)],
            '',
            [_section_titre("Véhicule", col), Spacer(1, 2 * mm),
             _info_simple_table(vehicule_rows, col, 30 * mm)],
        ]], colWidths=[col, 6 * mm, col])
        elements.append(_sans_marges(bloc, valign='TOP'))
        elements.append(Spacer(1, 5 * mm))

        if bon.observations:
            elements.append(_section_titre("Observations"))
            elements.append(Spacer(1, 2 * mm))
            elements.append(_description_verticale("", bon.observations))
            elements.append(Spacer(1, 4 * mm))
    else:
        elements.append(_section_titre("Informations"))
        elements.append(Spacer(1, 2 * mm))
        elements.append(_info_simple_table(info_rows))
        elements.append(Spacer(1, 5 * mm))

        if bon.types == 'DIVERS':
            elements.append(_section_titre("Objet / Matériel"))
            elements.append(Spacer(1, 2 * mm))
            elements.append(_description_verticale("Description", _parse_articles(bon.observations)))
            elements.append(Spacer(1, 4 * mm))

    # ── Signatures en bas de page (toujours présentes, pour signer à la main si besoin) ──
    elements.append(BottomSpacer(reserve=62 * mm))
    elements.append(_bloc_signatures(bon))

    pied = _pied_de_page(f"Bon de sortie N° {bon.numero}")
    doc.build(elements, onFirstPage=pied, onLaterPages=pied)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
