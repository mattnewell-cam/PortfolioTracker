
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
from decimal import Decimal

import pandas as pd
import yfinance as yf

from portfolios.models import Portfolio, PortfolioSnapshot
from portfolios.benchmarks import get_benchmark_prices_usd

today = timezone.now().date()


def _get_close_series(hist_df, symbol, symbol_count):
    if hist_df is None or hist_df.empty:
        return None

    if isinstance(hist_df.columns, pd.MultiIndex):
        if symbol in hist_df.columns.get_level_values(0):
            try:
                return hist_df[symbol]["Close"]
            except KeyError:
                return None
    elif symbol_count == 1 and "Close" in hist_df.columns:
        return hist_df["Close"]

    return None


def build_currency_map(symbols):
    if not symbols:
        return {}

    tickers = yf.Tickers(" ".join(symbols))
    currency_map = {}
    for symbol in symbols:
        try:
            info = tickers.tickers.get(symbol)
            currency = None
            if info is not None:
                fast_info = getattr(info, "fast_info", {})
                currency = fast_info.get("currency") if hasattr(fast_info, "get") else None
            currency_map[symbol] = currency or "USD"
        except Exception:
            currency_map[symbol] = "USD"

    return currency_map


def build_price_map(symbols, snap_date, currency_map, price_hist):
    if not symbols or price_hist is None or price_hist.empty:
        return {}

    price_map = {}
    symbol_count = len(symbols)
    for symbol in symbols:
        try:
            close_series = _get_close_series(price_hist, symbol, symbol_count)
            if close_series is None:
                continue

            close_series = close_series[close_series.index.date <= snap_date]
            if close_series.empty:
                continue

            close_local = Decimal(str(close_series.iloc[-1]))
            if currency_map.get(symbol) == "GBp":
                close_local = close_local / Decimal("100")

            price_map[symbol] = close_local
        except Exception:
            continue

    return price_map


def build_fx_map(currencies, snap_date, fx_hist):
    if not currencies or fx_hist is None or fx_hist.empty:
        return {}

    fx_symbols = [f"{currency}USD=X" for currency in currencies if currency]
    fx_map = {}
    for currency in currencies:
        try:
            close_series = _get_close_series(fx_hist, f"{currency}USD=X", len(fx_symbols))
            if close_series is None:
                continue

            close_series = close_series[close_series.index.date <= snap_date]
            if close_series.empty:
                continue

            fx_map[currency] = Decimal(str(close_series.iloc[-1]))
        except Exception:
            continue

    return fx_map


portfolios = list(Portfolio.objects.all())
all_symbols = set()
for p in portfolios:
    all_symbols.update(p.holdings.keys())

currency_map = build_currency_map(all_symbols)
fx_currency_map = {symbol: ("GBP" if currency_map.get(symbol) == "GBp" else currency_map.get(symbol, "USD")) for symbol in all_symbols}
fx_currencies = {currency for currency in fx_currency_map.values() if currency and currency != "USD"}

start_date = today - timedelta(days=21)
end_date = today + timedelta(days=1)

symbols_list = list(all_symbols)
price_hist = (
    yf.download(
        symbols_list,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        interval="1d",
        group_by="ticker",
        progress=False,
    )
    if symbols_list
    else None
)

fx_symbols = [f"{currency}USD=X" for currency in fx_currencies if currency]
fx_hist = (
    yf.download(
        fx_symbols,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        interval="1d",
        group_by="ticker",
        progress=False,
    )
    if fx_symbols
    else None
)

for p in portfolios:
    print(f"→ Processing Portfolio {p.pk}")
    for days_ago in range(14, 0, -1):
        snap_date = today - timedelta(days=days_ago)
        snap_dt = timezone.make_aware(
            timezone.datetime(snap_date.year, snap_date.month, snap_date.day, 16, 0)
        )

        if snap_date.weekday() > 4:  # Don't create snapshot for weekends
            continue

        price_map = build_price_map(all_symbols, snap_date, currency_map, price_hist)
        fx_map = build_fx_map(fx_currencies, snap_date, fx_hist)

        total_value = p.cash_balance
        for symbol, qty in p.holdings.items():
            try:
                close_local = price_map.get(symbol)
                if close_local is None:
                    continue

                fx_currency = fx_currency_map.get(symbol, "USD")
                fx_rate = fx_map.get(fx_currency, Decimal("1.0")) if fx_currency != "USD" else Decimal("1.0")

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
