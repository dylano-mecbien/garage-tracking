"""
Générateur PDF - Devis, Factures, Bons de sortie
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                  Spacer, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


COULEUR_PRIMAIRE = colors.HexColor('#1a3a5c')
COULEUR_ACCENT = colors.HexColor('#e67e22')
COULEUR_GRIS = colors.HexColor('#f5f5f5')
COULEUR_TEXTE = colors.HexColor('#2c3e50')


def _header_table(titre, numero, date, vehicule, client):
    styles = getSampleStyleSheet()
    data = [
        [Paragraph(f"<b><font size=14 color='#1a3a5c'>GARAGE AUTO</font></b>", styles['Normal']),
         Paragraph(f"<b><font size=16 color='#e67e22'>{titre}</font></b>", ParagraphStyle('', alignment=TA_RIGHT))],
        [Paragraph("BP 1234 - Douala, Cameroun<br/>Tél: +237 699 000 000", styles['Normal']),
         Paragraph(f"<b>N°:</b> {numero}<br/><b>Date:</b> {date.strftime('%d/%m/%Y')}", ParagraphStyle('', alignment=TA_RIGHT))],
        [Paragraph(f"<b>Véhicule:</b> {vehicule.immatriculation} - {vehicule.marque} {vehicule.modele}", styles['Normal']),
         Paragraph(f"<b>Client:</b> {client}", ParagraphStyle('', alignment=TA_RIGHT))],
    ]
    t = Table(data, colWidths=[95*mm, 95*mm])
    t.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, -1), (-1, -1), 1, COULEUR_PRIMAIRE),
    ]))
    return t


def _lignes_table(lignes, styles):
    entetes = ['#', 'Description', 'Type', 'Qté', 'Unité', 'P.U. (FCFA)', 'Remise%', 'Total HT']
    data = [entetes]
    for i, ligne in enumerate(lignes, 1):
        data.append([
            str(i),
            ligne.designation,
            ligne.get_type_ligne_display(),
            str(ligne.quantite),
            ligne.unite,
            f"{ligne.prix_unitaire:,.0f}",
            f"{ligne.remise_pct}%",
            f"{ligne.total_ht:,.0f}",
        ])

    col_w = [8*mm, 60*mm, 22*mm, 12*mm, 12*mm, 25*mm, 15*mm, 25*mm]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COULEUR_PRIMAIRE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COULEUR_GRIS]),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#cccccc')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def _totaux_table(total_ht, taux_tva, total_tva, remise, total_ttc):
    data = [
        ['Total HT', f"{total_ht:,.0f} FCFA"],
        [f'TVA ({taux_tva}%)', f"{total_tva:,.0f} FCFA"],
    ]
    if remise:
        data.append(['Remise', f"- {remise:,.0f} FCFA"])
    data.append(['TOTAL TTC', f"{total_ttc:,.0f} FCFA"])

    t = Table(data, colWidths=[50*mm, 50*mm], hAlign='RIGHT')
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 1.5, COULEUR_PRIMAIRE),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('BACKGROUND', (0, -1), (-1, -1), COULEUR_PRIMAIRE),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    return t


def generer_pdf_devis(devis, lignes):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    vehicule = devis.reception.vehicule
    client = vehicule.client
    story.append(_header_table('DEVIS', devis.numero, devis.created_at, vehicule, client))
    story.append(Spacer(1, 10*mm))

    # Validité
    story.append(Paragraph(
        f"<b>Validité:</b> {devis.date_expiration.strftime('%d/%m/%Y')} | "
        f"<b>Statut:</b> {devis.get_statut_display()}",
        styles['Normal']
    ))
    story.append(Spacer(1, 5*mm))

    story.append(_lignes_table(lignes, styles))
    story.append(Spacer(1, 5*mm))
    story.append(_totaux_table(devis.total_ht, devis.taux_tva, devis.total_tva, devis.remise, devis.total_ttc))

    if devis.notes_client:
        story.append(Spacer(1, 8*mm))
        story.append(Paragraph(f"<b>Notes:</b> {devis.notes_client}", styles['Normal']))

    # Signature zone
    story.append(Spacer(1, 15*mm))
    sig_data = [
        ['Signature Client', '', 'Cachet & Signature Garage'],
        ['\n\n\n', '', '\n\n\n'],
    ]
    sig_t = Table(sig_data, colWidths=[60*mm, 60*mm, 60*mm])
    sig_t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOX', (0, 0), (0, -1), 0.5, colors.grey),
        ('BOX', (2, 0), (2, -1), 0.5, colors.grey),
    ]))
    story.append(sig_t)

    doc.build(story)
    return buffer.getvalue()


def generer_pdf_facture(facture):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15*mm, leftMargin=15*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    vehicule = facture.reception.vehicule
    client = vehicule.client
    story.append(_header_table('FACTURE', facture.numero, facture.created_at, vehicule, client))
    story.append(Spacer(1, 10*mm))

    lignes = facture.devis.lignes.all()
    story.append(_lignes_table(lignes, styles))
    story.append(Spacer(1, 5*mm))
    story.append(_totaux_table(
        facture.total_ht, facture.devis.taux_tva,
        facture.total_tva, facture.devis.remise, facture.total_ttc
    ))

    # Paiement
    story.append(Spacer(1, 8*mm))
    pay_data = [
        ['Montant payé', f"{facture.montant_paye:,.0f} FCFA"],
        ['Solde restant', f"{facture.solde_restant:,.0f} FCFA"],
        ['Statut', facture.get_statut_display()],
    ]
    pay_t = Table(pay_data, colWidths=[50*mm, 50*mm], hAlign='LEFT')
    pay_t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(pay_t)

    doc.build(story)
    return buffer.getvalue()
