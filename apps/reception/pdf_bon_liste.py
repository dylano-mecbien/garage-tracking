from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.units import mm
from reportlab.lib import colors
from io import BytesIO
from django.utils import timezone
from apps.documents.pdf_generator import COULEUR_ACCENT, COULEUR_GRIS, COULEUR_PRIMAIRE, COULEUR_TEXTE, format_datetime

def generer_pdf_liste_bons(qs):
    """
    Génère un PDF de la liste des bons de sortie (paysage A4).
    `qs` : queryset de BonSortie (déjà filtré).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    elements = []
    # ── En-tête ──
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

    now_str = format_datetime(timezone.now())
    total = qs.count()

    header_data = [
        [
            Paragraph("CENTRE AUTO LA PRUDENCE +", nom_style),
            Paragraph("BONS DE SORTIE", titre_style),
        ],
        [
            Paragraph("BP 9060 — Douala, Cameroun<br/>Tél : +237 650 99 75 09", sub_style),
            Paragraph(f"Export du {now_str}<br/>Total : <b>{total}</b> bon(s)", meta_style),
        ],
    ]
    header = Table(header_data, colWidths=[140 * mm, 130 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, COULEUR_PRIMAIRE),
    ]))
    elements.append(header)
    elements.append(Spacer(1, 6 * mm))


# Style cellules normales (corps)
    cell = ParagraphStyle(
    '', fontSize=7.5, textColor=COULEUR_TEXTE, leading=10
    )
    cell_head = ParagraphStyle(
    '', fontSize=7.5, fontName='Helvetica-Bold',
    textColor=colors.white, leading=10
    )

    head = ['N° Bon', 'Type', 'État', 'Véhicule', 'Demandeur', 'Créé le', 'Validé le', 'Créé par']
    data = [[Paragraph(f"<b>{h}</b>", cell_head) for h in head]]

    for bon in qs:
        type_label = "Véhicule" if bon.types == 'VEHICULE' else "Divers"
        etat_label = {
            'VALIDER': 'Validé',
            'APPROBATION': 'Approbation',
            'CREER': 'Créé',
        }.get(bon.etats, bon.etats or '—')

        if bon.types == 'VEHICULE' and bon.vehicule:
            vehicule_txt = bon.vehicule.immatriculation
        else:
            vehicule_txt = "—"

        cree_par = bon.cree_par.full_name if bon.cree_par else "—"
        valide_le = format_datetime(bon.date_validation) if bon.date_validation else "—"

        data.append([
            Paragraph(str(bon.numero), cell),
            Paragraph(type_label, cell),
            Paragraph(etat_label, cell),
            Paragraph(str(vehicule_txt), cell),
            Paragraph(bon.nom_demandeur or "—", cell),
            Paragraph(format_datetime(bon.created_at), cell),
            Paragraph(valide_le, cell),
            Paragraph(cree_par, cell),
        ])

    col_widths = [24*mm, 20*mm, 24*mm, 26*mm, 32*mm, 28*mm, 28*mm, 30*mm]
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

    # ── Pied de page via callback ──
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#999999'))
        canvas.drawString(12 * mm, 8 * mm, "Centre Auto La Prudence + — Document généré automatiquement")
        canvas.drawRightString(
            landscape(A4)[0] - 12 * mm,
            8 * mm,
            f"Page {doc.page}"
        )
        canvas.restoreState()

    doc.build(elements, onFirstPage=add_footer, onLaterPages=add_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes