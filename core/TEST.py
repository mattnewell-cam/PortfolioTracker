import yfinance as yf
import pprint

# ticker = yf.Ticker("amzn")
# info = ticker.info
#
# bid = info.get("bid")
# ask = info.get("ask")
# currency = info.get("currency")
# if currency != "USD":
#     fx_rate = yf.Ticker(f"{currency}USD=X").fast_info["last_price"]
#
#     if currency == "GBp":
#         fx_rate /= 100
#
#     print(fx_rate)
# # pprint.pprint(info)
#
# print(bid, ask)

import feedparser

def substack_name(url):
    # normalize to the feed endpoint
    if not url.endswith("/feed"):
        url = url.rstrip("/") + "/feed"
    feed = feedparser.parse(url)
    # feed.channel.title or feed['feed']['title']
    return feed.feed.get("title")

print(substack_name("https://www.readtrung.com/"))