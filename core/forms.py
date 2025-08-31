from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
    UsernameField,
)
from django.core.validators import RegexValidator
from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator

from portfolios.models import Portfolio
from portfolios.constants import BENCHMARK_CHOICES


DISPLAY_NAME_VALIDATOR = RegexValidator(
    r"^[\w.@+\- ]+$", "Enter a valid display name."
)

class DisplayNameField(UsernameField):
    default_validators = [DISPLAY_NAME_VALIDATOR]


UserModel = get_user_model()
username_field = UserModel._meta.get_field(UserModel.USERNAME_FIELD)
username_field.validators = [
    v for v in username_field.validators if not isinstance(v, UnicodeUsernameValidator)
]
username_field.validators.insert(0, DISPLAY_NAME_VALIDATOR)


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
        field_classes = {
            **UserCreationForm.Meta.field_classes,
            "username": DisplayNameField,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Display Name"

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


class DisplayAuthenticationForm(AuthenticationForm):
    username = DisplayNameField(label="Display Name")
