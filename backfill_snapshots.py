
print("▶️  Starting backfill_snapshots.py …")

import os
import django

# 1) Point Django at your settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

# Show exactly which DATABASES setting is being used
from django.conf import settings
print("    Using DATABASES:", settings.DATABASES)

# 2) Now the rest of your code:
from django.utils import timezone
from datetime import timedelta
import yfinance as yf
from decimal import Decimal

from portfolios.models import Portfolio, PortfolioSnapshot
from portfolios.benchmarks import get_benchmark_prices_usd

today = timezone.now().date()

for p in Portfolio.objects.all():
    print(f"→ Processing Portfolio {p.pk}")
    for days_ago in range(14, 0, -1):
        snap_date = today - timedelta(days=days_ago)
        snap_dt = timezone.make_aware(
            timezone.datetime(snap_date.year, snap_date.month, snap_date.day, 16, 0)
        )

        if snap_date.weekday() > 4:  # Don't create snapshot for weekends
            continue

        total_value = p.cash_balance
        for symbol, qty in p.holdings.items():
            try:
                # 1) Attempt to fetch exactly snap_date → snap_date+1
                one_day_hist = yf.Ticker(symbol).history(
                    start=snap_date.isoformat(),
                    end=(snap_date + timedelta(days=1)).isoformat(),
                    interval="1d",
                )

                if not one_day_hist.empty:
                    # We have a row for snap_date
                    close_local = Decimal(str(one_day_hist["Close"].iloc[0]))
                else:
                    # 2) Market was closed on snap_date: fetch up to 7 days before snap_date
                    week_hist = yf.Ticker(symbol).history(
                        start=(snap_date - timedelta(days=7)).isoformat(),
                        end=(snap_date + timedelta(days=1)).isoformat(),
                        interval="1d",
                    )
                    # Filter to rows with date ≤ snap_date, then take the last closing price
                    week_hist = week_hist[week_hist.index.date <= snap_date]
                    if week_hist.empty:
                        # Still no data (e.g. impossible symbol, or more than 7 days back has no data)
                        continue
                    close_local = Decimal(str(week_hist["Close"].iloc[-1]))

                # 3) Determine FX rate (if needed)
                ticker = yf.Ticker(symbol)
                currency = ticker.fast_info.get("currency", "USD")

                if currency.upper() not in ("USD", None):
                    fx_tkr = yf.Ticker(f"{currency}USD=X")
                    fx_hist = fx_tkr.history(
                        start=snap_date.isoformat(),
                        end=(snap_date + timedelta(days=1)).isoformat(),
                        interval="1d",
                    )
                    if not fx_hist.empty:
                        fx_rate = Decimal(str(fx_hist["Close"].iloc[0]))
                    else:
                        # If FX data is missing for snap_date, fall back a few days as well:
                        fx_hist = fx_tkr.history(
                            start=(snap_date - timedelta(days=7)).isoformat(),
                            end=(snap_date + timedelta(days=1)).isoformat(),
                            interval="1d",
                        )
                        fx_hist = fx_hist[fx_hist.index.date <= snap_date]
                        fx_rate = Decimal(str(fx_hist["Close"].iloc[-1])) if not fx_hist.empty else Decimal("1.0")
                else:
                    fx_rate = Decimal("1.0")

                total_value += close_local * fx_rate * Decimal(str(qty))

            except Exception as e:
                # If anything goes wrong (bad ticker, network error, etc.), skip this symbol
                print(f"[WARNING] {symbol} on {snap_date}: {e}")
                continue

        # Ensure stored value matches the ``DecimalField`` precision
        total_value = total_value.quantize(Decimal("0.01"))
        benchmark_prices = get_benchmark_prices_usd(snap_date)
        PortfolioSnapshot.objects.update_or_create(
            portfolio=p,
            timestamp=snap_dt,
            defaults={
                "total_value": total_value,
                "benchmark_values": benchmark_prices,
            },
        )
        print(f"Created snapshot for {snap_date}----------------------")
        print(total_value)
        print(snap_dt)
