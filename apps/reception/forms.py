from django import forms
from .models import Reception, RapportReception, TransfertAtelier
from apps.atelier.models import Atelier, OrdreReparation
from apps.guerite.models import BonSortie

W = {'class': 'form-input'}
WTA = {'class': 'form-textarea', 'rows': 3}
WSE = {'class': 'form-select'}


class ReceptionForm(forms.ModelForm):
    class Meta:
        model = Reception
        fields = ['observations']
        widgets = {'observations': forms.Textarea(attrs={**WTA, 'placeholder': 'Observations...'})}


class RapportReceptionForm(forms.ModelForm):
    class Meta:
        model = RapportReception
        fields = ['constat', 'probleme_declare', 'kilometrage', 'niveau_carburant', 'decision', 'observations']
        widgets = {
            'constat':          forms.Textarea(attrs={**WTA, 'rows': 4, 'placeholder': 'Constat visuel à l\'arrivée...'}),
            'probleme_declare': forms.Textarea(attrs={**WTA, 'rows': 3, 'placeholder': 'Problème déclaré par le client...'}),
            'kilometrage':      forms.NumberInput(attrs=W),
            'niveau_carburant': forms.NumberInput(attrs={**W, 'min': 0, 'max': 100}),
            'decision':         forms.Select(attrs={**WSE, 'id': 'id_decision'}),
            'observations':     forms.Textarea(attrs={**WTA, 'rows': 2}),
        }


class TransfertAtelierForm(forms.Form):
    """Sélection de plusieurs ateliers"""
    ateliers = forms.ModelMultipleChoiceField(
        queryset=Atelier.objects.filter(is_active=True),
        label="Atelier(s) de destination",
        widget=forms.CheckboxSelectMultiple(),
    )
    motif = forms.CharField(
        label="Travaux demandés",
        widget=forms.Textarea(attrs={**WTA, 'placeholder': 'Décrivez les travaux à effectuer...'})
    )


class BonSortieForm(forms.ModelForm):

    class Meta:
        model = BonSortie
        fields = ['types', 'vehicule', 'nom_demandeur', 'observations', 'signature_client']
        widgets = {
            'types': forms.Select(attrs={'class': 'form-select'}),
            'vehicule': forms.Select(attrs={'class': 'form-select'}),
            'nom_demandeur': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Employé / Client / Conducteur',
                'list': 'demandeurs'
            }),
            'observations': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Observations...'
            }),
            'signature_client': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Types : valeur par défaut, non requis (car on le force en vue)
        self.fields['types'].initial = 'VEHICULE'
        self.fields['types'].required = False

        # Véhicule optionnel (pour le cas DIVERS)
        self.fields['vehicule'].required = False

class ORReceptionForm(forms.ModelForm):
    """Créer un OR depuis la réception"""
    class Meta:
        model = OrdreReparation
        fields = ['atelier', 'diagnostic', 'date_fin_prevue', 'observations']
        widgets = {
            'atelier':         forms.Select(attrs=WSE),
            'diagnostic':      forms.Textarea(attrs={**WTA, 'rows': 4}),
            'date_fin_prevue': forms.DateTimeInput(attrs={**W, 'type': 'datetime-local'}),
            'observations':    forms.Textarea(attrs={**WTA, 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atelier'].queryset = Atelier.objects.filter(is_active=True)
        self.fields['date_fin_prevue'].required = False
