from collections import Counter

from reportlab.lib.enums import TA_CENTER

from apps.documents.pdf_generator import COULEUR_ACCENT, COULEUR_GRIS, COULEUR_PRIMAIRE, COULEUR_TEXTE, format_datetime
from apps.reception.pdf_vehicules_pdf import BLEU, COULEUR_DISCRET, ORANGE, P, _badge, _bandeau_repartition, _construire, _entete, _message_vide, _nom_client, _tableau, _txt, _vide_cell






# ════════════════════════════════════════════════════════════════
#  LISTE DES CLIENTS
# ════════════════════════════════════════════════════════════════
def generer_pdf_liste_clients(qs):
    """Génère le PDF de la liste des clients (A4 paysage)."""
    if hasattr(qs, 'prefetch_related'):
        qs = qs.prefetch_related('centres')
    clients = list(qs)

    types = Counter('Particulier' if c.type_client == 'PARTICULIER' else 'Entreprise' for c in clients)
    total_veh = total_centres = 0
    lignes = []
    for c in clients:
        particulier = c.type_client == 'PARTICULIER'

        nb_veh = getattr(c, 'nb_vehicules_total', None)
        if nb_veh is None:
            nb_veh = getattr(c, 'nb_vehicules', None)
        if nb_veh is None:
            nb_veh = c.vehicules.count()
        nb_pass = getattr(c, 'nb_passages', None)
        centres = [] if particulier else [ct.nom for ct in c.centres.all()]
        total_veh += nb_veh or 0
        total_centres += len(centres)

        nom = f"<b>{_txt(_nom_client(c)) or '—'}</b>"
       
        if centres:
            liste = ", ".join(_txt(n) for n in centres[:4]) + (f" +{len(centres) - 4}" if len(centres) > 4 else '')
            nom += f"<br/><font size=6.5 color='#e67e22'>{len(centres)} centre(s) : {liste}</font>"

        contact = '<br/>'.join(_txt(x) for x in [c.telephone, getattr(c, 'telephone2', '')] if x)

        lignes.append([
            P(nom),
            _badge('Particulier', BLEU) if particulier else _badge('Entreprise', '#7c3aed'),
            P(contact) if contact else _vide_cell(),
            P(_txt(c.email)) if c.email else _vide_cell(),
            P(_txt(c.ville)) if c.ville else _vide_cell(),
            P(f"<b>{nb_veh}</b>", 9, True, TA_CENTER, COULEUR_PRIMAIRE if nb_veh else COULEUR_DISCRET),
            P(f"<b>{nb_pass}</b>", 9, True, TA_CENTER, COULEUR_PRIMAIRE if nb_pass else COULEUR_DISCRET)
            if nb_pass is not None else _vide_cell(),
            P(c.created_at.strftime('%d/%m/%Y') if c.created_at else '—', 7.5, False, TA_CENTER),
        ])

    titre = "Liste des clients"
    elements = _entete(titre.upper(), len(clients), "client(s)")
    elements += _bandeau_repartition([
        ("Répartition", [("Entreprises", types['Entreprise'], '#7c3aed'),
                         ("Particuliers", types['Particulier'], BLEU),
                         ("Centres", total_centres, ORANGE),
                         ("Véhicules", total_veh, '#1a3a5c')]),
    ])
    if lignes:
        elements.append(_tableau(
            ['Client', 'Type', 'Téléphone', 'Email', 'Ville', 'Véhicules', 'Passages', 'Client depuis'],
            [62, 26, 30, 50, 28, 20, 20, 24], lignes, centrer=(5, 6, 7)))
    else:
        elements.append(_message_vide("Aucun client ne correspond à ces critères."))
    return _construire(titre, elements)
