from django.core.management.base import BaseCommand, CommandError

from portfolios.models import Portfolio, PortfolioSnapshot


class Command(BaseCommand):
    help = "Delete portfolio snapshots without disturbing other data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--portfolio",
            type=int,
            help="Portfolio ID to delete snapshots for (omit to delete all)",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm snapshot deletion",
        )

    def handle(self, *args, **options):
        if not options.get("yes"):
            raise CommandError("Refusing to delete snapshots without --yes confirmation")

        queryset = PortfolioSnapshot.objects.all()
        portfolio_id = options.get("portfolio")
        if portfolio_id:
            try:
                portfolio = Portfolio.objects.get(pk=portfolio_id)
            except Portfolio.DoesNotExist:
                raise CommandError(f"Portfolio with id {portfolio_id} does not exist")
            queryset = queryset.filter(portfolio=portfolio)

        deleted_count, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} snapshot rows"))
