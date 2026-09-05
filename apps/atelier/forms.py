"""
Formulaires Atelier
"""
from django import forms
from .models import (
    Atelier, TypeOperation, OrdreReparation, Tache, 
    CompteRenduIntervention, PhotoIntervention, 
    FicheTechnique, FicheControle, TypeOR, StatutOR, 
    StatutTache, PrioriteTache
)
from apps.accounts.models import User, Role


class OrdreReparationForm(forms.ModelForm):
    class Meta:
        model = OrdreReparation
        fields = [
            'vehicule', 'atelier', 'responsable_atelier', 'reception', 
            'type_or', 'statut', 'diagnostic', 'observations', 'date_fin_prevue'
        ]
        widgets = {
            'vehicule': forms.Select(attrs={'class': 'form-select'}),
            'atelier': forms.Select(attrs={'class': 'form-select'}),
            'responsable_atelier': forms.Select(attrs={'class': 'form-select'}),
            'reception': forms.Select(attrs={'class': 'form-select'}),
            'type_or': forms.Select(attrs={'class': 'form-select'}),
            'statut': forms.Select(attrs={'class': 'form-select'}),
            'diagnostic': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4}),
            'observations': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
            'date_fin_prevue': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['atelier'].queryset = Atelier.objects.filter(is_active=True)
        self.fields['responsable_atelier'].queryset = User.objects.filter(is_active=True)
        self.fields['responsable_atelier'].required = False
        self.fields['reception'].required = False


class TacheForm(forms.ModelForm):
    class Meta:
        model = Tache
        fields = [
            'libelle', 'description', 'type_operation', 'statut', 
            'priorite', 'technicien', 'duree_estimee_minutes', 'duree_reelle_minutes'
        ]
        widgets = {
            'libelle': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ex: Changement plaquettes de frein'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'type_operation': forms.Select(attrs={'class': 'form-select'}),
            'statut': forms.Select(attrs={'class': 'form-select'}),
            'priorite': forms.Select(attrs={'class': 'form-select'}),
            'technicien': forms.Select(attrs={'class': 'form-select'}),
            'duree_estimee_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 15, 'step': 15}),
            'duree_reelle_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
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
            'description': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': 'Décrivez les travaux effectués...'
            }),
            'duree_minutes': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
            'pieces_utilisees': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 2,
                'placeholder': 'Ex: Plaquettes avant (x4), Disque avant gauche (x1)...'
            }),
            'observations': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
        }


class FicheControleForm(forms.ModelForm):
    class Meta:
        model = FicheControle
        exclude = ['id', 'date_inspection', 'inspecte_par']
        widgets = {
            'ordre_reparation': forms.Select(attrs={'class': 'form-select'}),
            'travail_a_effectuer': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'entree_le': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'sortir_le': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'immatriculation': forms.TextInput(attrs={'class': 'form-input'}),
            'marque': forms.TextInput(attrs={'class': 'form-input'}),
            'modele': forms.TextInput(attrs={'class': 'form-input'}),
            'kilometrage': forms.NumberInput(attrs={'class': 'form-input'}),
            'telephone': forms.TextInput(attrs={'class': 'form-input'}),
            
            # Statuts & Choix
            'jauge_carburant': forms.Select(attrs={'class': 'form-select'}),
            'type_vehicule': forms.Select(attrs={'class': 'form-select'}),
            'etat_general': forms.Select(attrs={'class': 'form-select'}),
            'pare_brise_etat': forms.Select(attrs={'class': 'form-select'}),
            'miroirs_retroviseurs_etat': forms.Select(attrs={'class': 'form-select'}),
            'phares_avant_etat': forms.Select(attrs={'class': 'form-select'}),
            'feux_arriere_etat': forms.Select(attrs={'class': 'form-select'}),
            
            # Textes & Commentaires
            'commentaires': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            'defauts_observes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3}),
            
            # Signatures & Noms
            'nom_receptionniste': forms.TextInput(attrs={'class': 'form-input'}),
            'nom_client_avant': forms.TextInput(attrs={'class': 'form-input'}),
            'nom_client_apres': forms.TextInput(attrs={'class': 'form-input'}),
            'nom_technicien': forms.TextInput(attrs={'class': 'form-input'}),
            'nom_controleur': forms.TextInput(attrs={'class': 'form-input'}),
            'signature_receptionniste': forms.HiddenInput(),
            'signature_client_avant': forms.HiddenInput(),
            'signature_client_apres': forms.HiddenInput(),
            'signature_technicien': forms.HiddenInput(),
            'signature_controleur': forms.HiddenInput(),
        }


class FicheTechniqueForm(forms.ModelForm):
    class Meta:
        model = FicheTechnique
        exclude = ['id', 'date_creation', 'cree_par']
        widgets = {
            'entre_id': forms.Select(attrs={'class': 'form-select'}),
            'numero_fiche': forms.TextInput(attrs={'class': 'form-input'}),
            'entree_le': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'sortie_le': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'nom_client': forms.TextInput(attrs={'class': 'form-input'}),
            'immatriculation': forms.TextInput(attrs={'class': 'form-input'}),
            'vehicule': forms.TextInput(attrs={'class': 'form-input'}),
            'kilometrage': forms.NumberInput(attrs={'class': 'form-input'}),
            'preconisation_courroie_distribution': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'rendre_pieces': forms.Select(attrs={'class': 'form-select'}),
            'ecrou_antivol': forms.Select(attrs={'class': 'form-select'}),
            'alarme': forms.Select(attrs={'class': 'form-select'}),
            
            # Jauge & Huile
            'jauge_carburant': forms.Select(attrs={'class': 'form-select'}),
            'niveau_huile_prise_en_charge': forms.Select(attrs={'class': 'form-select'}),
            'niveau_huile_apres_intervention': forms.Select(attrs={'class': 'form-select'}),
            
            # Diagnostic & Chiffrage
            'diagnostic': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': 'Diagnostic technique détaillé...'
            }),
            'pieces_recommandees': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 3,
                'placeholder': 'Liste des pièces recommandées...'
            }),
            'main_oeuvre_estimee': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'pieces_estimees': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.01'}),
            'temps_estime_heures': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5'}),
            'commentaires': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
            'observations': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2}),
            
            # Signatures
            'nom_controleur': forms.TextInput(attrs={'class': 'form-input'}),
            'nom_client_signataire': forms.TextInput(attrs={'class': 'form-input'}),
            'signature_controleur': forms.HiddenInput(),
            'signature_client': forms.HiddenInput(),
        }


class ORRetourForm(forms.Form):
    motif_retour = forms.CharField(
        label="Motif du retour / Malfaçon",
        widget=forms.Textarea(attrs={
            'class': 'form-textarea', 'rows': 3,
            'placeholder': 'Décrivez la raison du retour...'
        }),
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