"""
Générateur PDF - Devis, Factures, Bons de sortie
"""
from io import BytesIO
import logging
import os
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, Image, Flowable,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
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


def _badge_etat(etat):
    if etat == 'VALIDER':
        texte, bg, fg = "✔  VALIDÉ", COULEUR_VALIDE_BG, COULEUR_VALIDE_TEXTE
    elif etat == 'APPROBATION':
        texte, bg, fg = "EN ATTENTE D'APPROBATION", COULEUR_APPROBATION_BG, COULEUR_APPROBATION_TEXTE
    else:
        texte, bg, fg = "EN ATTENTE DE VALIDATION", COULEUR_CREER_BG, COULEUR_CREER_TEXTE

    style = ParagraphStyle(
        '', alignment=TA_CENTER, fontName='Helvetica-Bold',
        fontSize=10, textColor=fg, leading=13
    )
    t = Table([[Paragraph(texte, style)]], colWidths=[75 * mm], hAlign='RIGHT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    return t


def _header_table(titre, numero, date, vehicule=None, client=None):
    styles = getSampleStyleSheet()

    ligne_vehicule = (
        f"<b>Véhicule:</b> {vehicule.immatriculation} - {vehicule.marque} {vehicule.modele}"
        if vehicule else ""
    )
    ligne_client = f"<b>Client:</b> {client}" if client else ""

    data = [
        [
            Paragraph(
                "<b><font size=14 color='#1a3a5c'>CENTRE AUTO LA PRUDENCE +</font></b>",
                styles['Normal']
            ),
            Paragraph(
                f"<b><font size=16 color='#e67e22'>{titre}</font></b>",
                ParagraphStyle('', alignment=TA_RIGHT)
            ),
        ],
        [
            Paragraph(
                "BP 9060 - Douala, Cameroun<br/>Tél: +237 650 99 75 09",
                styles['Normal']
            ),
            Paragraph(
                f"<b>N°:</b> {numero}<br/><b>Date de Création:</b> {format_datetime(date)}",
                ParagraphStyle('', alignment=TA_RIGHT)
            ),
        ],
        [
            Paragraph(ligne_vehicule, styles['Normal']),
            Paragraph(ligne_client, ParagraphStyle('', alignment=TA_RIGHT)),
        ],
    ]
    t = Table(data, colWidths=[95 * mm, 95 * mm])
    t.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, -1), (-1, -1), 1, COULEUR_PRIMAIRE),
    ]))
    return t


