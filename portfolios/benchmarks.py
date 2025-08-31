from datetime import timedelta
import yfinance as yf

from .constants import BENCHMARK_CHOICES

def get_benchmark_prices_usd(date):
    """Return mapping of benchmark ticker -> USD price for given date."""
    prices = {}
    for ticker, _ in BENCHMARK_CHOICES:
        try:
            tkr = yf.Ticker(ticker)
            hist = tkr.history(
                start=(date - timedelta(days=7)).isoformat(),
                end=(date + timedelta(days=1)).isoformat(),
                interval="1d",
            )
            hist = hist[hist.index.date <= date]
            if hist.empty:
                continue
            last_close = float(hist["Close"].iloc[-1])
            currency = tkr.fast_info.get("currency", "USD")
            if currency not in ("USD", None):
                fx_tkr = yf.Ticker(f"{currency}USD=X")
                fx_hist = fx_tkr.history(
                    start=(date - timedelta(days=7)).isoformat(),
                    end=(date + timedelta(days=1)).isoformat(),
                    interval="1d",
                )
                fx_hist = fx_hist[fx_hist.index.date <= date]
                fx_rate = float(fx_hist["Close"].iloc[-1]) if not fx_hist.empty else 1.0
            else:
                fx_rate = 1.0
            prices[ticker] = last_close * fx_rate
        except Exception:
            continue
    return prices
