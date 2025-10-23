from __future__ import annotations

from collections import OrderedDict

from django import forms
from django.core.exceptions import ValidationError

from .models import Company, Watchlist
from .services import get_user_companies, get_user_type_preference


class WatchlistForm(forms.ModelForm):
    class Meta:
        model = Watchlist
        fields = ["name"]
        widgets = {"name": forms.TextInput(attrs={"class": "form-control"})}


class WatchlistCompanyForm(forms.Form):
    ticker = forms.CharField(
        max_length=20,
        help_text="Use the primary LSE ticker without the .L suffix (e.g. VOD).",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    isin = forms.CharField(
        max_length=12,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    website = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={"class": "form-control"}),
    )

    def clean_ticker(self):
        ticker = self.cleaned_data["ticker"].strip().upper()
        if not ticker:
            raise ValidationError("Ticker cannot be blank.")
        return ticker

    def save(self, user, watchlist: Watchlist) -> Company:
        ticker = self.cleaned_data["ticker"]
        company, created = Company.objects.get_or_create(
            ticker=ticker,
            defaults={
                "name": self.cleaned_data["name"],
                "isin": self.cleaned_data.get("isin") or "",
                "website": self.cleaned_data.get("website") or "",
            },
        )
        if not created:
            for field in ["name", "isin", "website"]:
                value = self.cleaned_data.get(field)
                if value:
                    setattr(company, field, value)
            company.save()
        watchlist.entries.get_or_create(company=company, defaults={})
        return company


class AnnouncementTypePreferenceForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        types = OrderedDict()
        from .models import AnnouncementType

        for announcement_type in AnnouncementType.objects.order_by("label"):
            field_name = f"type_{announcement_type.pk}"
            types[field_name] = announcement_type
            initial = get_user_type_preference(user, announcement_type)
            self.fields[field_name] = forms.BooleanField(
                required=False,
                initial=initial,
                label=announcement_type.label,
                help_text=announcement_type.description,
            )
            self.fields[field_name].widget.attrs.update({"class": "form-check-input"})
        self._type_lookup = types

    def save(self):
        from .models import UserAnnouncementTypePreference

        for field_name, announcement_type in self._type_lookup.items():
            is_important = self.cleaned_data.get(field_name, False)
            UserAnnouncementTypePreference.objects.update_or_create(
                user=self.user,
                announcement_type=announcement_type,
                defaults={"is_important": is_important},
            )


class CompanyPreferenceForm(forms.Form):
    company = forms.ModelChoiceField(queryset=Company.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        companies = get_user_companies(user)
        self.fields["company"].queryset = companies
        self.fields["company"].empty_label = "Select a company"

        from .models import AnnouncementType

        self._type_lookup = OrderedDict()
        if "company" in self.data:
            try:
                company = companies.get(pk=int(self.data["company"]))
            except (ValueError, Company.DoesNotExist):
                company = None
        else:
            company = self.initial.get("company") if self.initial else None

        for announcement_type in AnnouncementType.objects.order_by("label"):
            field_name = f"type_{announcement_type.pk}"
            self._type_lookup[field_name] = announcement_type
            initial = False
            if company:
                from .services import get_user_company_preference

                company_pref = get_user_company_preference(
                    user=user, company=company, announcement_type=announcement_type
                )
                if company_pref is not None:
                    initial = company_pref
                else:
                    initial = get_user_type_preference(user, announcement_type)
            else:
                initial = get_user_type_preference(user, announcement_type)
            self.fields[field_name] = forms.BooleanField(
                required=False,
                initial=initial,
                label=announcement_type.label,
                help_text=announcement_type.description,
            )
            self.fields[field_name].widget.attrs.update({"class": "form-check-input"})

    def save(self):
        from .models import CompanyAnnouncementPreference

        company = self.cleaned_data["company"]
        for field_name, announcement_type in self._type_lookup.items():
            is_important = self.cleaned_data.get(field_name, False)
            CompanyAnnouncementPreference.objects.update_or_create(
                user=self.user,
                company=company,
                announcement_type=announcement_type,
                defaults={"is_important": is_important},
            )
