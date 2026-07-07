"""
Générateur PDF - Devis, Factures, Bons de sortie
"""
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, HRFlowable, Image)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

COULEUR_PRIMAIRE = colors.HexColor('#1a3a5c')
COULEUR_ACCENT = colors.HexColor('#e67e22')
COULEUR_GRIS = colors.HexColor('#f5f5f5')
COULEUR_TEXTE = colors.HexColor('#2c3e50')

# Couleurs des badges d'état (cohérentes avec le template HTML : etat-valider / etat-approbation / etat-creer)
COULEUR_VALIDE_BG = colors.HexColor('#d1fae5')
COULEUR_VALIDE_TEXTE = colors.HexColor('#065f46')
COULEUR_APPROBATION_BG = colors.HexColor('#fef3c7')
COULEUR_APPROBATION_TEXTE = colors.HexColor('#92400e')
COULEUR_CREER_BG = colors.HexColor('#e5e7eb')
COULEUR_CREER_TEXTE = colors.HexColor('#374151')


def _badge_etat(etat):
    """
    Retourne un petit Table à fond coloré servant de badge d'état,
    aligné à droite, juste au-dessus du bloc Informations.
    """
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
    """
    En-tête réutilisable pour devis/factures/bons.
    vehicule et client sont optionnels : pour un bon de sortie de type
    DIVERS, il n'y a pas de véhicule associé.
    """
    styles = getSampleStyleSheet()

    if vehicule is not None:
        ligne_vehicule = f"<b>Véhicule:</b> {vehicule.immatriculation} - {vehicule.marque} {vehicule.modele}"
    else:
        ligne_vehicule = ""

    ligne_client = f"<b>Client:</b> {client}" if client else ""

    data = [
        [Paragraph("<b><font size=14 color='#1a3a5c'>GARAGE AUTO LA PRUDENCE +</font></b>", styles['Normal']),
         Paragraph(f"<b><font size=16 color='#e67e22'>{titre}</font></b>", ParagraphStyle('', alignment=TA_RIGHT))],
        [Paragraph("BP 9060 - Douala, Cameroun<br/>Tél: +237 650 99 75 09", styles['Normal']),
         Paragraph(f"<b>N°:</b> {numero}<br/><b>Date:</b> {date.strftime('%d/%m/%Y %H:%M')}", ParagraphStyle('', alignment=TA_RIGHT))],
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
    """Titre de section avec petite barre verticale orange devant, façon fiche pro."""
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
    """
    Petit tableau clé/valeur deux colonnes pour les informations
    simples d'un bon de sortie (pas de prix, pas de quantités).
    `rows` est une liste de tuples (label, valeur).
    """
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
    """
    Bloc 'description' en disposition verticale (label au-dessus,
    contenu en dessous, sur toute la largeur) — utilisé pour les bons
    de type DIVERS où une description peut être longue.

    `contenu` peut être :
      - une chaîne de texte simple (affichée telle quelle), ou
      - une liste de chaînes (affichée comme une liste numérotée
        verticale, une ligne par article).
    """
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
    """
    Découpe un texte d'observations en liste d'articles, sur la base
    des séparateurs ';' ou saut de ligne — même logique que côté
    formulaire (aperçu cahier) et côté template HTML (filtre
    split_articles), pour un rendu cohérent partout.
    """
    if not texte:
        return []
    import re
    items = re.split(r'[;\n]+', texte)
    return [item.strip() for item in items if item.strip()]


def _mention_legale():
    """Mention légale en pied de document, sur fond léger, encadrée."""
    style = ParagraphStyle('', fontSize=8.5, fontName='Helvetica-Oblique',
                            textColor=COULEUR_TEXTE, alignment=TA_CENTER, leading=12)
    texte = ("NB : Tout bon de sortie validé fait office de signature numérique.")
    t = Table([[Paragraph(texte, style)]], colWidths=[190 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COULEUR_GRIS),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    return t



def generer_pdf_bon_sortie(bon):
    """
    Génère le PDF d'un bon de sortie (véhicule ou divers) au même
    style visuel que les devis/factures : en-tête GARAGE AUTO,
    badge d'état coloré, informations, détails véhicule ou description
    verticale pour un bon divers, et mention légale en pied de page.

    Si le bon est de type VEHICULE, les dates d'entrée/sortie sont
    récupérées depuis l'EnregistrementEntree lié (relation déjà
    existante via bon.entrees_liees), sans paramètre supplémentaire.

    Retourne les bytes du PDF (utilisables directement dans une
    HttpResponse Django).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=15 * mm, bottomMargin=15 * mm,
        leftMargin=15 * mm, rightMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    elements = []

    # Pour l'en-tête : véhicule/client uniquement si bon de type VEHICULE
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

    # ── Badge d'état, aligné à droite ──
    elements.append(_badge_etat(getattr(bon, 'etats', 'CREER')))
    elements.append(Spacer(1, 7 * mm))

    # ── Bloc informations principales ──
    info_rows = [
        ("Type", "Véhicule" if bon.types == 'VEHICULE' else "Divers"),
        ("Demandeur", bon.nom_demandeur or "—"),
        ("Créé par", bon.cree_par.full_name if bon.cree_par else "—"),
        ("Créé le", bon.created_at.strftime('%d/%m/%Y %H:%M')),
    ]

    # Dates d'entrée/sortie : récupérées depuis l'EnregistrementEntree lié
    # à ce bon (relation bon_sortie -> related_name='entrees_liees').
    if bon.types == 'VEHICULE':
        entree = bon.entrees_liees.first()
        if entree:
            date_entree_str = entree.date_entree.strftime('%d/%m/%Y %H:%M') if entree.date_entree else "—"
            date_sortie_str = entree.date_sortie.strftime('%d/%m/%Y %H:%M') if entree.date_sortie else "—"
            info_rows.append(("Date entrée", date_entree_str))
            info_rows.append(("Date sortie", date_sortie_str))

    if bon.est_valide:
        info_rows.append(("Validé par", bon.valide_par.full_name if bon.valide_par else "—"))
        info_rows.append(("Validé le", bon.date_validation.strftime('%d/%m/%Y %H:%M') if bon.date_validation else "—"))

    elements.append(_section_titre("Informations"))
    elements.append(Spacer(1, 3 * mm))
    elements.append(_info_simple_table(info_rows))
    elements.append(Spacer(1, 8 * mm))

    # ── Bloc véhicule détaillé OU objet divers (description verticale) ──
    if bon.types == 'VEHICULE' and bon.vehicule:
        v = bon.vehicule
        vehicule_rows = [
            ("Immatriculation", v.immatriculation),
            ("Marque / Modèle", f"{v.marque} {v.modele}"),
            ("Année", v.annee),
            ("Couleur", v.couleur or "—"),
            ("Carburant", v.get_type_carburant_display()),
            ("Propriétaire", str(v.client) if v.client else "—"),
            ("Téléphone", v.client.telephone if v.client else "—"),
        ]
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

    # ── Observations (uniquement pour VEHICULE, pour ne pas dupliquer DIVERS) ──
    if bon.observations and bon.types == 'VEHICULE':
        elements.append(_section_titre("Observations"))
        elements.append(Spacer(1, 3 * mm))
        elements.append(_description_verticale("", bon.observations))
        elements.append(Spacer(1, 8 * mm))

    # ── Signature client si présente ──
    if bon.signature_client:
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc')))
        elements.append(Spacer(1, 4 * mm))
        elements.append(_section_titre("Signature du demandeur"))
        elements.append(Spacer(1, 4 * mm))
        try:
            # signature_client est une image encodée en base64 (data URL) via le pad JS
            import base64
            header, encoded = bon.signature_client.split(',', 1)
            img_data = base64.b64decode(encoded)
            img_buffer = BytesIO(img_data)
            elements.append(Image(img_buffer, width=60 * mm, height=30 * mm))
        except Exception:
            # Si le format n'est pas exploitable, on ignore l'image plutôt que de casser le PDF
            elements.append(Paragraph("Signature enregistrée (aperçu indisponible)", styles['Normal']))
        elements.append(Spacer(1, 8 * mm))
    else:
        elements.append(Spacer(1, 4 * mm))

    # ── Mention légale en pied de document ──
    elements.append(Spacer(1, 6 * mm))
    elements.append(_mention_legale())

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