def _section_titre(texte):
    style = ParagraphStyle(
        '', fontSize=11.5, fontName='Helvetica-Bold',
        textColor=COULEUR_PRIMAIRE, leftIndent=8, spaceAfter=0
    )
    t = Table([[Paragraph(texte, style)]], colWidths=[186 * mm])
    t.setStyle(TableStyle([
        ('LINEBEFORE', (0, 0), (0, 0), 3, COULEUR_ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def _info_simple_table(rows):
    label_style = ParagraphStyle(
        '', fontSize=8, fontName='Helvetica-Bold',
        textColor=COULEUR_TEXTE, leading=10
    )
    value_style = ParagraphStyle(
        '', fontSize=8, textColor=COULEUR_TEXTE, leading=10
    )
    data = []
    for label, valeur in rows:
        data.append([
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph(str(valeur) if valeur else "—", value_style),
        ])
    t = Table(data, colWidths=[50 * mm, 136 * mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#e2e2e2')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, COULEUR_GRIS]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _description_verticale(label, contenu):
    label_style = ParagraphStyle(
        '', fontName='Helvetica-Bold', fontSize=9.5,
        textColor=COULEUR_PRIMAIRE, spaceAfter=2
    )
    texte_style = ParagraphStyle(
        '', fontSize=8, textColor=COULEUR_TEXTE, leading=11
    )
    item_style = ParagraphStyle(
        '', fontSize=8, textColor=COULEUR_TEXTE, leading=11,
        spaceAfter=1, leftIndent=4
    )

    data = [[Paragraph(label, label_style)]] if label else []

    if isinstance(contenu, (list, tuple)):
        if contenu:
            for i, item in enumerate(contenu, 1):
                data.append([Paragraph(f"{i}. {item}", item_style)])
        else:
            data.append([Paragraph("—", texte_style)])
    else:
        data.append([Paragraph(contenu if contenu else "—", texte_style)])

    t = Table(data, colWidths=[186 * mm])
    style_cmds = [
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
    ]
    if label:
        style_cmds.append(('TOPPADDING', (0, 0), (0, 0), 5))
        style_cmds.append(('TOPPADDING', (0, 1), (0, 1), 1))
    t.setStyle(TableStyle(style_cmds))
    return t


def _parse_articles(texte):
    if not texte:
        return []
    items = re.split(r'[;\n]+', texte)
    return [item.strip() for item in items if item.strip()]


def _signature_image(signature_field, width=65 * mm, height=38 * mm):
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

        return Image(BytesIO(data), width=width, height=height)

    except FileNotFoundError:
        logging.warning(
            "Signature introuvable : %s",
            getattr(signature_field, 'name', '?')
        )
        return None
    except Exception as e:
        logging.warning(
            "Impossible de charger la signature %s : %s",
            getattr(signature_field, 'name', '?'), e,
        )
        return None

def _bloc_signatures(bon):
    """
    Affiche les signatures :
    - VEHICULE : garage à gauche, client à droite
    - DIVERS   : admin à droite uniquement
    """
    nom_style = ParagraphStyle(
        '', fontSize=8, alignment=TA_CENTER,
        textColor=COULEUR_TEXTE, spaceBefore=2
    )
    titre_style = ParagraphStyle(
        '', fontSize=9, fontName='Helvetica-Bold',
        alignment=TA_CENTER, textColor=COULEUR_PRIMAIRE
    )

    if bon.types == 'VEHICULE':
        nom_admin = bon.approuve_par.full_name if bon.approuve_par else "—"
    else:
        nom_admin = bon.valide_par.full_name if bon.valide_par else "—"

    nom_client = bon.nom_demandeur or "—"

    img_admin = _signature_image(bon.signature_admin)
    img_client = _signature_image(getattr(bon, 'signature_client', None))

    cell_gauche = []
    cell_droite = []

    if bon.types == 'VEHICULE':
        # Gauche = garage / admin
        cell_gauche.append(Paragraph("Signature Garage", titre_style))
        if img_admin:
            cell_gauche.append(img_admin)
        else:
            cell_gauche.append(Spacer(1, 22 * mm))
        cell_gauche.append(Paragraph(nom_admin, nom_style))

        # Droite = client
        cell_droite.append(Paragraph("Signature Client", titre_style))
        if img_client:
            cell_droite.append(img_client)
        else:
            cell_droite.append(Spacer(1, 22 * mm))
        cell_droite.append(Paragraph(nom_client, nom_style))

        data = [[cell_gauche, cell_droite]]
        t = Table(data, colWidths=[93 * mm, 93 * mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        return t

    else:
        # DIVERS → uniquement admin à droite
        cell_gauche.append(Paragraph("Signature Garage", titre_style))
        cell_droite.append(Paragraph("Signature Client", titre_style))
        if img_admin:
            cell_gauche.append(img_admin)
        else:
            cell_gauche.append(Spacer(1, 20 * mm))
        cell_gauche.append(Paragraph(nom_admin, nom_style))

        data = [[cell_gauche, cell_droite]]
        t = Table(data, colWidths=[90 * mm, 93 * mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        return t
    

def _add_row(rows, label, value, default=None):
    if value not in (None, "", []):
        rows.append((label, value))
    elif default is not None:
        rows.append((label, default))


def generer_pdf_bon_sortie(bon):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=12 * mm, bottomMargin=12 * mm,
        leftMargin=12 * mm, rightMargin=12 * mm,
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
    elements.append(Spacer(1, 3 * mm))

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
            info_rows.append(
                ("Validé par", bon.valide_par.full_name if bon.valide_par else "—")
            )
        else:
            info_rows.append(
                ("Approuvé par", bon.approuve_par.full_name if bon.approuve_par else "—")
            )

    elements.append(_section_titre("Informations"))
    elements.append(Spacer(1, 2 * mm))
    elements.append(_info_simple_table(info_rows))
    elements.append(Spacer(1, 4 * mm))

    # ── Véhicule ou Divers ──
    if bon.types == 'VEHICULE' and bon.vehicule:
        v = bon.vehicule
        vehicule_rows = [
            ("Immatriculation", v.immatriculation),
            ("Marque / Modèle", f"{v.marque} {v.modele}"),
        ]
        _add_row(vehicule_rows, "Année", v.annee)
        _add_row(vehicule_rows, "Couleur", v.couleur)
        _add_row(
            vehicule_rows, "Propriétaire",
            str(v.client) if v.client else "", default="—"
        )
        _add_row(
            vehicule_rows, "Téléphone",
            v.client.telephone if v.client else "", default="—"
        )

        elements.append(_section_titre("Véhicule"))
        elements.append(Spacer(1, 2 * mm))
        elements.append(_info_simple_table(vehicule_rows))
        elements.append(Spacer(1, 4 * mm))

    elif bon.types == 'DIVERS':
        elements.append(_section_titre("Objet / Matériel"))
        elements.append(Spacer(1, 2 * mm))
        articles = _parse_articles(bon.observations)
        elements.append(_description_verticale("Description", articles))
        elements.append(Spacer(1, 3 * mm))


    # ── Observations (VEHICULE uniquement) ──
    if bon.observations and bon.types == 'VEHICULE':
        elements.append(_section_titre("Observations"))
        elements.append(Spacer(1, 2 * mm))
        elements.append(_description_verticale("", bon.observations))
        elements.append(Spacer(1, 4 * mm))

    # ── Signatures en bas de page ──
    if bon.signature_admin or getattr(bon, 'signature_client', None):
        
        elements.append(BottomSpacer(reserve=85 * mm))

      
        elements.append(Spacer(1, 3 * mm))
        elements.append(_bloc_signatures(bon))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes