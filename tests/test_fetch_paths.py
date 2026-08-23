"""End-to-end provider tests with the HTTP layer stubbed.

The network is not touched here - these pin the URL each provider builds and
prove the response flows all the way through to metrics.
"""

import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stockmon import analysis, providers, snapshot
from tests.test_providers import STOOQ_CSV, TWELVEDATA_JSON, YAHOO_JSON


class StubHTTP:
    """Records requested URLs and replays a canned body."""

    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else body.encode()
        self.urls = []

    def __call__(self, url, timeout=30.0, headers=None):
        self.urls.append(url)
        return self.body


class FetchPathTest(unittest.TestCase):
    def setUp(self):
        self.real_get = providers._get
        self.lse = {
            "ticker": "HSBA", "name": "HSBC Holdings plc", "sector": "Financials",
            "exchange": "LSE", "currency": "GBX",
            "symbols": {"stooq": "hsba.uk", "yahoo": "HSBA.L"},
        }

    def tearDown(self):
        providers._get = self.real_get

    def test_stooq_url_and_series(self):
        stub = StubHTTP(STOOQ_CSV)
        providers._get = stub
        series = providers.StooqProvider().fetch(self.lse, 200)

        url = stub.urls[0]
        self.assertTrue(url.startswith("https://stooq.com/q/d/l/?"), url)
        self.assertIn("s=hsba.uk", url)
        self.assertIn("i=d", url)
        self.assertIn("d1=", url)
        self.assertEqual(series[-1], (dt.date(2026, 7, 20), 884.6))

    def test_yahoo_url_and_series(self):
        stub = StubHTTP(json.dumps(YAHOO_JSON))
        providers._get = stub
        series = providers.YahooProvider().fetch(self.lse, 200)

        url = stub.urls[0]
        self.assertIn("query1.finance.yahoo.com/v8/finance/chart/HSBA.L", url)
        self.assertIn("interval=1d", url)
        self.assertIn("range=1y", url)  # 200 days needs more than 6mo
        self.assertEqual([c for _, c in series], [910.4, 901.2, 884.6])

    def test_yahoo_short_lookback_uses_6mo(self):
        providers._get = StubHTTP(json.dumps(YAHOO_JSON))
        providers.YahooProvider().fetch(self.lse, 120)
        self.assertIn("range=6mo", providers._get.urls[0])

    def test_yahoo_year_on_year_lookback_asks_for_two_years(self):
        # 500 days is more than a 1y range can serve.
        providers._get = StubHTTP(json.dumps(YAHOO_JSON))
        providers.YahooProvider().fetch(self.lse, 500)
        self.assertIn("range=2y", providers._get.urls[0])

    def test_twelvedata_url_and_series(self):
        stub = StubHTTP(json.dumps(TWELVEDATA_JSON))
        providers._get = stub
        series = providers.TwelveDataProvider(api_key="secret").fetch(self.lse, 200)

        url = stub.urls[0]
        self.assertIn("api.twelvedata.com/time_series", url)
        self.assertIn("symbol=HSBA%3ALSE", url)
        self.assertIn("apikey=secret", url)
        self.assertEqual(len(series), 3)

    def test_http_errors_surface_as_provider_errors(self):
        def boom(url, timeout=30.0, headers=None):
            raise providers.ProviderError("HTTP 429 for " + url)

        providers._get = boom
        with self.assertRaises(providers.ProviderError):
            providers.StooqProvider().fetch(self.lse, 200)


class SnapshotBuildTest(unittest.TestCase):
    """The whole pipeline over the real universe files, with a stub provider."""

    def setUp(self):
        today = dt.date.today()

        class Fake(providers.Provider):
            name = "fake"
            delay = 0.0

            def fetch(self, company, days):
                # A clean 10% fall over the last month, 10% rise the month before.
                return [
                    (today - dt.timedelta(days=62), 100.0),
                    (today - dt.timedelta(days=31), 110.0),
                    (today, 99.0),
                ]

        self.provider = Fake()

    def test_builds_rows_and_meta(self):
        result = snapshot.build(ROOT, self.provider, exchanges=["LSE"], limit=5, cache_hours=0)
        self.assertEqual(len(result["companies"]), 5)
        self.assertEqual(result["meta"]["counts"]["decliners"], 5)
        self.assertEqual(result["meta"]["counts"]["errors"], 0)
        self.assertFalse(result["meta"]["is_demo"])
        self.assertEqual(result["exchanges"][0]["code"], "LSE")

        row = result["companies"][0]
        self.assertAlmostEqual(row["mom_pct"], -10.0, places=1)
        self.assertGreater(row["prev_mom_pct"], 0)
        self.assertFalse(row["sustained"])   # last month was up
        self.assertEqual(row["currency"], "GBX")
        self.assertIn("spark", row)

    def test_failures_are_recorded_not_raised(self):
        class Broken(providers.Provider):
            name = "broken"
            delay = 0.0

            def fetch(self, company, days):
                raise providers.ProviderError("symbol not found")

        providers.time.sleep = lambda _s: None
        result = snapshot.build(ROOT, Broken(), exchanges=["NYSE"], limit=3)
        self.assertEqual(result["companies"], [])
        self.assertEqual(result["meta"]["counts"]["errors"], 3)
        self.assertIn("symbol not found", result["meta"]["errors"][0]["error"])

    def test_rows_are_sorted_worst_first(self):
        values = [r["mom_pct"] for r in snapshot.build(ROOT, providers.DemoProvider(), limit=30)["companies"]]
        self.assertEqual(values, sorted(values))

    def test_cache_round_trip(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cache", "x.csv")
            series = [(dt.date(2026, 7, 1), 10.5), (dt.date(2026, 7, 2), 11.0)]
            snapshot.write_cache(path, series)
            self.assertEqual(snapshot.read_cache(path, max_age_hours=24), series)
            self.assertIsNone(snapshot.read_cache(path, max_age_hours=0))
            self.assertIsNone(snapshot.read_cache(os.path.join(tmp, "missing.csv"), 24))


if __name__ == "__main__":
    unittest.main()
