from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from core.yfinance_client import get_quote


class YFinanceClientTests(SimpleTestCase):
    @patch("core.yfinance_client.yf.Ticker")
    def test_get_quote_prefers_intraday_price(self, mock_ticker):
        ticker = Mock()
        ticker.info = {
            "currentPrice": 100,
            "currency": "USD",
            "open": 1,
            "bid": 1.0,
            "ask": 1.5,
            "symbol": "AAPL",
        }
        ticker.fast_info = {"last_price": 105, "currency": "USD"}
        mock_ticker.return_value = ticker

        quote = get_quote("AAPL")

        self.assertEqual(quote["price"], 105)
        self.assertEqual(quote["currency"], "USD")
        self.assertEqual(quote["fx_rate"], 1.0)

    @patch("core.yfinance_client.yf.Ticker")
    def test_get_quote_falls_back_to_previous_close(self, mock_ticker):
        ticker = Mock()
        ticker.info = {"regularMarketPreviousClose": 90, "currency": "USD", "open": 0}
        ticker.fast_info = {}
        mock_ticker.return_value = ticker

        quote = get_quote("MSFT")

        self.assertEqual(quote["price"], 90)
        self.assertFalse(quote["traded_today"])
