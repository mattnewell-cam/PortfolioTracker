from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import List, Sequence

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .constants import KEYWORD_TYPE_MAP
from .models import (
    Announcement,
    AnnouncementNotification,
    AnnouncementType,
    Company,
    CompanyAnnouncementPreference,
    EmailThrottle,
    UserAnnouncementTypePreference,
    Watchlist,
)

logger = logging.getLogger(__name__)

EMAILS_PER_HOUR_LIMIT = 20


def classify_announcement_type(title: str, summary: str | None = None) -> AnnouncementType:
    text = f"{title} {summary or ''}".lower()
    for code, keywords in KEYWORD_TYPE_MAP.items():
        if any(keyword in text for keyword in keywords):
            return AnnouncementType.objects.get(code=code)
    return AnnouncementType.objects.get(code="GENERAL")


def get_user_watchlists(user) -> Sequence[Watchlist]:
    return Watchlist.objects.filter(user=user).order_by("name")


def get_user_companies(user, watchlist_id: int | None = None) -> Iterable[Company]:
    companies = Company.objects.filter(watchlists__watchlist__user=user)
    if watchlist_id:
        companies = companies.filter(watchlists__watchlist_id=watchlist_id)
    return companies.distinct().order_by("name")


def get_user_company_ids(user, watchlist_id: int | None = None) -> List[int]:
    return list(get_user_companies(user, watchlist_id).values_list("id", flat=True))


def get_user_type_preference(user, announcement_type: AnnouncementType) -> bool:
    try:
        pref = UserAnnouncementTypePreference.objects.get(
            user=user, announcement_type=announcement_type
        )
        return pref.is_important
    except UserAnnouncementTypePreference.DoesNotExist:
        return announcement_type.default_is_important


def get_user_company_preference(
    user, company: Company, announcement_type: AnnouncementType
) -> bool | None:
    try:
        pref = CompanyAnnouncementPreference.objects.get(
            user=user, company=company, announcement_type=announcement_type
        )
        return pref.is_important
    except CompanyAnnouncementPreference.DoesNotExist:
        return None


def is_announcement_important_for_user(announcement: Announcement, user) -> bool:
    company_override = get_user_company_preference(
        user=user, company=announcement.company, announcement_type=announcement.announcement_type
    )
    if company_override is not None:
        return company_override
    return get_user_type_preference(user, announcement.announcement_type)


def get_user_feed(
    user,
    *,
    search: str | None = None,
    watchlist_id: int | None = None,
    announcement_type_code: str | None = None,
    company_id: int | None = None,
    months: int = 6,
) -> List[Announcement]:
    qs = Announcement.objects.select_related("company", "announcement_type").since(months)
    qs = qs.filter(company__watchlists__watchlist__user=user).distinct()
    if watchlist_id:
        qs = qs.filter(company__watchlists__watchlist_id=watchlist_id)
    if announcement_type_code:
        qs = qs.filter(announcement_type__code=announcement_type_code)
    if company_id:
        qs = qs.filter(company_id=company_id)
    qs = qs.search(search)
    announcements = [
        announcement
        for announcement in qs
        if is_announcement_important_for_user(announcement, user)
    ]
    return announcements


def record_and_send_notification(user, announcement: Announcement) -> bool:
    if not is_announcement_important_for_user(announcement, user):
        return False

    notification, created = AnnouncementNotification.objects.get_or_create(
        user=user, announcement=announcement
    )
    if not created:
        logger.debug(
            "Skipping email for %s and %s – already notified", user.pk, announcement.pk
        )
        return False

    if not EmailThrottle.can_send(user, EMAILS_PER_HOUR_LIMIT):
        logger.warning("Email rate limit reached for user %s", user.pk)
        notification.delivered = False
        notification.save(update_fields=["delivered"])
        return False

    subject = f"{announcement.company.ticker}: {announcement.title}"
    context = {
        "announcement": announcement,
        "user": user,
        "feed_url": settings.SITE_URL + reverse("announcements:feed"),
    }
    body = render_to_string("announcements/email/new_announcement.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
    EmailThrottle.increment(user, EMAILS_PER_HOUR_LIMIT)
    notification.delivered = True
    notification.sent_at = timezone.now()
    notification.save(update_fields=["delivered", "sent_at"])
    return True


def select_announcement_type_by_keyword(title: str, summary: str | None = None) -> AnnouncementType:
    return classify_announcement_type(title, summary)
