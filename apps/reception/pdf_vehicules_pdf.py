from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.lib import colors
from io import BytesIO
from django.utils import timezone
from apps.documents.pdf_generator import COULEUR_ACCENT, COULEUR_GRIS, COULEUR_PRIMAIRE, COULEUR_TEXTE, format_datetime




def generer_pdf_liste_vehicules(qs, today=None):
    """
    Génère un PDF de la liste des véhicules (portrait A4).
    """
    from django.utils import timezone
    if today is None:
        today = timezone.localdate()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=portrait(A4),
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
    )
    elements = []

    titre_style = ParagraphStyle(
        '', fontSize=16, fontName='Helvetica-Bold',
        textColor=COULEUR_ACCENT, alignment=TA_RIGHT
    )
    nom_style = ParagraphStyle(
        '', fontSize=13, fontName='Helvetica-Bold',
        textColor=COULEUR_PRIMAIRE
    )
    sub_style = ParagraphStyle(
        '', fontSize=8, textColor=colors.HexColor('#666666'), leading=11
    )
    meta_style = ParagraphStyle(
        '', fontSize=8, textColor=colors.HexColor('#555555'),
        alignment=TA_RIGHT, leading=11
    )
    cell = ParagraphStyle('', fontSize=7, textColor=COULEUR_TEXTE, leading=9)
    cell_head = ParagraphStyle(
        '', fontSize=7, fontName='Helvetica-Bold',
        textColor=colors.white, leading=9
    )

    now_str = format_datetime(timezone.now())
    total = qs.count()

    header_data = [
        [
            Paragraph("CENTRE AUTO LA PRUDENCE +", nom_style),
            Paragraph("LISTE DES VÉHICULES", titre_style),
        ],
        [
            Paragraph("BP 9060 — Douala, Cameroun<br/>Tél : +237 650 99 75 09", sub_style),
            Paragraph(f"Export du {now_str}<br/>Total : <b>{total}</b> véhicule(s)", meta_style),
        ],
    ]
    header = Table(header_data, colWidths=[100 * mm, 90 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, COULEUR_PRIMAIRE),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 5 * mm))

    head = ['Présence', 'Immat.', 'Véhicule', 'Propriétaire', 'Carburant', 'Assurance', 'Visite tech.', 'Passages']
    data = [[Paragraph(f"<b>{h}</b>", cell_head) for h in head]]

    for v in qs:
        # Présence
        if getattr(v, 'en_local', False) and getattr(v, 'en_atelier', False):
            presence = "Local + Atelier"
        elif getattr(v, 'en_local', False):
            presence = "Présent"
        elif getattr(v, 'en_atelier', False):
            presence = "Atelier"
        else:
            presence = "Hors garage"

        # Véhicule
        veh_txt = f"{v.marque or ''} {v.modele or ''}".strip() or "—"
        if v.annee:
            veh_txt += f" ({v.annee})"

        # Propriétaire
        if v.client:
            if v.client.type_client == 'PARTICULIER':
                prop = f"{v.client.prenom or ''} {v.client.nom or ''}".strip()
            else:
                prop = v.client.nom or "—"
            tel = v.client.telephone or ""
            if tel:
                prop = f"{prop}<br/>{tel}"
        else:
            prop = "—"

        # Carburant
        try:
            carb = v.get_type_carburant_display() if v.type_carburant != 'NON_DEFINI' else "—"
        except Exception:
            carb = v.type_carburant or "—"

        # Assurance
        if v.expiry_assurance:
            if v.expiry_assurance < today:
                ass = f"Expirée<br/>{v.expiry_assurance.strftime('%d/%m/%Y')}"
            else:
                ass = f"Valide<br/>{v.expiry_assurance.strftime('%d/%m/%Y')}"
        else:
            ass = "—"

        # Visite technique
        if v.date_visite:
            if v.date_visite < today:
                visite = f"À renouv.<br/>{v.date_visite.strftime('%d/%m/%Y')}"
            else:
                visite = f"OK<br/>{v.date_visite.strftime('%d/%m/%Y')}"
        else:
            visite = "—"

        nb_pass = getattr(v, 'nb_passages', None)
        if nb_pass is None:
            nb_pass = v.entrees.count() if hasattr(v, 'entrees') else "—"

        data.append([
            Paragraph(presence, cell),
            Paragraph(v.immatriculation or "—", cell),
            Paragraph(veh_txt, cell),
            Paragraph(prop, cell),
            Paragraph(str(carb), cell),
            Paragraph(ass, cell),
            Paragraph(visite, cell),
            Paragraph(str(nb_pass), cell),
        ])

    col_widths = [24*mm, 24*mm, 32*mm, 36*mm, 20*mm, 22*mm, 22*mm, 16*mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COULEUR_GRIS]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dde1e6')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)

    def add_footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#999999'))
        canvas.drawString(10 * mm, 8 * mm, "Centre Auto La Prudence + — Document généré automatiquement")
        canvas.drawRightString(portrait(A4)[0] - 10 * mm, 8 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes