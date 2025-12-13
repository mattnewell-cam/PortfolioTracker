
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
from portfolios.constants import BENCHMARK_CHOICES

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


def build_currency_map(symbols, tickers=None):
    if not symbols:
        return {}

    tickers_obj = tickers or yf.Tickers(" ".join(symbols))
    currency_map = {}
    for symbol in symbols:
        try:
            info = tickers_obj.tickers.get(symbol)
            currency = None
            if info is not None:
                fast_info = getattr(info, "fast_info", {})
                currency = fast_info.get("currency") if hasattr(fast_info, "get") else None
            currency_map[symbol] = currency or "USD"
        except Exception:
            currency_map[symbol] = "USD"

    return currency_map


def _series_by_date(close_series):
    close_series = close_series.copy()
    close_series.index = close_series.index.date
    close_series = close_series[~close_series.index.duplicated(keep="last")]
    return close_series.sort_index()


def build_price_history_maps(symbols, currency_map, price_hist, target_dates, total_symbol_count=None):
    if not symbols or price_hist is None or price_hist.empty:
        return {snap_date: {} for snap_date in target_dates}

    price_map_by_date = {snap_date: {} for snap_date in target_dates}
    sorted_dates = sorted(target_dates)
    symbol_count = total_symbol_count or len(symbols)

    for symbol in symbols:
        try:
            close_series = _get_close_series(price_hist, symbol, symbol_count)
            if close_series is None or close_series.empty:
                continue

            close_series = _series_by_date(close_series)
            all_dates = sorted(set(close_series.index).union(sorted_dates))
            filled = close_series.reindex(all_dates).ffill()

            for snap_date in sorted_dates:
                price_value = filled.get(snap_date)
                if price_value is None or pd.isna(price_value):
                    continue

                close_local = Decimal(str(price_value))
                if currency_map.get(symbol) == "GBp":
                    close_local = close_local / Decimal("100")

                price_map_by_date[snap_date][symbol] = close_local
        except Exception:
            continue

    return price_map_by_date


def build_fx_history_maps(currencies, fx_hist, target_dates, total_symbol_count=None):
    if not currencies or fx_hist is None or fx_hist.empty:
        return {snap_date: {} for snap_date in target_dates}

    fx_symbols = [f"{currency}USD=X" for currency in currencies if currency]
    fx_map_by_date = {snap_date: {} for snap_date in target_dates}
    sorted_dates = sorted(target_dates)
    symbol_count = total_symbol_count or len(fx_symbols)

    for currency in currencies:
        try:
            close_series = _get_close_series(fx_hist, f"{currency}USD=X", symbol_count)
            if close_series is None or close_series.empty:
                continue

            close_series = _series_by_date(close_series)
            all_dates = sorted(set(close_series.index).union(sorted_dates))
            filled = close_series.reindex(all_dates).ffill()

            for snap_date in sorted_dates:
                fx_value = filled.get(snap_date)
                if fx_value is None or pd.isna(fx_value):
                    continue

                fx_map_by_date[snap_date][currency] = Decimal(str(fx_value))
        except Exception:
            continue

    return fx_map_by_date


def build_benchmark_price_maps(benchmark_symbols, currency_map, price_hist, fx_map_by_date, target_dates, total_symbol_count=None):
    if not benchmark_symbols:
        return {snap_date: {} for snap_date in target_dates}

    price_maps = build_price_history_maps(
        benchmark_symbols,
        currency_map,
        price_hist,
        target_dates,
        total_symbol_count=total_symbol_count,
    )

    benchmark_maps = {snap_date: {} for snap_date in target_dates}

    for snap_date in target_dates:
        fx_map = fx_map_by_date.get(snap_date, {})
        for symbol, close_local in price_maps.get(snap_date, {}).items():
            fx_currency = currency_map.get(symbol, "USD")
            if fx_currency == "GBp":
                fx_currency = "GBP"

            fx_rate = Decimal("1.0")
            if fx_currency and fx_currency != "USD":
                fx_rate = fx_map.get(fx_currency, Decimal("1.0"))

            benchmark_maps[snap_date][symbol] = close_local * fx_rate

    return benchmark_maps


portfolios = list(Portfolio.objects.all())
all_symbols = set()
for p in portfolios:
    all_symbols.update(p.holdings.keys())

benchmark_symbols = [ticker for ticker, _ in BENCHMARK_CHOICES]
all_requested_symbols = sorted(all_symbols.union(set(benchmark_symbols)))

tickers = yf.Tickers(" ".join(all_requested_symbols)) if all_requested_symbols else None
currency_map = build_currency_map(all_requested_symbols, tickers=tickers)

fx_currency_map = {
    symbol: ("GBP" if currency_map.get(symbol) == "GBp" else currency_map.get(symbol, "USD"))
    for symbol in all_requested_symbols
}
fx_currencies = {currency for currency in fx_currency_map.values() if currency and currency != "USD"}

start_date = today - timedelta(days=21)
end_date = today + timedelta(days=1)

fx_symbols = [f"{currency}USD=X" for currency in fx_currencies if currency]
download_symbols = list(dict.fromkeys(all_requested_symbols + fx_symbols))

price_hist = (
    yf.download(
        download_symbols,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        interval="1d",
        group_by="ticker",
        progress=False,
    )
    if download_symbols
    else None
)

snapshot_dates = [today - timedelta(days=days_ago) for days_ago in range(14, 0, -1) if (today - timedelta(days=days_ago)).weekday() <= 4]
price_maps_by_date = build_price_history_maps(
    all_symbols,
    currency_map,
    price_hist,
    snapshot_dates,
    total_symbol_count=len(download_symbols),
)
fx_maps_by_date = build_fx_history_maps(
    fx_currencies,
    price_hist,
    snapshot_dates,
    total_symbol_count=len(download_symbols),
)
benchmark_price_maps_by_date = build_benchmark_price_maps(
    benchmark_symbols,
    currency_map,
    price_hist,
    fx_maps_by_date,
    snapshot_dates,
    total_symbol_count=len(download_symbols),
)

for p in portfolios:
    print(f"→ Processing Portfolio {p.pk}")
    for snap_date in snapshot_dates:
        snap_dt = timezone.make_aware(
            timezone.datetime(snap_date.year, snap_date.month, snap_date.day, 16, 0)
        )

        price_map = price_maps_by_date.get(snap_date, {})
        fx_map = fx_maps_by_date.get(snap_date, {})
        benchmark_prices = benchmark_price_maps_by_date.get(snap_date, {})

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
