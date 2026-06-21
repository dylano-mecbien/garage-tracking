"""
Formulaires Comptes utilisateurs
"""
from django import forms
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import User, Role


class ConnexionForm(forms.Form):
    email = forms.EmailField(
        label="Adresse email",
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'votre@email.com',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'placeholder': '••••••••',
        })
    )
    remember_me = forms.BooleanField(required=False, label="Se souvenir de moi")

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email')
        password = self.cleaned_data.get('password')
        if email and password:
            # Vérification anti-brute force
            try:
                user_obj = User.objects.get(email=email)
                if user_obj.locked_until and user_obj.locked_until > timezone.now():
                    minutes = int((user_obj.locked_until - timezone.now()).total_seconds() / 60)
                    raise forms.ValidationError(
                        f"Compte temporairement verrouillé. Réessayez dans {minutes} minute(s)."
                    )
            except User.DoesNotExist:
                pass

            self.user_cache = authenticate(self.request, username=email, password=password)
            if self.user_cache is None:
                # Incrémenter tentatives échouées
                try:
                    user_obj = User.objects.get(email=email)
                    user_obj.failed_login_count += 1
                    if user_obj.failed_login_count >= 5: 
                        from datetime import timedelta
                        user_obj.locked_until = timezone.now() + timedelta(minutes=15)
                    user_obj.save(update_fields=['failed_login_count', 'locked_until'])
                except User.DoesNotExist:
                    pass
                raise forms.ValidationError("Email ou mot de passe incorrect.")
            elif not self.user_cache.is_active:
                raise forms.ValidationError("Ce compte est désactivé.")
            else:
                # Reset tentatives
                self.user_cache.failed_login_count = 0
                self.user_cache.locked_until = None
                self.user_cache.save(update_fields=['failed_login_count', 'locked_until'])
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class UserCreateForm(forms.ModelForm):

    class Meta:
        model = User
        fields = ['email', 'nom', 'prenom', 'telephone', 'role', 'atelier', 'matricule']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'nom': forms.TextInput(attrs={'class': 'form-input'}),
            'prenom': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone': forms.TextInput(attrs={'class': 'form-input'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'atelier': forms.Select(attrs={'class': 'form-select'}),
            'matricule': forms.TextInput(attrs={'class': 'form-input'}),
        }

class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['email', 'nom', 'prenom', 'telephone', 'role', 'atelier', 'matricule', 'is_active']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'nom': forms.TextInput(attrs={'class': 'form-input'}),
            'prenom': forms.TextInput(attrs={'class': 'form-input'}),
            'telephone': forms.TextInput(attrs={'class': 'form-input'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'atelier': forms.Select(attrs={'class': 'form-select'}),
            'matricule': forms.TextInput(attrs={'class': 'form-input'}),
        }


class ChangePasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label="Nouveau mot de passe",
        widget=forms.PasswordInput(attrs={'class': 'form-input'})
    )
    new_password2 = forms.CharField(
        label="Confirmer",
        widget=forms.PasswordInput(attrs={'class': 'form-input'})
    )

    def clean_new_password2(self):
        p1 = self.cleaned_data.get('new_password1')
        p2 = self.cleaned_data.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        if p1 and len(p1) < 8:
            raise forms.ValidationError("Le mot de passe doit contenir au moins 8 caractères.")
        return p2
