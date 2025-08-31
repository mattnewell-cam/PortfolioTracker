from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from portfolios.models import Portfolio
from portfolios.constants import BENCHMARK_CHOICES


class SubstackRegistrationForm(UserCreationForm):
    substack_url = forms.URLField(label="Substack URL")
    benchmarks = forms.MultipleChoiceField(
        choices=BENCHMARK_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select up to 3 indices to benchmark against. This choice is permanent, so choose carefully.",
    )

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = UserCreationForm.Meta.fields + ("substack_url",)

    def clean_substack_url(self):
        url = self.cleaned_data["substack_url"].rstrip("/")
        if Portfolio.objects.filter(substack_url=url).exists():
            raise forms.ValidationError(
                "This Substack URL is already linked to an account."
            )
        return url

    def clean_benchmarks(self):
        selected = self.cleaned_data.get("benchmarks", [])
        if len(selected) > 3:
            raise forms.ValidationError("You can choose at most 3 benchmarks.")
        return selected
