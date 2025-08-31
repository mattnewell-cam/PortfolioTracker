from django.db import models
from django.contrib.auth import get_user_model
from django.db.models import JSONField
from django.core.validators import MinValueValidator
from decimal import Decimal


User = get_user_model()

class Portfolio(models.Model):
    """A single portfolio associated with each user."""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="portfolio"
    )
    name = models.CharField(max_length=100)
    substack_url = models.URLField(unique=True, blank=True, null=True)
    cash_balance = models.DecimalField(
        max_digits=20,
        decimal_places=2,
        default=Decimal("100000.00"),
        validators=[MinValueValidator(0)],
    )
    holdings = JSONField(default=dict)
    benchmarks = JSONField(default=list)
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} – {self.name}"


class Order(models.Model):
    SIDE_CHOICES = [("BUY", "Buy"), ("SELL", "Sell")]

    portfolio      = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="orders")
    symbol         = models.CharField(max_length=20)
    side           = models.CharField(max_length=4, choices=SIDE_CHOICES)
    quantity       = models.PositiveIntegerField()
    price_executed = models.DecimalField(max_digits=20, decimal_places=2)       # local‐currency price
    currency       = models.CharField(max_length=10)
    fx_rate        = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("1.00"))       # FX rate at execution
    executed_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.portfolio} | {self.side} {self.quantity}×{self.symbol} @ {self.price_executed} {self.currency}"


class PortfolioSnapshot(models.Model):
    portfolio    = models.ForeignKey("Portfolio", on_delete=models.CASCADE, related_name="snapshots")
    timestamp    = models.DateTimeField(
        # auto_now_add=True  # Remove when you want to backfill
    )
    total_value  = models.DecimalField(max_digits=20, decimal_places=2)  # USD value at this moment

    class Meta:
        ordering = ["timestamp"]
        get_latest_by = "timestamp"
