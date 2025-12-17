import yfinance as yf

def _safe_get(container, key):
    """Fetch a value from a mapping-like or attribute-bearing object."""

    if container is None:
        return None

    try:
        value = container.get(key)
        if value is not None:
            return value
    except Exception:
        pass

    try:
        return getattr(container, key)
    except Exception:
        return None


def _choose_price(info, fast_info):
    """Pick the freshest available price, preferring intraday quotes."""

    intraday_price = _safe_get(fast_info, "last_price")
    if intraday_price is None:
        intraday_price = info.get("regularMarketPrice") or info.get("currentPrice")

    if intraday_price is None:
        intraday_price = (
            _safe_get(fast_info, "regularMarketPreviousClose")
            or _safe_get(fast_info, "regular_market_previous_close")
        )

    if intraday_price is None:
        intraday_price = info.get("regularMarketPreviousClose")

    return intraday_price


def _quote_from_info(symbol, info, fx_rate_cache=None, fast_info=None):
    fx_rate_cache = fx_rate_cache if fx_rate_cache is not None else {}

    currency = _safe_get(fast_info, "currency") or info.get("currency")
    price = _choose_price(info, fast_info)

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
        "market_state": info.get("marketState", None) or _safe_get(fast_info, "market_state"),
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
    fast_info = getattr(ticker, "fast_info", None)

    return _quote_from_info(symbol, info, fast_info=fast_info)


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
            ticker_obj = tickers.tickers.get(symbol)
            if ticker_obj is None:
                continue
            quotes[symbol] = _quote_from_info(
                symbol,
                ticker_obj.info,
                fx_rate_cache,
                fast_info=getattr(ticker_obj, "fast_info", None),
            )
        except Exception:
            # Skip symbols that fail to fetch; they can be retried individually
            continue

    return quotes
