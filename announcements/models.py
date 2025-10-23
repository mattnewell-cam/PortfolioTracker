from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AnnouncementType(TimestampedModel):
    code = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    default_is_important = models.BooleanField(default=False)

    class Meta:
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label


class Company(TimestampedModel):
    name = models.CharField(max_length=255)
    ticker = models.CharField(max_length=20, unique=True)
    isin = models.CharField(max_length=12, blank=True, null=True)
    website = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.ticker})"


class AnnouncementQuerySet(models.QuerySet):
    def since(self, months: int = 6) -> "AnnouncementQuerySet":
        boundary = timezone.now() - timedelta(days=30 * months)
        return self.filter(published_at__gte=boundary)

    def search(self, term: str | None) -> "AnnouncementQuerySet":
        if not term:
            return self
        return self.filter(
            Q(title__icontains=term)
            | Q(summary__icontains=term)
            | Q(company__name__icontains=term)
            | Q(company__ticker__icontains=term)
        )


class Announcement(TimestampedModel):
    objects = AnnouncementQuerySet.as_manager()

    company = models.ForeignKey(
        Company, related_name="announcements", on_delete=models.CASCADE
    )
    announcement_type = models.ForeignKey(
        AnnouncementType, related_name="announcements", on_delete=models.PROTECT
    )
    rns_id = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    url = models.URLField()
    published_at = models.DateTimeField()
    raw_payload = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self) -> str:
        return f"{self.company.ticker}: {self.title}"


class Watchlist(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="announcement_watchlists",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.user})"


class WatchlistCompany(TimestampedModel):
    watchlist = models.ForeignKey(
        Watchlist, related_name="entries", on_delete=models.CASCADE
    )
    company = models.ForeignKey(
        Company, related_name="watchlists", on_delete=models.CASCADE
    )

    class Meta:
        unique_together = ("watchlist", "company")
        ordering = ["company__name"]

    def __str__(self) -> str:
        return f"{self.watchlist}: {self.company}"


class UserAnnouncementTypePreference(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="announcement_type_preferences",
        on_delete=models.CASCADE,
    )
    announcement_type = models.ForeignKey(
        AnnouncementType, related_name="user_preferences", on_delete=models.CASCADE
    )
    is_important = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "announcement_type")

    def __str__(self) -> str:
        status = "important" if self.is_important else "ignore"
        return f"{self.user} – {self.announcement_type} ({status})"


class CompanyAnnouncementPreference(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="company_announcement_preferences",
        on_delete=models.CASCADE,
    )
    company = models.ForeignKey(
        Company, related_name="user_preferences", on_delete=models.CASCADE
    )
    announcement_type = models.ForeignKey(
        AnnouncementType, related_name="company_preferences", on_delete=models.CASCADE
    )
    is_important = models.BooleanField(default=True)

    class Meta:
        unique_together = ("user", "company", "announcement_type")

    def __str__(self) -> str:
        status = "important" if self.is_important else "ignore"
        return f"{self.user} – {self.company} – {self.announcement_type} ({status})"


class AnnouncementNotification(TimestampedModel):
    announcement = models.ForeignKey(
        Announcement, related_name="notifications", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="announcement_notifications",
        on_delete=models.CASCADE,
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    delivered = models.BooleanField(default=True)

    class Meta:
        unique_together = ("announcement", "user")
        ordering = ["-sent_at"]

    def __str__(self) -> str:
        return f"{self.announcement} → {self.user}"  # pragma: no cover


class EmailThrottle(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="announcement_email_windows",
        on_delete=models.CASCADE,
    )
    window_start = models.DateTimeField()
    emails_sent = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ("user", "window_start")
        ordering = ["-window_start"]

    @classmethod
    def _current_window(cls) -> timezone.datetime:
        now = timezone.now()
        return now.replace(minute=0, second=0, microsecond=0)

    @classmethod
    def can_send(cls, user, limit: int) -> bool:
        window_start = cls._current_window()
        window, _ = cls.objects.get_or_create(
            user=user, window_start=window_start, defaults={"emails_sent": 0}
        )
        return window.emails_sent < limit

    @classmethod
    def increment(cls, user, limit: int) -> None:
        window_start = cls._current_window()
        window, _ = cls.objects.get_or_create(
            user=user, window_start=window_start, defaults={"emails_sent": 0}
        )
        if window.emails_sent < limit:
            window.emails_sent += 1
            window.save(update_fields=["emails_sent"])
