"""
Générateur PDF - Devis, Factures, Bons de sortie
"""
from io import BytesIO
import logging
from venv import logger
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                Spacer, HRFlowable, Image)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from django.utils import timezone
import os


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

    style = ParagraphStyle('', alignment=TA_CENTER, fontName='Helvetica-Bold',
                           fontSize=10, textColor=fg, leading=13)
    t = Table([[Paragraph(texte, style)]], colWidths=[75 * mm], hAlign='RIGHT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
    ]))
    return t


def _header_table(titre, numero, date, vehicule=None, client=None):
    styles = getSampleStyleSheet()

    ligne_vehicule = f"<b>Véhicule:</b> {vehicule.immatriculation} - {vehicule.marque} {vehicule.modele}" if vehicule else ""
    ligne_client = f"<b>Client:</b> {client}" if client else ""

    data = [
        [Paragraph("<b><font size=14 color='#1a3a5c'>CENTRE AUTO LA PRUDENCE +</font></b>", styles['Normal']),
         Paragraph(f"<b><font size=16 color='#e67e22'>{titre}</font></b>", ParagraphStyle('', alignment=TA_RIGHT))],
        [Paragraph("BP 9060 - Douala, Cameroun<br/>Tél: +237 650 99 75 09", styles['Normal']),
         Paragraph(f"<b>N°:</b> {numero}<br/><b>Date de Création:</b> {format_datetime(date)}", ParagraphStyle('', alignment=TA_RIGHT))],
        [Paragraph(ligne_vehicule, styles['Normal']),
         Paragraph(ligne_client, ParagraphStyle('', alignment=TA_RIGHT))],
    ]
    t = Table(data, colWidths=[95 * mm, 95 * mm])
    t.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1, COULEUR_PRIMAIRE),
    ]))
    return t


