from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.lib import colors
from io import BytesIO
from django.utils import timezone
from apps.documents.pdf_generator import COULEUR_ACCENT, COULEUR_GRIS, COULEUR_PRIMAIRE, COULEUR_TEXTE, format_datetime





def generer_pdf_liste_clients(qs):
    """
    Génère un PDF de la liste des clients (portrait A4).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=portrait(A4),
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )
    elements = []

    # ── Styles ──
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
    cell = ParagraphStyle('', fontSize=7.5, textColor=COULEUR_TEXTE, leading=10)
    cell_head = ParagraphStyle(
        '', fontSize=7.5, fontName='Helvetica-Bold',
        textColor=colors.white, leading=10
    )

    now_str = format_datetime(timezone.now())
    total = qs.count()
    nb_part = qs.filter(type_client='PARTICULIER').count()
    nb_ent = qs.filter(type_client='ENTREPRISE').count()

    # ── En-tête ──
    header_data = [
        [
            Paragraph("CENTRE AUTO LA PRUDENCE +", nom_style),
            Paragraph("LISTE DES CLIENTS", titre_style),
        ],
        [
            Paragraph("BP 9060 — Douala, Cameroun<br/>Tél : +237 650 99 75 09", sub_style),
            Paragraph(
                f"Export du {now_str}<br/>"
                f"Total : <b>{total}</b> — "
                f"{nb_part} particulier(s), {nb_ent} entreprise(s)",
                meta_style
            ),
        ],
    ]
    header = Table(header_data, colWidths=[100 * mm, 86 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, COULEUR_PRIMAIRE),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 6 * mm))

    # ── Tableau ──
    head = ['Client', 'Type', 'Téléphone', 'Email', 'Ville', 'Véhicules', 'Passages', 'Créé le']
    data = [[Paragraph(f"<b>{h}</b>", cell_head) for h in head]]

    for c in qs:
        if c.type_client == 'PARTICULIER':
            nom = f"{c.prenom or ''} {c.nom or ''}".strip()
            type_label = "Particulier"
        else:
            nom = c.nom or "—"
            type_label = "Entreprise"

        nb_veh = getattr(c, 'nb_vehicules', None)
        if nb_veh is None:
            nb_veh = c.vehicules.count()

        nb_pass = getattr(c, 'nb_passages', None)
        if nb_pass is None:
            nb_pass = "—"

        data.append([
            Paragraph(nom, cell),
            Paragraph(type_label, cell),
            Paragraph(c.telephone or "—", cell),
            Paragraph(c.email or "—", cell),
            Paragraph(c.ville or "—", cell),
            Paragraph(str(nb_veh), cell),
            Paragraph(str(nb_pass), cell),
            Paragraph(c.created_at.strftime('%d/%m/%Y') if c.created_at else "—", cell),
        ])

    col_widths = [38*mm, 22*mm, 26*mm, 35*mm, 22*mm, 18*mm, 18*mm, 20*mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COULEUR_GRIS]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dde1e6')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(table)

    # ── Pied de page ──
    def add_footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#999999'))
        canvas.drawString(12 * mm, 8 * mm, "Centre Auto La Prudence + — Document généré automatiquement")
        canvas.drawRightString(portrait(A4)[0] - 12 * mm, 8 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes