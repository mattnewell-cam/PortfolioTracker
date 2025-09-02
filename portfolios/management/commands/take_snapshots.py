import sys
from datetime import timedelta

import pytz
import yfinance as yf

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db.utils import OperationalError
from django.utils import timezone
from decimal import Decimal

from portfolios.models import Portfolio, PortfolioSnapshot
from portfolios.benchmarks import get_benchmark_prices_usd
from core.yfinance_client import get_quote  # updated import


class Command(BaseCommand):
    help = "Take a snapshot of every portfolio’s total USD value, credit recent dividends, and adjust for splits"

    def handle(self, *args, **options):
        now = timezone.now()
        since_date = (now - timedelta(days=1)).date()  # look back 24h

        # Ensure the database schema exists (helpful on fresh setups)
        try:
            portfolios = Portfolio.objects.all()
        except OperationalError:
            call_command("migrate", interactive=False)
            portfolios = Portfolio.objects.all()

        benchmark_prices = get_benchmark_prices_usd(now.date())

        for p in portfolios:
            # 1) Adjust holdings for any splits in the last 24 hours
            for symbol, qty in list(p.holdings.items()):
                try:
                    ticker = yf.Ticker(symbol)
                    splits = ticker.splits  # pandas Series indexed by ex-date
                    if splits is not None and not splits.empty:
                        new_qty = qty
                        for ex_date, ratio in splits.items():
                            if ex_date.date() >= since_date:
                                new_qty *= float(ratio)
                                self.stdout.write(
                                    f"↔ Adjusted {symbol} in Portfolio {p.pk}: "
                                    f"{qty} → {new_qty} (split ratio {ratio} on {ex_date.date()})"
                                )
                        if new_qty != qty:
                            p.holdings[symbol] = new_qty
                except Exception:
                    continue  # skip if yfinance fails

            # 2) Credit any dividends paid in the last 24 hours
            total_dividend_credit = Decimal("0")
            for symbol, qty in p.holdings.items():
                try:
                    ticker = yf.Ticker(symbol)
                    div_series = ticker.dividends
                    if div_series is not None and not div_series.empty:
                        for ex_date, div_amount in div_series.items():
                            if ex_date.date() >= since_date:
                                quote = get_quote(symbol)
                                fx_rate = Decimal(str(quote["fx_rate"]))
                                credit = Decimal(str(div_amount)) * Decimal(str(qty)) * fx_rate
                                total_dividend_credit += credit
                                self.stdout.write(
                                    f"➕ Credited {symbol} dividend ${credit:.2f} to Portfolio {p.pk} "
                                    f"(ex-date {ex_date.date()})"
                                )
                except Exception:
                    continue

            if total_dividend_credit > 0:
                p.cash_balance += total_dividend_credit
                p.save()

            # 3) Compute total USD value (cash + holdings)
            total_value = p.cash_balance
            for symbol, qty in p.holdings.items():
                try:
                    quote = get_quote(symbol)
                    fx_rate = Decimal(str(quote["fx_rate"]))
                    mid_local = Decimal(str(quote["price"]))
                    total_value += mid_local * fx_rate * Decimal(str(qty))
                except Exception as e:
                    self.stderr.write(f"⏱ Skipping {symbol} for Portfolio {p.pk}: {e}")
                    continue

            # 4) Create the snapshot record including benchmark values
            PortfolioSnapshot.objects.create(
                portfolio=p,
                timestamp=now,
                total_value=total_value,
                benchmark_values=benchmark_prices,
            )
            self.stdout.write(f"✔ Snapshot: Portfolio {p.pk} = ${total_value:.2f} at {now}")

        sys.exit(0)
