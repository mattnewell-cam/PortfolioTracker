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
    if currency != "USD":
        fx_rate = yf.Ticker(f"{currency}USD=X").fast_info["last_price"]
        if currency == "GBp":
            fx_rate /= 100

    else:
        fx_rate = 1.0

    return {
        "bid": info.get("bid", None),
        "ask": info.get("ask", None),
        "currency": info.get("currency", None),
        "fx_rate": fx_rate,
        "market_state": info.get("marketState", None),
    }

