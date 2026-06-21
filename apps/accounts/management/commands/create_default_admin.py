
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.vehicules.models import Marque, Modele

class Command(BaseCommand):
    help = "Création des marques et modèles de véhicules"


    def handle(self, *args, **options):
        self.stdout.write("🚀 Initialisation des marques et modèles...\n")

        with transaction.atomic():
            self._create_marques_modeles()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✅ Initialisation terminée !"))

    def _create_marques_modeles(self):
        from apps.vehicules.models import Marque, Modele

    data = {
        "Toyota": ["Corolla", "Camry", "Hilux", "Land Cruiser", "RAV4"],
        "Honda": ["Civic", "Accord", "CR-V", "Pilot", "HR-V"],
        "Nissan": ["Sentra", "Altima", "X-Trail", "Patrol", "Navara"],
        "Hyundai": ["i10", "Elantra", "Tucson", "Santa Fe", "Creta"],
        "Kia": ["Picanto", "Rio", "Cerato", "Sportage", "Sorento"],
        "Ford": ["Fiesta", "Focus", "Ranger", "Everest", "Explorer"],
        "Chevrolet": ["Spark", "Aveo", "Cruze", "Captiva", "Tahoe"],
        "Volkswagen": ["Polo", "Golf", "Passat", "Tiguan", "Touareg"],
        "Peugeot": ["208", "301", "308", "3008", "5008"],
        "Renault": ["Clio", "Logan", "Duster", "Kadjar", "Master"],
        "BMW": ["Serie 1", "Serie 3", "Serie 5", "X3", "X5"],
        "Mercedes-Benz": ["Classe A", "Classe C", "Classe E", "GLC", "GLE"],
        "Audi": ["A3", "A4", "A6", "Q3", "Q5"],
        "Lexus": ["IS", "ES", "RX", "GX", "LX"],
        "Mazda": ["Mazda2", "Mazda3", "Mazda6", "CX-5", "CX-9"],
        "Suzuki": ["Alto", "Swift", "Baleno", "Vitara", "Jimny"],
        "Mitsubishi": ["Lancer", "ASX", "Outlander", "Pajero", "L200"],
        "Subaru": ["Impreza", "Legacy", "Forester", "Outback", "XV"],
        "Isuzu": ["D-Max", "MU-X", "N-Series", "F-Series", "Trooper"],
        "Jeep": ["Renegade", "Compass", "Cherokee", "Wrangler", "Grand Cherokee"],
        "Land Rover": ["Defender", "Discovery", "Range Rover", "Evoque", "Velar"],
        "Volvo": ["S60", "S90", "XC40", "XC60", "XC90"],
        "Jaguar": ["XE", "XF", "F-Pace", "E-Pace", "I-Pace"],
        "Porsche": ["Macan", "Cayenne", "Panamera", "911", "Taycan"],
        "Ferrari": ["Roma", "Portofino", "F8", "SF90", "Purosangue"],
        "Lamborghini": ["Huracan", "Aventador", "Urus", "Revuelto", "Gallardo"],
        "Bentley": ["Continental", "Flying Spur", "Bentayga", "Mulsanne", "Azure"],
        "Rolls-Royce": ["Ghost", "Phantom", "Cullinan", "Wraith", "Dawn"],
        "Tesla": ["Model 3", "Model S", "Model X", "Model Y", "Cybertruck"],
        "BYD": ["Dolphin", "Atto 3", "Seal", "Han", "Tang"],
        "Chery": ["Tiggo 2", "Tiggo 4", "Tiggo 7", "Tiggo 8", "Arrizo 5"],
        "Geely": ["Coolray", "Emgrand", "Azkarra", "Okavango", "Preface"],
        "Great Wall": ["Wingle", "Poer", "Haval H6", "Jolion", "Tank 300"],
        "Dongfeng": ["S30", "AX3", "AX7", "Rich", "Shine"],
        "FAW": ["V5", "X40", "X80", "Bestune B70", "T77"],
        "Opel": ["Corsa", "Astra", "Insignia", "Crossland", "Grandland"],
        "Citroen": ["C3", "C4", "C5", "Berlingo", "Aircross"],
        "Seat": ["Ibiza", "Leon", "Arona", "Ateca", "Tarraco"],
        "Skoda": ["Fabia", "Octavia", "Superb", "Karoq", "Kodiaq"],
        "Dacia": ["Sandero", "Logan", "Duster", "Jogger", "Spring"],
        "Fiat": ["500", "Panda", "Tipo", "Doblo", "Toro"],
        "Alfa Romeo": ["Giulia", "Stelvio", "Tonale", "Mito", "159"],
        "Aston Martin": ["DB11", "DBX", "Vantage", "Rapide", "Vanquish"],
        "Mini": ["Cooper", "Clubman", "Countryman", "Paceman", "Roadster"],
        "Acura": ["ILX", "TLX", "RDX", "MDX", "NSX"],
        "Infiniti": ["Q50", "Q60", "QX50", "QX60", "QX80"],
        "Genesis": ["G70", "G80", "G90", "GV70", "GV80"],
        "Cadillac": ["CT4", "CT5", "XT4", "XT5", "Escalade"],
        "Buick": ["Encore", "Envision", "Enclave", "LaCrosse", "Regal"],
        "Lincoln": ["Corsair", "Nautilus", "Aviator", "Navigator", "MKZ"]
    }

    marques_creees = 0
    modeles_crees = 0

    for marque_nom, modeles in data.items():
        marque, created = Marque.objects.get_or_create(nom=marque_nom)

        if created:
            marques_creees += 1

        for modele_nom in modeles:
            _, modele_created = Modele.objects.get_or_create(
                marque=marque,
                nom=modele_nom
            )

            if modele_created:
                modeles_crees += 1


