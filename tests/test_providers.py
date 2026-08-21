import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stockmon import providers

STOOQ_CSV = """Date,Open,High,Low,Close,Volume
2026-07-16,905.2,912.0,900.1,910.4,7412331
2026-07-17,910.9,915.5,899.0,901.2,6120044
2026-07-20,901.0,905.0,880.5,884.6,8930112
"""

YAHOO_JSON = {
    "chart": {
        "error": None,
        "result": [
            {
                "meta": {"currency": "GBp", "symbol": "HSBA.L"},
                "timestamp": [1752624000, 1752710400, 1752969600],
                "indicators": {
                    "quote": [{"close": [905.0, 900.0, 880.0]}],
                    "adjclose": [{"adjclose": [910.4, 901.2, 884.6]}],
                },
            }
        ],
    }
}

TWELVEDATA_JSON = {
    "meta": {"symbol": "HSBA:LSE", "currency": "GBp"},
    "values": [
        {"datetime": "2026-07-20", "close": "884.60"},
        {"datetime": "2026-07-17", "close": "901.20"},
        {"datetime": "2026-07-16", "close": "910.40"},
    ],
    "status": "ok",
}


class StooqParseTest(unittest.TestCase):
    def test_parses_and_sorts(self):
        s = providers.parse_stooq_csv(STOOQ_CSV)
        self.assertEqual(len(s), 3)
        self.assertEqual(s[0], (dt.date(2026, 7, 16), 910.4))
        self.assertEqual(s[-1], (dt.date(2026, 7, 20), 884.6))

    def test_skips_na_rows(self):
        csv = "Date,Open,High,Low,Close,Volume\n2026-07-16,1,1,1,N/A,0\n2026-07-17,1,1,1,12.5,0\n"
        self.assertEqual(providers.parse_stooq_csv(csv), [(dt.date(2026, 7, 17), 12.5)])

    def test_empty_and_no_data_raise(self):
        with self.assertRaises(providers.ProviderError):
            providers.parse_stooq_csv("")
        with self.assertRaises(providers.ProviderError):
            providers.parse_stooq_csv("No data")
        with self.assertRaises(providers.ProviderError):
            providers.parse_stooq_csv("Date,Open,High,Low,Close,Volume\n")


class YahooParseTest(unittest.TestCase):
    def test_prefers_adjusted_close(self):
        s = providers.parse_yahoo_json(YAHOO_JSON)
        self.assertEqual([c for _, c in s], [910.4, 901.2, 884.6])

    def test_falls_back_to_raw_close(self):
        payload = {"chart": {"result": [dict(YAHOO_JSON["chart"]["result"][0])]}}
        payload["chart"]["result"][0]["indicators"] = {"quote": [{"close": [905.0, 900.0, 880.0]}]}
        self.assertEqual([c for _, c in providers.parse_yahoo_json(payload)], [905.0, 900.0, 880.0])

    def test_skips_null_closes(self):
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": [1752624000, 1752710400],
                        "indicators": {"quote": [{"close": [None, 900.0]}]},
                    }
                ]
            }
        }
        self.assertEqual(len(providers.parse_yahoo_json(payload)), 1)

    def test_error_payloads_raise(self):
        for payload in (
            {"chart": {"error": {"code": "Not Found"}, "result": None}},
            {"chart": {"result": []}},
            {"chart": {"result": [{"timestamp": [], "indicators": {}}]}},
        ):
            with self.assertRaises(providers.ProviderError):
                providers.parse_yahoo_json(payload)


class TwelveDataParseTest(unittest.TestCase):
    def test_parses_and_sorts_ascending(self):
        s = providers.parse_twelvedata_json(TWELVEDATA_JSON)
        self.assertEqual(s[0][0], dt.date(2026, 7, 16))
        self.assertEqual(s[-1][1], 884.6)

    def test_error_status_raises(self):
        with self.assertRaises(providers.ProviderError):
            providers.parse_twelvedata_json({"status": "error", "message": "bad symbol"})


class SymbolMappingTest(unittest.TestCase):
    def setUp(self):
        self.lse = {
            "ticker": "BA.", "exchange": "LSE", "currency": "GBX",
            "symbols": {"stooq": "ba.uk", "yahoo": "BA.L"},
        }
        self.us = {
            "ticker": "AAPL", "exchange": "NASDAQ", "currency": "USD",
            "symbols": {"stooq": "aapl.us", "yahoo": "AAPL"},
        }

    def test_provider_picks_its_own_symbol(self):
        self.assertEqual(providers.StooqProvider().symbol_for(self.lse), "ba.uk")
        self.assertEqual(providers.YahooProvider().symbol_for(self.lse), "BA.L")
        self.assertEqual(providers.StooqProvider().symbol_for(self.us), "aapl.us")

    def test_twelvedata_derives_exchange_suffix(self):
        provider = providers.TwelveDataProvider(api_key="x")
        self.assertEqual(provider.symbol_for(self.lse), "BA:LSE")
        self.assertEqual(provider.symbol_for(self.us), "AAPL")

    def test_falls_back_to_ticker_when_unmapped(self):
        class Bare(providers.Provider):
            name = "nope"
        self.assertEqual(Bare().symbol_for(self.us), "AAPL")


class DemoProviderTest(unittest.TestCase):
    def test_is_deterministic_and_weekday_only(self):
        company = {"ticker": "AAPL", "exchange": "NASDAQ", "currency": "USD", "symbols": {}}
        a = providers.DemoProvider().fetch(company, 120)
        b = providers.DemoProvider().fetch(company, 120)
        self.assertEqual(a, b)
        self.assertTrue(all(d.weekday() < 5 for d, _ in a))
        self.assertTrue(all(c > 0 for _, c in a))

    def test_different_tickers_differ(self):
        base = {"exchange": "NASDAQ", "currency": "USD", "symbols": {}}
        a = providers.DemoProvider().fetch({**base, "ticker": "AAPL"}, 60)
        b = providers.DemoProvider().fetch({**base, "ticker": "MSFT"}, 60)
        self.assertNotEqual([c for _, c in a], [c for _, c in b])


class GetProviderTest(unittest.TestCase):
    def test_unknown_provider_raises(self):
        with self.assertRaises(providers.ProviderError):
            providers.get_provider("bloomberg")

    def test_known_providers(self):
        self.assertIsInstance(providers.get_provider("stooq"), providers.StooqProvider)
        self.assertIsInstance(providers.get_provider("demo", seed="x"), providers.DemoProvider)


class RetryTest(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = []

        class Flaky(providers.Provider):
            name = "flaky"
            def fetch(self, company, days):
                calls.append(1)
                if len(calls) < 2:
                    raise providers.ProviderError("boom")
                return [(dt.date(2026, 7, 20), 1.0)]

        providers.time.sleep = lambda _s: None  # keep the test fast
        self.assertEqual(len(providers.fetch_with_retry(Flaky(), {"ticker": "X", "symbols": {}}, 10)), 1)
        self.assertEqual(len(calls), 2)

    def test_gives_up_and_raises_last_error(self):
        class Dead(providers.Provider):
            name = "dead"
            def fetch(self, company, days):
                raise providers.ProviderError("always down")

        providers.time.sleep = lambda _s: None
        with self.assertRaises(providers.ProviderError):
            providers.fetch_with_retry(Dead(), {"ticker": "X", "symbols": {}}, 10, attempts=2)


if __name__ == "__main__":
    unittest.main()
