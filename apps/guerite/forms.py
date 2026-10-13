"""
Formulaires Guérite
"""
from django import forms
from apps.vehicules.models import Vehicule, Client, Conducteur
from .models import EnregistrementEntree, MotifEntree


class RechercheVehiculeForm(forms.Form):
    q = forms.CharField(
        label="Recherche",
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Immatriculation, marque, client...',
            'autofocus': True,
        }),
    )


class VehiculeForm(forms.ModelForm):
    marque = forms.CharField(max_length=100, required=True, label="Marque")
    modele = forms.CharField(max_length=100, required=True, label="Modèle")
    annee = forms.IntegerField(
        required=False, min_value=1920, max_value=2090, label="Année",
    )

    class Meta:
        model = Vehicule
        fields = [
            'immatriculation', 'marque', 'modele', 'annee', 'couleur',
            'numero_chassis', 'type_carburant', 'transmission', 'client', 'photo',
        ]
        widgets = {
            'immatriculation': forms.TextInput(attrs={
                'class': 'form-input', 'placeholder': 'AA-123-BB',
            }),
            'marque': forms.TextInput(attrs={'class': 'form-input'}),
            'modele': forms.TextInput(attrs={'class': 'form-input'}),
            'annee': forms.NumberInput(attrs={
                'class': 'form-input', 'min': 1940, 'max': 2090,
            }),
            'couleur': forms.TextInput(attrs={'class': 'form-input'}),
            'numero_chassis': forms.TextInput(attrs={'class': 'form-input'}),
            'type_carburant': forms.Select(attrs={'class': 'form-select'}),
            'transmission': forms.Select(attrs={'class': 'form-select'}),
            'client': forms.Select(attrs={'class': 'form-select'}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'type_client', 'nom', 'prenom', 'telephone', 'telephone2',
            'email', 'adresse', 'ville', 'ninea',
        ]
        widgets = {
            'type_client': forms.Select(attrs={'class': 'form-select'}),
            'nom': forms.TextInput(attrs={'class': 'form-input'}),
            'prenom': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone2': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'adresse': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
            'ville': forms.TextInput(attrs={'class': 'form-input'}),
            'ninea': forms.TextInput(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Souple côté form : la vue décide si on crée le client
        self.fields['nom'].required = False
        self.fields['telephone'].required = False
        self.fields['prenom'].required = False
        self.fields['email'].required = False
        self.fields['adresse'].required = False
        self.fields['ville'].required = False
        self.fields['ninea'].required = False

    def clean(self):
        cleaned = super().clean()
        # Si un client_id est fourni (réutilisation), on ne valide pas le reste
        # → géré dans la vue ; ici on valide seulement une création
        type_client = cleaned.get('type_client') or 'PARTICULIER'
        nom = (cleaned.get('nom') or '').strip()
        telephone = (cleaned.get('telephone') or '').strip()

        # La vue peut court-circuiter avec client_id ; si POST sans client_id,
        # on exige nom + téléphone
        if not nom:
            self.add_error('nom', "Le nom / raison sociale est obligatoire.")
        if not telephone:
            self.add_error('telephone', "Le téléphone est obligatoire.")

        cleaned['nom'] = nom
        cleaned['telephone'] = telephone
        if cleaned.get('prenom'):
            cleaned['prenom'] = cleaned['prenom'].strip()
        return cleaned


class ConducteurForm(forms.ModelForm):
    class Meta:
        model = Conducteur
        fields = [
            'nom', 'prenom', 'telephone', 'telephone2',
            'cni', 'permis', 'categorie_permis',
        ]
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-input'}),
            'prenom': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone2': forms.TextInput(attrs={'class': 'form-input'}),
            'cni': forms.TextInput(attrs={'class': 'form-input'}),
            'permis': forms.TextInput(attrs={'class': 'form-input'}),
            'categorie_permis': forms.TextInput(attrs={'class': 'form-input'}),
        }


class EntreeForm(forms.ModelForm):
    class Meta:
        model = EnregistrementEntree
        fields = ['vehicule', 'conducteur', 'motif', 'observations']
        widgets = {
            'vehicule': forms.Select(attrs={'class': 'form-select'}),
            'conducteur': forms.Select(attrs={'class': 'form-select'}),
            'motif': forms.Select(attrs={'class': 'form-select'}),
            'observations': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 3,
            }),
        }


class SortieForm(forms.Form):
    numero_bon = forms.CharField(
        label="Numéro du bon de sortie",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'BS-YYYYMM-XXXX',
        }),
    )
    observations_sortie = forms.CharField(
        label="Observations sortie",
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
    )