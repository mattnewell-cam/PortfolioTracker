from django.db import models
from django.contrib.auth import get_user_model
from django.db.models import JSONField
from django.core.validators import MinValueValidator


User = get_user_model()

class Portfolio(models.Model):
    """
    Each user can have one or more portfolios.
    We'll start with a simple 'name' and a cash balance.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="portfolios"
    )
    name = models.CharField(max_length=100)
    cash_balance = models.FloatField(default=100000.00, validators=[MinValueValidator(0)])
    holdings = JSONField(default=dict)
    benchmarks = JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} – {self.name}"


class Order(models.Model):
    SIDE_CHOICES = [("BUY", "Buy"), ("SELL", "Sell")]

    portfolio      = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="orders")
    symbol         = models.CharField(max_length=20)
    side           = models.CharField(max_length=4, choices=SIDE_CHOICES)
    quantity       = models.PositiveIntegerField()
    price_executed = models.FloatField()       # local‐currency price
    currency       = models.CharField(max_length=10)
    fx_rate        = models.FloatField(default=1.0)       # FX rate at execution
    executed_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.portfolio} | {self.side} {self.quantity}×{self.symbol} @ {self.price_executed} {self.currency}"


class PortfolioSnapshot(models.Model):
    portfolio    = models.ForeignKey("Portfolio", on_delete=models.CASCADE, related_name="snapshots")
    timestamp    = models.DateTimeField(
        # auto_now_add=True  # Remove when you want to backfill
    )
    total_value  = models.FloatField()  # USD value at this moment

    class Meta:
        ordering = ["timestamp"]
        get_latest_by = "timestamp"