def _section_titre(texte):
    style = ParagraphStyle('', fontSize=11.5, fontName='Helvetica-Bold',
                           textColor=COULEUR_PRIMAIRE, leftIndent=8, spaceAfter=0)
    t = Table([[Paragraph(texte, style)]], colWidths=[180 * mm])
    t.setStyle(TableStyle([
        ('LINEBEFORE', (0, 0), (0, 0), 3, COULEUR_ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def _info_simple_table(rows):
    styles = getSampleStyleSheet()
    data = []
    for label, valeur in rows:
        data.append([
            Paragraph(f"<b>{label}</b>", styles['Normal']),
            Paragraph(str(valeur) if valeur else "—", styles['Normal']),
        ])
    t = Table(data, colWidths=[55 * mm, 135 * mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#e2e2e2')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, COULEUR_GRIS]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
    ]))
    return t


def _description_verticale(label, contenu):
    styles = getSampleStyleSheet()
    label_style = ParagraphStyle('', fontName='Helvetica-Bold', fontSize=9.5,
                                 textColor=COULEUR_PRIMAIRE, spaceAfter=4)
    texte_style = ParagraphStyle('', fontSize=10, textColor=COULEUR_TEXTE, leading=14)
    item_style = ParagraphStyle('', fontSize=10, textColor=COULEUR_TEXTE, leading=14,
                                spaceAfter=3, leftIndent=4)

    data = [[Paragraph(label, label_style)]] if label else []

    if isinstance(contenu, (list, tuple)):
        if contenu:
            for i, item in enumerate(contenu, 1):
                data.append([Paragraph(f"{i}. {item}", item_style)])
        else:
            data.append([Paragraph("—", texte_style)])
    else:
        data.append([Paragraph(contenu if contenu else "—", texte_style)])

    t = Table(data, colWidths=[190 * mm])
    style_cmds = [
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
    ]
    if label:
        style_cmds.append(('TOPPADDING', (0, 0), (0, 0), 8))
        style_cmds.append(('TOPPADDING', (0, 1), (0, 1), 2))
    t.setStyle(TableStyle(style_cmds))
    return t


def _parse_articles(texte):
    if not texte:
        return []
    import re
    items = re.split(r'[;\n]+', texte)
    return [item.strip() for item in items if item.strip()]

def _signature_image(signature_field, width=55 * mm, height=28 * mm):
    """
    Retourne un objet Image ReportLab à partir d'un ImageField/FileField,
    compatible stockage local ET MinIO/S3.
    """
    if not signature_field:
        return None

    try:
        # Vérifier que le fichier existe (compatible MinIO)
        # `.name` vide = pas de fichier
        if not getattr(signature_field, 'name', None):
            return None

        # Ouvrir via le storage Django (local OU MinIO)
        signature_field.open('rb')
        try:
            data = signature_field.read()
        finally:
            signature_field.close()

        if not data:
            logging.warning("Signature vide : %s", signature_field.name)
            return None

        # ReportLab accepte un file-like object
        return Image(BytesIO(data), width=width, height=height)

    except FileNotFoundError:
        logging.warning("Signature introuvable : %s", getattr(signature_field, 'name', '?'))
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
    - VEHICULE : client à gauche, admin à droite
    - DIVERS   : admin à droite uniquement
    """
    styles = getSampleStyleSheet()
    nom_style = ParagraphStyle('', fontSize=9, alignment=TA_CENTER,
                               textColor=COULEUR_TEXTE, spaceBefore=3)
    titre_style = ParagraphStyle('', fontSize=9, fontName='Helvetica-Bold',
                                 alignment=TA_CENTER, textColor=COULEUR_PRIMAIRE)

    # Nom admin
    nom_admin = "—"
    if bon.types == 'VEHICULE' :
        nom_admin = bon.approuve_par.full_name if bon.approuve_par else "—"
    elif bon.types == 'DIVERS':
        nom_admin = bon.valide_par.full_name if bon.valide_par else "—"



    # Nom client
    nom_client = bon.nom_demandeur or "—"
  

    img_admin = _signature_image(bon.signature_admin)
    img_client = _signature_image(bon.signature_client)

    # Contenu gauche (client) et droite (admin)
    cell_gauche = []
    cell_droite = []

    if bon.types == 'VEHICULE':
        # Gauche = client
        cell_gauche.append(Paragraph("Signature Client", titre_style))
        if img_client:
            cell_gauche.append(img_client)
        else:
            cell_gauche.append(Spacer(1, 28 * mm))
        cell_gauche.append(Paragraph(nom_client, nom_style))

        # Droite = admin
        cell_droite.append(Paragraph("Signature Admin", titre_style))
        if img_admin:
            cell_droite.append(img_admin)
        else:
            cell_droite.append(Spacer(1, 28 * mm))
        cell_droite.append(Paragraph(nom_admin, nom_style))

        data = [[cell_gauche, cell_droite]]
        t = Table(data, colWidths=[95 * mm, 95 * mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t

    else:
        # DIVERS → uniquement admin à droite
        cell_droite.append(Paragraph("Signature Admin", titre_style))
        if img_admin:
            cell_droite.append(img_admin)
        else:
            cell_droite.append(Spacer(1, 28 * mm))
        cell_droite.append(Paragraph(nom_admin, nom_style))

        data = [[Spacer(1, 1), cell_droite]]
        t = Table(data, colWidths=[95 * mm, 95 * mm])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return t



def _add_row(rows, label, value, default=None):
    """Ajoute (label, value) si value est renseigné, sinon (label, default) si default fourni."""
    if value not in (None, "", []):
        rows.append((label, value))
    elif default is not None:
        rows.append((label, default))


def generer_pdf_bon_sortie(bon):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=15 * mm, bottomMargin=15 * mm,
        leftMargin=15 * mm, rightMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
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
    elements.append(Spacer(1, 5 * mm))

    elements.append(_badge_etat(getattr(bon, 'etats', 'CREER')))
    elements.append(Spacer(1, 7 * mm))

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
        else :
            info_rows.append(("Approuvé par", bon.approuve_par.full_name if bon.approuve_par else "—"))

    info_rows.append(("Validé le", format_datetime(bon.date_validation)))

    elements.append(_section_titre("Informations"))
    elements.append(Spacer(1, 3 * mm))
    elements.append(_info_simple_table(info_rows))
    elements.append(Spacer(1, 8 * mm))

    # ── Véhicule ou Divers ──
    if bon.types == 'VEHICULE' and bon.vehicule:
      
        v = bon.vehicule
        vehicule_rows = [
        ("Immatriculation", v.immatriculation),
        ("Marque / Modèle", f"{v.marque} {v.modele}"),
]

        _add_row(vehicule_rows, "Année", v.annee)
        _add_row(vehicule_rows, "Couleur", v.couleur)
        _add_row(vehicule_rows, "Carburant", v.get_type_carburant_display() if v.type_carburant else "")

        _add_row(vehicule_rows, "Propriétaire", str(v.client) if v.client else "", default="—")
        _add_row(vehicule_rows, "Téléphone", v.client.telephone if v.client else "", default="—")

        elements.append(_section_titre("Véhicule"))
        elements.append(Spacer(1, 3 * mm))
        elements.append(_info_simple_table(vehicule_rows))
        elements.append(Spacer(1, 8 * mm))
    elif bon.types == 'DIVERS':
        elements.append(_section_titre("Objet / Matériel"))
        elements.append(Spacer(1, 3 * mm))
        articles = _parse_articles(bon.observations)
        elements.append(_description_verticale("Description", articles))
        elements.append(Spacer(1, 4 * mm))
        origine = getattr(bon, 'Origine_demande', None)
        if origine:
            elements.append(_description_verticale("Origine de la demande", origine))
            elements.append(Spacer(1, 4 * mm))
        elements.append(Spacer(1, 4 * mm))

    # ── Observations (VEHICULE uniquement) ──
    if bon.observations and bon.types == 'VEHICULE':
        elements.append(_section_titre("Observations"))
        elements.append(Spacer(1, 3 * mm))
        elements.append(_description_verticale("", bon.observations))
        elements.append(Spacer(1, 8 * mm))

    # ── Signatures ──
    if bon.signature_admin or getattr(bon, 'signature_client', None):
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc')))
        elements.append(Spacer(1, 5 * mm))
        elements.append(_section_titre("Signatures"))
        elements.append(Spacer(1, 5 * mm))
        elements.append(_bloc_signatures(bon))

    # Plus de mention légale

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes