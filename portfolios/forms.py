from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model

from .models import Portfolio, Order, NotificationSetting
from .constants import BENCHMARK_CHOICES


class PortfolioForm(forms.ModelForm):
    cash_balance = forms.DecimalField(max_digits=20, decimal_places=2, min_value=0)
    # allow up to 3 benchmarks
    benchmarks = forms.MultipleChoiceField(
        choices=BENCHMARK_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select up to 3 indices to benchmark against. This choice is permanent, so choose carefully."
    )

    class Meta:
        model = Portfolio
        fields = ["name", "cash_balance", "benchmarks", "is_private"]

    def clean_benchmarks(self):
        selected = self.cleaned_data.get("benchmarks", [])
        if len(selected) > 3:
            raise forms.ValidationError("You can choose at most 3 benchmarks.")
        return selected


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["symbol", "side", "quantity"]
        widgets = {
            "side": forms.Select(choices=Order.SIDE_CHOICES),
        }


class AllowedEmailForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "input"}))


class AllowedEmailUploadForm(forms.Form):
    file = forms.FileField(
        label="Bulk upload:",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "w-full !border-0 !shadow-none !bg-transparent !outline-none "
                    "focus:!outline-none focus:!ring-0 "
                    "file:mr-3 file:rounded-lg file:border-0 "
                    "file:bg-blue-600 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white "
                    "hover:file:bg-blue-700",
                "accept": ".csv,.tsv,.xlsx",
            }
        )
    )

    def clean_file(self):
        file = self.cleaned_data["file"]
        ext = Path(file.name).suffix.lower()
        allowed_extensions = {".csv", ".tsv", ".xlsx"}
        if ext not in allowed_extensions:
            raise forms.ValidationError("File must be .csv, .tsv, or .xlsx.")
        return file


class AccountForm(forms.ModelForm):
    display_name = forms.CharField(
        label="Display Name",
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={"class": "input flex-1"}),
    )

    class Meta:
        model = get_user_model()
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "input flex-1"})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_name"].initial = self.instance.first_name

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        User = get_user_model()
        if User.objects.filter(username=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def save(self, commit=True):
        user = self.instance
        email = self.cleaned_data["email"]
        user.email = email
        user.username = email
        user.first_name = self.cleaned_data.get("display_name", "")
        user.last_name = ""
        if commit:
            user.save()
        return user


class NotificationSettingForm(forms.Form):
    preference = forms.ChoiceField(
        choices=NotificationSetting.PREFERENCE_CHOICES,
        widget=forms.RadioSelect,
        label="Trade notifications",
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if user:
            self.fields["preference"].initial = NotificationSetting.for_user(user).preference

    def save(self):
        setting = NotificationSetting.for_user(self.user)
        setting.preference = self.cleaned_data["preference"]
        setting.save()
        return setting
