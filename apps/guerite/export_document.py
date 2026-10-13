
# ---------------------------------------------------------------------------
# Export PDF (ReportLab, cohérent avec le reste du projet)
# ---------------------------------------------------------------------------
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.choices import MotifEntree, StatutVehicule
from apps.guerite.views import get_entrees_presentes_filtrees, get_filtered_entrees
from openpyxl import Workbook
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from django.http import HttpResponse
 
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib.enums import TA_CENTER


def _ligne_entree(entree):
    """Une ligne de données commune aux deux exports."""
    vehicule = entree.vehicule
    client = vehicule.client
    return [
        vehicule.immatriculation,
        f"{vehicule.marque} {vehicule.modele}".strip(),
        str(client) if client else "—",
        getattr(client, "telephone", "") or "—",
        str(entree.conducteur) if entree.conducteur else "—",
        MOTIF_LABELS.get(entree.motif, entree.get_motif_display()),
        timezone.localtime(entree.date_entree).strftime("%d/%m/%Y %H:%M"),
        str(entree.duree_sejour),
    ]

ENTETES = [
    "Immatriculation", "Véhicule", "Propriétaire", "Téléphone",
    "Conducteur", "Motif", "Entrée le", "Durée",
]
MOTIF_LABELS = {
    "REPARATION": "🔧 Réparation",
    "VISITE": "👁 Visite",
}
 
def export_presents_pdf(request):
    entrees = get_entrees_presentes_filtrees(request)
 
    response = HttpResponse(content_type="application/pdf")
    filename = f"vehicules_presents_{timezone.localtime().strftime('%Y%m%d_%H%M')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
 
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        leftMargin=1 * cm,
        rightMargin=1 * cm,
    )
 
    styles = getSampleStyleSheet()
    titre_style = ParagraphStyle(
        "Titre", parent=styles["Title"], fontSize=16, alignment=TA_CENTER,
        textColor=colors.HexColor("#1F4E78"),
    )
    sous_titre_style = ParagraphStyle(
        "SousTitre", parent=styles["Normal"], fontSize=9, alignment=TA_CENTER,
        textColor=colors.HexColor("#666666"),
    )
 
    elements = [
        Paragraph("Véhicules présents dans le local", titre_style),
        Paragraph(
            f"Généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')} — "
            f"{entrees.paginator.count} véhicule(s)",
            sous_titre_style,
        ),
        Spacer(1, 0.5 * cm),
    ]
 
    data = [ENTETES] + [_ligne_entree(e) for e in entrees]
 
    if len(data) == 1:
        elements.append(Paragraph("Aucun véhicule dans le local.", styles["Normal"]))
    else:
        col_widths = [3.0, 4.2, 4.2, 3.0, 3.4, 3.2, 3.4, 2.3]
        col_widths = [w * cm for w in col_widths]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E75B6")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F2F6FA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(table)
 
    doc.build(elements)
    return response



 
# ---------------------------------------------------------------------------
# Export Excel
# ---------------------------------------------------------------------------
def export_presents_excel(request):
    entrees = get_entrees_presentes_filtrees(request)
 
    wb = Workbook()
    ws = wb.active
    ws.title = "Véhicules présents"
 
    # Titre
    ws.merge_cells("A1:H1")
    titre = ws["A1"]
    titre.value = "Véhicules présents dans le local"
    titre.font = Font(size=14, bold=True, color="FFFFFF")
    titre.alignment = Alignment(horizontal="center", vertical="center")
    titre.fill = PatternFill("solid", fgColor="1F4E78")
    ws.row_dimensions[1].height = 26
 
    ws.merge_cells("A2:H2")
    sous_titre = ws["A2"]
    sous_titre.value = (
        f"Généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')} — "
        f"{entrees.count()} véhicule(s)"
    )
    sous_titre.font = Font(size=9, italic=True, color="666666")
    sous_titre.alignment = Alignment(horizontal="center")
 
    # En-têtes (ligne 4)
    header_row = 4
    header_fill = PatternFill("solid", fgColor="2E75B6")
    header_font = Font(bold=True, color="FFFFFF")
    thin_border = Border(*(Side(style="thin", color="CCCCCC"),) * 4)
 
    for col, entete in enumerate(ENTETES, start=1):
        cell = ws.cell(row=header_row, column=col, value=entete)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
 
    # Données
    zebra_fill = PatternFill("solid", fgColor="F2F6FA")
    for i, entree in enumerate(entrees, start=1):
        row = header_row + i
        for col, valeur in enumerate(_ligne_entree(entree), start=1):
            cell = ws.cell(row=row, column=col, value=valeur)
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=False)
            if i % 2 == 0:
                cell.fill = zebra_fill
 
    # Largeurs de colonnes auto (approx.)
    largeurs = [16, 22, 22, 15, 18, 16, 17, 12]
    for col, largeur in enumerate(largeurs, start=1):
        ws.column_dimensions[get_column_letter(col)].width = largeur
 
    ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = f"A{header_row}:H{header_row}"
 
    response = HttpResponse(
        content_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        )
    )
    filename = f"vehicules_presents_{timezone.localtime().strftime('%Y%m%d_%H%M')}.xlsx"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response




