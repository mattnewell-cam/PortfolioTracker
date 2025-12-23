from django import forms
from django.contrib.auth import get_user_model

from portfolios.models import Portfolio
from portfolios.constants import BENCHMARK_CHOICES


class EmailRegistrationForm(forms.Form):
    email = forms.EmailField()
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        User = get_user_model()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class EmailVerificationForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={"class": "input"}))


class PortfolioSetupForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    display_name = forms.CharField(label="Display Name")
    substack_url = forms.URLField(label="Substack URL")
    benchmarks = forms.MultipleChoiceField(
        choices=BENCHMARK_CHOICES,
        required=True,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select up to 3 indices to benchmark against.",
    )

    def clean_substack_url(self):
        url = self.cleaned_data["substack_url"].rstrip("/")
        conflict_qs = Portfolio.objects.filter(substack_url=url, is_deleted=False)
        if self.user:
            conflict_qs = conflict_qs.exclude(user=self.user)
        if conflict_qs.exists():
            raise forms.ValidationError(
                "This Substack URL is already linked to an account."
            )
        return url

    def clean_benchmarks(self):
        selected = self.cleaned_data.get("benchmarks", [])
        if not selected:
            raise forms.ValidationError("Select at least one benchmark.")
        if len(selected) > 3:
            raise forms.ValidationError("You can choose at most 3 benchmarks.")
        return selected
