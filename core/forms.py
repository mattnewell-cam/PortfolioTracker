from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from portfolios.models import Portfolio


class SubstackRegistrationForm(UserCreationForm):
    substack_url = forms.URLField(label="Substack URL")

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
