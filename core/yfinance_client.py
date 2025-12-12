import os
import requests
import yfinance as yf



def get_quote(symbol):
    """
    Returns a dict: { "bid": <Decimal or float>, "ask": <Decimal or float> }
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info

    currency = info.get("currency")
    price = info.get("currentPrice", None)

    # UK tickers report in pence (GBp); convert to pounds for display and FX
    fx_currency = currency
    if currency == "GBp":
        fx_currency = "GBP"
        if price is not None:
            price = price / 100

    if fx_currency and fx_currency != "USD":
        fx_rate = yf.Ticker(f"{fx_currency}USD=X").fast_info["last_price"]
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
        "fx_rate": fx_rate,
        "market_state": info.get("marketState", None),
        "shortName": info.get("shortName"),
        "longName": info.get("longName"),
        "symbol": info.get("symbol") or symbol,
    }


