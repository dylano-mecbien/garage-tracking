# ─────────────────────────────────────────────────────────────────────
#  admin_custom/forms.py
#   - CentreForm : créer / modifier un centre (= un Client enfant)
#   - VehiculeClientMixin : dans le formulaire véhicule, la liste des
#     clients est groupée « Entreprise → Siège + ses centres »
# ─────────────────────────────────────────────────────────────────────
from django import forms

from apps.vehicules.models import Client


class CentreForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['nom', 'telephone', 'email', 'ville', 'adresse', 'is_active']
        labels = {'nom': "Nom du centre"}
        widgets = {'adresse': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, parent=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent = parent or self.instance.parent
        for name, field in self.fields.items():
            if name != 'is_active':
                field.widget.attrs.setdefault('class', 'form-control')
        # Téléphone facultatif : on reprend celui de l'entreprise s'il est vide
        self.fields['telephone'].required = False

    def clean_nom(self):
        nom = self.cleaned_data['nom'].strip()
        doublon = Client.objects.filter(parent=self.parent, nom__iexact=nom)
        if self.instance.pk:
            doublon = doublon.exclude(pk=self.instance.pk)
        if doublon.exists():
            raise forms.ValidationError("Cette entreprise a déjà un centre avec ce nom.")
        return nom

    def save(self, commit=True):
        centre = super().save(commit=False)
        centre.parent = self.parent
        centre.type_client = 'ENTREPRISE'
        if not centre.telephone:
            centre.telephone = self.parent.telephone
        if commit:
            centre.save()
        return centre


class VehiculeClientMixin:
    """
    À mettre devant ton VehiculeForm :
        class VehiculeForm(VehiculeClientMixin, forms.ModelForm): ...

    Le <select> client devient :
        SOCAPALM
            SOCAPALM (siège)
            Agence Bonabéri
            Plantation Kienké
        Particuliers
            Jean-Paul Mbarga
    Passe client=<Client> à la vue de création pour présélectionner.
    """

    def __init__(self, *args, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['client']
        qs = (Client.objects.filter(is_active=True).select_related('parent')
              .order_by('nom'))
        if self.instance.pk and self.instance.client_id:
            qs = qs | Client.objects.filter(pk=self.instance.client_id)
        field.queryset = qs
        if client is not None and not self.is_bound:
            self.initial['client'] = client.pk

        entreprises, particuliers = {}, []
        for c in qs:
            if c.parent_id:
                entreprises.setdefault(c.parent_id, [c.parent, []])[1].append((c.pk, c.nom))
            elif c.type_client == 'ENTREPRISE':
                entreprises.setdefault(c.pk, [c, []])
            else:
                particuliers.append((c.pk, str(c)))

        groupes = [('', '— Choisir un client / centre —')]
        for ent, centres in sorted(entreprises.values(), key=lambda x: x[0].nom.lower()):
            options = [(ent.pk, f"{ent.nom} (siège)")] + sorted(centres, key=lambda x: x[1].lower())
            groupes.append((ent.nom, options))
        if particuliers:
            groupes.append(("Particuliers", sorted(particuliers, key=lambda x: x[1].lower())))
        field.widget.choices = groupes
        field.label = "Client / Centre"
