from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Iterable

import feedparser
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from announcements.models import Announcement, Company
from announcements.services import record_and_send_notification, select_announcement_type_by_keyword

User = get_user_model()


class Command(BaseCommand):
    help = "Synchronise recent RNS announcements for tracked companies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=6,
            help="How many months back to fetch announcements (default: 6).",
        )
        parser.add_argument(
            "--tickers",
            nargs="*",
            help="Optional list of specific tickers to refresh (e.g. VOD LLOY).",
        )
        parser.add_argument(
            "--skip-emails",
            action="store_true",
            help="Do not send email notifications for new announcements.",
        )

    def handle(self, *args, **options):
        months = options["months"]
        tickers = options.get("tickers") or []
        send_emails = not options["skip_emails"]

        companies = Company.objects.all().order_by("ticker")
        if tickers:
            companies = companies.filter(ticker__in=[ticker.upper() for ticker in tickers])

        if not companies.exists():
            self.stdout.write(self.style.WARNING("No companies to process."))
            return

        cutoff = timezone.now() - timedelta(days=30 * months)

        for company in companies:
            self.stdout.write(f"Fetching RNS feed for {company.ticker}…")
            announcements = list(self.fetch_company_announcements(company, cutoff))
            created_count = 0
            for payload in announcements:
                with transaction.atomic():
                    announcement, created = Announcement.objects.update_or_create(
                        rns_id=payload["rns_id"],
                        defaults={
                            "company": company,
                            "announcement_type": payload["announcement_type"],
                            "title": payload["title"],
                            "summary": payload["summary"],
                            "url": payload["url"],
                            "published_at": payload["published_at"],
                            "raw_payload": payload["raw_payload"],
                        },
                    )
                if created:
                    created_count += 1
                    if send_emails:
                        self.notify_watchers(company, announcement)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed {len(announcements)} announcements for {company.ticker} ({created_count} new)."
                )
            )

    def fetch_company_announcements(self, company: Company, cutoff: datetime) -> Iterable[dict]:
        url = f"https://www.londonstockexchange.com/exchange/en/news/market-news/rss-feed.html?company={company.ticker}.L"
        feed = feedparser.parse(url)
        if getattr(feed, "bozo", False):
            self.stderr.write(
                self.style.WARNING(
                    f"Unable to parse feed for {company.ticker}: {getattr(feed, 'bozo_exception', 'unknown error')}"
                )
            )
            return []
        for entry in feed.entries:
            published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if not published_struct:
                continue
            published = datetime.fromtimestamp(time.mktime(published_struct), tz=timezone.utc)
            if published < cutoff:
                continue
            rns_id = entry.get("id") or entry.get("guid") or entry.get("link")
            if not rns_id:
                continue
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            announcement_type = select_announcement_type_by_keyword(title, summary)
            yield {
                "rns_id": rns_id,
                "title": title,
                "summary": summary,
                "url": entry.get("link", ""),
                "published_at": published,
                "announcement_type": announcement_type,
                "raw_payload": {
                    "title": entry.get("title"),
                    "link": entry.get("link"),
                    "summary": entry.get("summary"),
                    "published": entry.get("published"),
                    "updated": entry.get("updated"),
                },
            }

    def notify_watchers(self, company: Company, announcement: Announcement) -> None:
        watcher_ids = (
            User.objects.filter(announcement_watchlists__entries__company=company)
            .distinct()
            .values_list("id", flat=True)
        )
        for user in User.objects.filter(id__in=watcher_ids):
            if not user.email:
                continue
            record_and_send_notification(user, announcement)
