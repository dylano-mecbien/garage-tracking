"""
Formulaires Atelier
"""
from django import forms
from .models import (OrdreReparation, Tache, CompteRenduIntervention,
                     FicheControle, FicheTechnique, Atelier, TypeOR, StatutTache, PrioriteTache)
from apps.accounts.models import User, Role


class OrdreReparationForm(forms.ModelForm):
    class Meta:
        model = OrdreReparation
        fields = ['atelier', 'diagnostic', 'observations', 'date_fin_prevue']
        widgets = {
            'atelier': forms.Select(attrs={'class': 'form-select'}),
            'diagnostic': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4}),
            'observations': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
            'date_fin_prevue': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atelier'].queryset = Atelier.objects.filter(is_active=True)


class TacheForm(forms.ModelForm):
    class Meta:
        model = Tache
        fields = ['libelle', 'description', 'type_operation', 'technicien', 'priorite', 'duree_estimee_minutes']
        widgets = {
            'libelle': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: Changement plaquettes de frein'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'type_operation': forms.Select(attrs={'class': 'form-select'}),
            'technicien': forms.Select(attrs={'class': 'form-select'}),
            'priorite': forms.Select(attrs={'class': 'form-select'}),
            'duree_estimee_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 15, 'step': 15}),
        }

    def __init__(self, atelier=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if atelier:
            self.fields['technicien'].queryset = User.objects.filter(
                role=Role.TECHNICIEN, atelier=atelier, is_active=True
            )
        else:
            self.fields['technicien'].queryset = User.objects.filter(
                role=Role.TECHNICIEN, is_active=True
            )
        self.fields['technicien'].required = False


class CompteRenduForm(forms.ModelForm):
    class Meta:
        model = CompteRenduIntervention
        fields = ['description', 'duree_minutes', 'pieces_utilisees', 'observations']
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4,
                'placeholder': 'Décrivez les travaux effectués...'}),
            'duree_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'pieces_utilisees': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2,
                'placeholder': 'Ex: Plaquettes avant (x4), Disque avant gauche (x1)...'}),
            'observations': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
        }


class FicheControleForm(forms.ModelForm):
    class Meta:
        model = FicheControle
        fields = [
            'etat_general', 'niveau_carburant', 'kilometrage',
            'feux_avant', 'feux_arriere', 'feux_stop', 'clignotants',
            'carrosserie_avant', 'carrosserie_arriere', 'carrosserie_gauche', 'carrosserie_droite',
            'pneu_avant_gauche', 'pneu_avant_droit', 'pneu_arriere_gauche', 'pneu_arriere_droit',
            'tableau_bord', 'radio', 'climatisation', 'siege_conducteur', 'tapis',
            'roue_secours', 'cric', 'triangle', 'extincteur',
            'defauts_observes',
        ]
        widgets = {
            'etat_general': forms.Select(attrs={'class': 'form-select'}),
            'niveau_carburant': forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 100}),
            'kilometrage': forms.NumberInput(attrs={'class': 'form-input'}),
            'carrosserie_avant': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'État avant...'}),
            'carrosserie_arriere': forms.TextInput(attrs={'class': 'form-input'}),
            'carrosserie_gauche': forms.TextInput(attrs={'class': 'form-input'}),
            'carrosserie_droite': forms.TextInput(attrs={'class': 'form-input'}),
            'pneu_avant_gauche': forms.Select(attrs={'class': 'form-select pneu-select'}),
            'pneu_avant_droit': forms.Select(attrs={'class': 'form-select pneu-select'}),
            'pneu_arriere_gauche': forms.Select(attrs={'class': 'form-select pneu-select'}),
            'pneu_arriere_droit': forms.Select(attrs={'class': 'form-select pneu-select'}),
            'siege_conducteur': forms.TextInput(attrs={'class': 'form-input'}),
            'defauts_observes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4}),
        }


class FicheTechniqueForm(forms.ModelForm):
    class Meta:
        model = FicheTechnique
        fields = ['diagnostic', 'pieces_recommandees', 'main_oeuvre_estimee', 'pieces_estimees',
                  'temps_estime_heures', 'observations']
        widgets = {
            'diagnostic': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 5,
                'placeholder': 'Diagnostic technique détaillé...'}),
            'pieces_recommandees': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3,
                'placeholder': 'Liste des pièces recommandées...'}),
            'main_oeuvre_estimee': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'pieces_estimees': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'temps_estime_heures': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5'}),
            'observations': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
        }


class ORRetourForm(forms.Form):
    motif_retour = forms.CharField(
        label="Motif du retour / Malfaçon",
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3,
            'placeholder': 'Décrivez la raison du retour...'}),
    )
    taches_a_copier = forms.MultipleChoiceField(
        label="Tâches à reprendre de l'OR précédent",
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        choices=[],
    )

    def __init__(self, taches=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if taches:
            self.fields['taches_a_copier'].choices = [
                (str(t.id), f"{t.libelle} ({t.get_statut_display()})") for t in taches
            ]


class ReouvertureORForm(forms.Form):
    raison = forms.CharField(
        label="Raison de la réouverture",
        widget=forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
    )