def export_entrees_excel(request):
    # Récupérer les mêmes filtres que dans historique_entrees
    entrees = get_filtered_entrees(request)  # on factorise la logique

    wb = Workbook()
    ws = wb.active
    ws.title = "Historique entrées"

    # En-têtes
    headers = [
        'N°', 'Immatriculation', 'Client', 'Téléphone client', 'Conducteur',
        'Motif', 'Statut', 'Date entrée', 'Date sortie', 'Agent entrée',
        'Observations',
    ]
    ws.append(headers)

    # Mise en forme des en-têtes
    for cell in ws[1]:
        cell.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal='center')

    for e in entrees:
        ws.append([
            e.numero,
            e.vehicule.immatriculation,
            str(e.vehicule.client),
            e.vehicule.client.telephone if e.vehicule.client else '',
            str(e.conducteur) if e.conducteur else '',
            e.get_motif_display(),
            e.get_statut_display(),
            e.date_entree.strftime("%d/%m/%Y %H:%M") if e.date_entree else '',
            e.date_sortie.strftime("%d/%m/%Y %H:%M") if e.date_sortie else '',
            e.agent_entree.full_name if e.agent_entree else '',
            e.observations or '',
        ])

    # Ajuster la largeur des colonnes
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        adjusted_width = min(max_length + 2, 30)
        ws.column_dimensions[col_letter].width = adjusted_width

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=historique_entrees_{timezone.localdate()}.xlsx'
    wb.save(response)
    return response


BRAND_COLOR = colors.HexColor('#366092')


def _footer(canvas, doc):
    """Pied de page : numéro de page + date de génération, sur chaque page."""
    canvas.saveState()
    canvas.setFont('Helvetica', 7)
    canvas.setFillColor(colors.HexColor('#999999'))
    canvas.drawString(
        1 * cm, 0.7 * cm,
        f"Généré le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')}",
    )
    canvas.drawRightString(
        landscape(A4)[0] - 1 * cm, 0.7 * cm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def export_entrees_pdf(request):
    entrees = get_filtered_entrees(request)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename=historique_entrees_{timezone.localdate()}.pdf'

    doc = SimpleDocTemplate(
        response, pagesize=landscape(A4),
        rightMargin=1 * cm, leftMargin=1 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    # Titre
    title_style = ParagraphStyle(
        'Titre', parent=styles['Heading1'], alignment=TA_CENTER,
        textColor=BRAND_COLOR, fontSize=16, spaceAfter=2,
    )
    elements.append(Paragraph("Historique des entrées", title_style))

    # Sous-titre : nombre de résultats
    meta_style = ParagraphStyle(
        'Meta', parent=styles['Normal'], alignment=TA_CENTER,
        fontSize=9, textColor=colors.HexColor('#666666'),
    )
    elements.append(Paragraph(
        f"{entrees.count()} mouvement(s) trouvé(s)", meta_style,
    ))
    elements.append(Spacer(1, 8))

    # Filtres appliqués (affichés seulement s'il y en a)
    filters = []
    if request.GET.get('q'):
        filters.append(f"Recherche : {request.GET['q']}")
    if request.GET.get('statut'):
        filters.append(f"Statut : {dict(StatutVehicule.choices).get(request.GET['statut'], '')}")
    if request.GET.get('motif'):
        filters.append(f"Motif : {dict(MotifEntree.choices).get(request.GET['motif'], '')}")
    if request.GET.get('date_debut'):
        filters.append(f"Du : {request.GET['date_debut']}")
    if request.GET.get('date_fin'):
        filters.append(f"Au : {request.GET['date_fin']}")

    if filters:
        filter_style = ParagraphStyle(
            'FilterStyle', parent=styles['Normal'], alignment=TA_CENTER,
            fontSize=8.5, textColor=colors.HexColor('#888888'), spaceAfter=4,
        )
        elements.append(Paragraph("Filtres : " + " · ".join(filters), filter_style))

    elements.append(Spacer(1, 10))

    # Données du tableau
    data = [['Immat.', 'Client', 'Motif', 'Statut', 'Entrée', 'Sortie', 'Agent']]
    for e in entrees:
        data.append([
            e.vehicule.immatriculation,
            str(e.vehicule.client)[:30],
            e.get_motif_display(),
            e.get_statut_display(),
            e.date_entree.strftime("%d/%m %H:%M") if e.date_entree else '—',
            e.date_sortie.strftime("%d/%m %H:%M") if e.date_sortie else '—',
            e.agent_entree.full_name.split()[0] if e.agent_entree else '—',
        ])

    if len(data) == 1:
        elements.append(Paragraph("Aucun mouvement ne correspond à ces critères.", styles['Normal']))
    else:
        table = Table(
            data, repeatRows=1,
            colWidths=[2.2 * cm, 4.5 * cm, 2.8 * cm, 2.8 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm],
        )
        table.setStyle(TableStyle([
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), BRAND_COLOR),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            # Corps (lignes zébrées)
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F2F6FA')]),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
            # Global
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CCCCCC')),
        ]))
        elements.append(table)

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return response
