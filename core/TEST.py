import yfinance as yf
import pprint

ticker = yf.Ticker("amzn")
info = ticker.info

bid = info.get("bid")
ask = info.get("ask")
currency = info.get("currency")
if currency != "USD":
    fx_rate = yf.Ticker(f"{currency}USD=X").fast_info["last_price"]

    if currency == "GBp":
        fx_rate /= 100

    print(fx_rate)
# pprint.pprint(info)

print(bid, ask)