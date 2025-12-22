from django.db import models
from django.contrib.auth import get_user_model
from django.db.models import JSONField
from django.core.validators import MinValueValidator
import uuid
from decimal import Decimal


User = get_user_model()


class NotificationSetting(models.Model):
    PREFERENCE_IMMEDIATE = "immediate"
    PREFERENCE_WEEKLY = "weekly"
    PREFERENCE_NONE = "none"

    PREFERENCE_CHOICES = [
        (PREFERENCE_IMMEDIATE, "Every trade"),
        (PREFERENCE_WEEKLY, "Weekly summary"),
        (PREFERENCE_NONE, "No notifications"),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="notification_setting"
    )
    preference = models.CharField(
        max_length=20, choices=PREFERENCE_CHOICES, default=PREFERENCE_IMMEDIATE
    )

    def __str__(self):
        return f"Notifications for {self.user}: {self.preference}"

    @classmethod
    def for_user(cls, user):
        setting, _ = cls.objects.get_or_create(user=user)
        return setting


class Portfolio(models.Model):
    """A single portfolio associated with each user."""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="portfolio"
    )
    name = models.CharField(max_length=100)
    substack_url = models.URLField(unique=True, blank=True, null=True)
    url_tag = models.SlugField(max_length=100, unique=True, default=uuid.uuid4)
    short_description = models.CharField(max_length=200, blank=True, null=True)
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


class PortfolioFollower(models.Model):
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="followers"
    )
    follower = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="followed_portfolios"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("portfolio", "follower")


class PortfolioAllowedEmail(models.Model):
    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="allowed_emails"
    )
    email = models.EmailField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("portfolio", "email")

    def __str__(self):
        return f"{self.email} for {self.portfolio}"


class Order(models.Model):
    SIDE_CHOICES = [("BUY", "Buy"), ("SELL", "Sell")]

    portfolio      = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="orders")
    symbol         = models.CharField(max_length=20)
    side           = models.CharField(max_length=4, choices=SIDE_CHOICES)
    quantity       = models.PositiveIntegerField()
    price_executed = models.DecimalField(max_digits=20, decimal_places=2)       # local‐currency price
    currency       = models.CharField(max_length=10)
    fx_rate        = models.DecimalField(max_digits=20, decimal_places=10, default=Decimal("1.0"))       # FX rate at execution
    executed_at    = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.symbol:
            self.symbol = self.symbol.upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.portfolio} | {self.side} {self.quantity}×{self.symbol} @ {self.price_executed} {self.currency}"


class PortfolioSnapshot(models.Model):
    portfolio    = models.ForeignKey("Portfolio", on_delete=models.CASCADE, related_name="snapshots")
    timestamp    = models.DateTimeField(
        # auto_now_add=True  # Remove when you want to backfill
    )
    total_value  = models.DecimalField(max_digits=20, decimal_places=2)  # USD value at this moment
    benchmark_values = JSONField(default=dict)

    class Meta:
        ordering = ["timestamp"]
        get_latest_by = "timestamp"
