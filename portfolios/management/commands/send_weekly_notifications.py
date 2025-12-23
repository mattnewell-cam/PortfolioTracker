from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portfolios.models import Portfolio, NotificationSetting
from core.email import send_email


class Command(BaseCommand):
    help = "Send weekly trade summaries to followers who opted into weekly notifications."

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=7)
        portfolios = Portfolio.objects.filter(is_deleted=False).prefetch_related(
            "orders", "followers__follower__notification_setting"
        )
        sent_count = 0
        notifications_by_user = {}

        for portfolio in portfolios:
            recent_orders = list(
                portfolio.orders.filter(executed_at__gte=since).order_by("executed_at")
            )
            if not recent_orders:
                continue

            for follower_rel in portfolio.followers.select_related(
                "follower__notification_setting"
            ):
                follower = follower_rel.follower
                setting = getattr(follower, "notification_setting", None)
                preference = (
                    setting.preference
                    if setting
                    else NotificationSetting.PREFERENCE_IMMEDIATE
                )
                if preference != NotificationSetting.PREFERENCE_WEEKLY:
                    continue
                if not follower.email:
                    continue

                lines = [
                    f"{order.executed_at.strftime('%d %b')}: "
                    f"{portfolio.name} {'bought' if order.side == 'BUY' else 'sold'} "
                    f"{order.quantity} x {order.symbol} at {order.currency} {order.price_executed}"
                    for order in recent_orders
                ]
                notifications_by_user.setdefault(
                    follower.id,
                    {
                        "user": follower,
                        "portfolios": [],
                    },
                )["portfolios"].append(
                    {
                        "name": portfolio.name,
                        "lines": lines,
                    }
                )

        for notification in notifications_by_user.values():
            follower = notification["user"]
            sections = []
            for portfolio_summary in notification["portfolios"]:
                section = "<strong><u>" + portfolio_summary["name"] + "</u></strong>\n" + "\n".join(
                    portfolio_summary["lines"]
                )
                sections.append(section)
            body = "Here's your weekly summary:\n\n" + "\n\n".join(sections)
            send_email(
                "notifications@trackstack.uk",
                "Your weekly trade summaries",
                body,
                [follower.email],
                fail_silently=True,
            )
            sent_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Sent {sent_count} weekly notification emails.")
        )
