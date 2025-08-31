from django import forms
from .models import Portfolio, Order
from .constants import BENCHMARK_CHOICES


class PortfolioForm(forms.ModelForm):
    # allow up to 3 benchmarks
    benchmarks = forms.MultipleChoiceField(
        choices=BENCHMARK_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Select up to 3 indices to benchmark against."
    )

    class Meta:
        model = Portfolio
        fields = ["name", "cash_balance", "benchmarks"]

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


class PortfolioLookupForm(forms.Form):
    """Form for looking up a portfolio by its Substack URL."""

    substack_url = forms.URLField(label="Substack URL")

    def clean_substack_url(self):
        """Normalize the URL by removing any trailing slash."""
        return self.cleaned_data["substack_url"].rstrip("/")
