import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from stockmon import universe


class UniverseFilesTest(unittest.TestCase):
    def test_all_three_exchanges_load(self):
        companies = universe.load(ROOT)
        codes = {c["exchange"] for c in companies}
        self.assertEqual(codes, {"NYSE", "NASDAQ", "LSE"})
        self.assertGreater(len(companies), 100)

    def test_tickers_are_unique_within_an_exchange(self):
        for code in universe.EXCHANGES:
            rows = universe.load(ROOT, [code])
            tickers = [r["ticker"] for r in rows]
            self.assertEqual(len(tickers), len(set(tickers)), f"duplicate ticker in {code}")

    def test_every_company_has_provider_symbols(self):
        for company in universe.load(ROOT):
            for provider in ("stooq", "yahoo"):
                self.assertTrue(company["symbols"].get(provider), f"{company['ticker']} missing {provider}")

    def test_symbol_suffixes_match_the_exchange(self):
        for company in universe.load(ROOT):
            stooq, yahoo = company["symbols"]["stooq"], company["symbols"]["yahoo"]
            if company["exchange"] == "LSE":
                self.assertTrue(stooq.endswith(".uk"), stooq)
                self.assertTrue(yahoo.endswith(".L"), yahoo)
                self.assertEqual(company["currency"], "GBX")
            else:
                self.assertTrue(stooq.endswith(".us"), stooq)
                self.assertNotIn(".", yahoo, yahoo)
                self.assertEqual(company["currency"], "USD")

    def test_subset_selection(self):
        rows = universe.load(ROOT, ["LSE"])
        self.assertTrue(all(r["exchange"] == "LSE" for r in rows))

    def test_unknown_exchange_rejected(self):
        with self.assertRaises(ValueError):
            universe.load(ROOT, ["TSE"])

    def test_missing_fields_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "universe"))
            with open(os.path.join(tmp, "universe", "lse.json"), "w") as handle:
                json.dump([{"ticker": "X", "exchange": "LSE"}], handle)
            with self.assertRaises(ValueError):
                universe.load(tmp, ["LSE"])


if __name__ == "__main__":
    unittest.main()
