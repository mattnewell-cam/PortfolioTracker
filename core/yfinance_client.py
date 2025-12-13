import os
import requests
import yfinance as yf


def _quote_from_info(symbol, info, fx_rate_cache=None):
    fx_rate_cache = fx_rate_cache if fx_rate_cache is not None else {}

    currency = info.get("currency")
    price = info.get("currentPrice", None)

    # UK tickers report in pence (GBp); convert to pounds for display and FX
    fx_currency = currency
    if currency == "GBp":
        fx_currency = "GBP"
        if price is not None:
            price = price / 100

    if fx_currency and fx_currency != "USD":
        if fx_currency not in fx_rate_cache:
            fx_rate_cache[fx_currency] = yf.Ticker(f"{fx_currency}USD=X").fast_info["last_price"]
        fx_rate = fx_rate_cache[fx_currency]
    elif fx_currency == "USD":
        fx_rate = 1.0
    else:
        fx_rate = None

    traded_today = False if info.get("open") == 0.0 else True

    return {
        "price": price,
        "bid": info.get("bid"),
        "ask": info.get("ask"),
        "traded_today": traded_today,
        "currency": fx_currency,
        "native_currency": currency,
        "fx_rate": fx_rate,
        "market_state": info.get("marketState", None),
        "shortName": info.get("shortName"),
        "longName": info.get("longName"),
        "symbol": info.get("symbol") or symbol,
    }


def get_quote(symbol):
    """
    Returns a dict: { "bid": <Decimal or float>, "ask": <Decimal or float> }
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info

    return _quote_from_info(symbol, info)


def get_quotes(symbols):
    """Fetch quotes for multiple symbols in a single batch call when possible."""

    unique_symbols = [s for s in dict.fromkeys(symbols)]  # dedupe while preserving order
    if not unique_symbols:
        return {}

    fx_rate_cache = {}
    tickers = yf.Tickers(" ".join(unique_symbols))
    quotes = {}

    for symbol in unique_symbols:
        try:
            info = tickers.tickers.get(symbol)
            if info is None:
                continue
            quotes[symbol] = _quote_from_info(symbol, info.info, fx_rate_cache)
        except Exception:
            # Skip symbols that fail to fetch; they can be retried individually
            continue

    return quotes


