from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model


class SubstackRegistrationForm(UserCreationForm):
    substack_url = forms.URLField(label="Substack URL")

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = UserCreationForm.Meta.fields + ("substack_url",)
