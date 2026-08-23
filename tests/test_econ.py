"""Tests for the economic tracker.

Everything here is offline: the World Bank parser runs against recorded
response shapes, and the scoring is pure arithmetic.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from econ import countries, indicators, providers, pulse, snapshot


# --------------------------------------------------------------------------
# catalogue integrity
# --------------------------------------------------------------------------

class CatalogueTests(unittest.TestCase):
    def test_indicator_codes_are_unique(self):
        self.assertEqual(len(indicators.BY_CODE), len(indicators.INDICATORS))

    def test_every_indicator_is_complete(self):
        families = {f["id"] for f in indicators.FAMILIES}
        for entry in indicators.INDICATORS:
            with self.subTest(entry["code"]):
                for field in ("code", "family", "pulse", "label", "short",
                              "unit", "direction", "since", "note"):
                    self.assertIn(field, entry)
                self.assertIn(entry["family"], families)
                self.assertIn(entry["direction"],
                              {"up_good", "down_good", "target", "neutral"})

    def test_no_neutral_indicator_feeds_the_pulse(self):
        # A neutral indicator has no "better" direction, so scoring one would
        # be meaningless - and it would silently drag the composite around.
        for code in indicators.PULSE_CODES:
            self.assertNotEqual(indicators.get(code)["direction"], "neutral", code)

    def test_every_country_has_an_inflation_target(self):
        for country in countries.COUNTRIES:
            self.assertIsInstance(country["inflation_target"], float)


# --------------------------------------------------------------------------
# World Bank parsing
# --------------------------------------------------------------------------

class WorldBankParserTests(unittest.TestCase):
    def test_parses_a_normal_response(self):
        payload = [
            {"page": 1, "pages": 1, "per_page": 20000, "total": 3},
            [
                {"countryiso3code": "USA", "date": "2024", "value": 2.8},
                {"countryiso3code": "GBR", "date": "2023", "value": "0.4"},
                {"countryiso3code": "NGA", "date": "2024", "value": 3.4},
            ],
        ]
        self.assertEqual(
            providers.parse_worldbank_json(payload),
            {("USA", 2024): 2.8, ("GBR", 2023): 0.4, ("NGA", 2024): 3.4},
        )

    def test_drops_null_observations_rather_than_zeroing_them(self):
        # A missing year must not become 0.0 - that would read as a collapse.
        payload = [{"page": 1}, [
            {"countryiso3code": "IRL", "date": "2024", "value": None},
            {"countryiso3code": "IRL", "date": "2023", "value": 5.1},
        ]]
        self.assertEqual(providers.parse_worldbank_json(payload), {("IRL", 2023): 5.1})

    def test_empty_result_set_is_not_an_error(self):
        self.assertEqual(providers.parse_worldbank_json([{"page": 1}, None]), {})

    def test_api_level_error_is_raised(self):
        payload = [{"message": [{"id": "120", "key": "Invalid value",
                                 "value": "The indicator was not found."}]}]
        with self.assertRaises(providers.ProviderError) as ctx:
            providers.parse_worldbank_json(payload)
        self.assertIn("not found", str(ctx.exception))

    def test_unparseable_shapes_raise(self):
        for payload in ([], {"unexpected": True}, [{"page": 1}, "not a list"]):
            with self.subTest(payload=payload):
                with self.assertRaises(providers.ProviderError):
                    providers.parse_worldbank_json(payload)

    def test_non_numeric_values_are_skipped(self):
        payload = [{"page": 1}, [
            {"countryiso3code": "CAN", "date": "2024", "value": "n/a"},
            {"countryiso3code": "CAN", "date": "bad-year", "value": 1.0},
            {"countryiso3code": "CAN", "date": "2023", "value": 1.5},
        ]]
        self.assertEqual(providers.parse_worldbank_json(payload), {("CAN", 2023): 1.5})

    def test_governance_series_are_requested_from_their_own_source(self):
        # These return "indicator not found" against the default WDI database.
        url = providers.WorldBankProvider().url_for("PV.EST", ["USA"], 1996, 2025, source=3)
        self.assertIn("source=3", url)
        plain = providers.WorldBankProvider().url_for("NY.GDP.MKTP.KD.ZG", ["USA"], 1975, 2025)
        self.assertNotIn("source=", plain)

    def test_date_range_is_not_percent_encoded(self):
        url = providers.WorldBankProvider().url_for("NY.GDP.MKTP.KD.ZG", ["USA", "NGA"], 1975, 2025)
        self.assertIn("date=1975:2025", url)
        self.assertIn("country/USA;NGA/", url)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

class OrientationTests(unittest.TestCase):
    def test_up_good_and_down_good_are_mirror_images(self):
        self.assertEqual(pulse.orient(3.0, "up_good"), 3.0)
        self.assertEqual(pulse.orient(3.0, "down_good"), -3.0)

    def test_target_penalises_both_sides(self):
        # 5% inflation against a 2% target is exactly as far off as -1%.
        self.assertEqual(pulse.orient(5.0, "target", 2.0), pulse.orient(-1.0, "target", 2.0))

    def test_target_respects_a_country_specific_goal(self):
        # 15% inflation is a disaster against 2% and merely high against 7.5%.
        self.assertLess(pulse.orient(15.0, "target", 2.0), pulse.orient(15.0, "target", 7.5))

    def test_neutral_is_never_scored(self):
        self.assertIsNone(pulse.orient(3.0, "neutral"))


class PercentileTests(unittest.TestCase):
    def test_midpoint(self):
        self.assertEqual(pulse.percentile_rank([1, 2, 3, 4], 2.5), 50.0)

    def test_ties_count_as_half(self):
        self.assertEqual(pulse.percentile_rank([5, 5, 5], 5), 50.0)

    def test_extremes(self):
        self.assertEqual(pulse.percentile_rank([1, 2, 3], 0), 0.0)
        self.assertEqual(pulse.percentile_rank([1, 2, 3], 9), 100.0)

    def test_empty_sample_raises(self):
        with self.assertRaises(ValueError):
            pulse.percentile_rank([], 1)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.series = {year: value for year, value in
                       zip(range(2010, 2025),
                           [2, 3, -1, 4, 2, 2.5, 3, 1, 0, -4, 6, 2, 1.5, 2, 2.2])}

    def test_best_and_worst_years_land_at_the_extremes(self):
        scored = pulse.score_series(self.series, "up_good")
        self.assertEqual(max(scored, key=scored.get), 2020)   # the 6% year
        self.assertEqual(min(scored, key=scored.get), 2019)   # the -4% year

    def test_direction_flips_the_ranking(self):
        up = pulse.score_series(self.series, "up_good")
        down = pulse.score_series(self.series, "down_good")
        self.assertEqual(max(down, key=down.get), min(up, key=up.get))

    def test_short_series_are_reported_but_not_graded(self):
        self.assertEqual(pulse.score_series({2023: 1.0, 2024: 2.0}, "up_good"), {})

    def test_neutral_series_are_never_graded(self):
        self.assertEqual(pulse.score_series(self.series, "neutral"), {})

    def test_describe_finds_the_extremes(self):
        stats = pulse.describe(self.series)
        self.assertEqual(stats["min_year"], 2019)
        self.assertEqual(stats["max_year"], 2020)
        self.assertEqual(stats["count"], 15)

    def test_describe_handles_an_empty_series(self):
        self.assertEqual(pulse.describe({})["count"], 0)

    def test_latest_reading_compares_against_the_previous_observation(self):
        # Not the previous calendar year: these series have gaps, and dressing
        # a five-year-old comparison up as year-on-year would be a lie.
        gappy = {2010: 1.0, 2018: 5.0, 2024: 2.0}
        reading = pulse.latest_reading(gappy, {})
        self.assertEqual(reading["year"], 2024)
        self.assertEqual(reading["prev_year"], 2018)
        self.assertEqual(reading["change"], -3.0)

    def test_latest_reading_of_nothing_is_none(self):
        self.assertIsNone(pulse.latest_reading({}, {}))


class CompositeTests(unittest.TestCase):
    def test_averages_components(self):
        parts = {"a": {2020: 10, 2021: 90}, "b": {2020: 20, 2021: 80},
                 "c": {2020: 30, 2021: 70}, "d": {2020: 40, 2021: 60}}
        self.assertEqual(pulse.composite(parts), {2020: 25.0, 2021: 75.0})

    def test_thin_years_are_dropped_rather_than_averaged(self):
        self.assertEqual(pulse.composite({"a": {2020: 10}, "b": {2020: 20}}), {})

    def test_trend_needs_a_reference_year(self):
        self.assertIsNone(pulse.trend({2024: 50.0}))

    def test_trend_directions(self):
        self.assertEqual(pulse.trend({2020: 40.0, 2024: 60.0})["direction"], "improving")
        self.assertEqual(pulse.trend({2020: 60.0, 2024: 40.0})["direction"], "deteriorating")
        self.assertEqual(pulse.trend({2020: 50.0, 2024: 52.0})["direction"], "steady")

    def test_bands_cover_the_whole_range(self):
        self.assertEqual(pulse.band(None), "unknown")
        for score in range(0, 101):
            self.assertNotEqual(pulse.band(float(score)), "unknown")


# --------------------------------------------------------------------------
# snapshot assembly
# --------------------------------------------------------------------------

class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        cls.snap = snapshot.build(cls.root, providers.get_provider("demo"),
                                  start=1975, end=2024, delay=0)

    def test_covers_every_country_and_indicator(self):
        self.assertEqual(len(self.snap["countries"]), len(countries.COUNTRIES))
        self.assertEqual(len(self.snap["indicators"]), len(indicators.INDICATORS))
        for iso3 in countries.ISO3_CODES:
            self.assertIn(iso3, self.snap["series"])
            self.assertIn(iso3, self.snap["pulse"])

    def test_pulse_history_is_scored_for_every_country(self):
        for iso3 in countries.ISO3_CODES:
            entry = self.snap["pulse"][iso3]
            with self.subTest(iso3):
                self.assertIsNotNone(entry["latest"])
                self.assertGreater(len(entry["history"]), 20)
                self.assertGreaterEqual(entry["component_count"],
                                        pulse.MIN_PULSE_COMPONENTS)

    def test_series_are_year_sorted_pairs(self):
        series = self.snap["series"]["USA"]["NY.GDP.MKTP.KD.ZG"]
        years = [year for year, _ in series]
        self.assertEqual(years, sorted(years))

    def test_rankings_put_the_best_score_first(self):
        ranked = self.snap["rankings"]["NY.GDP.MKTP.KD.ZG"]
        scores = [r["score"] for r in ranked if r["score"] is not None]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_demo_snapshot_is_flagged_as_demo(self):
        self.assertTrue(self.snap["meta"]["is_demo"])

    def test_snapshot_is_json_serialisable(self):
        json.dumps(self.snap)

    def test_missing_context_file_is_not_an_error(self):
        self.assertEqual(snapshot.load_context(self.root), {})

    def test_context_file_is_read_when_present(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            with open(os.path.join(root, "data", "econ_context.json"), "w") as handle:
                json.dump({"as_of": "2026-08-23"}, handle)
            self.assertEqual(snapshot.load_context(root)["as_of"], "2026-08-23")

    def test_malformed_context_file_degrades_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            with open(os.path.join(root, "data", "econ_context.json"), "w") as handle:
                handle.write("{not json")
            self.assertIn("error", snapshot.load_context(root))


class ContextOnlyRefreshTests(unittest.TestCase):
    """`fetch_econ.py --context-only` must swap the curated layer and nothing else."""

    def setUp(self):
        import fetch_econ
        self.fetch_econ = fetch_econ
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "econ.json")
        with open(self.path, "w") as handle:
            json.dump({"meta": {"observations": 42}, "context": {"as_of": "1999-01-01"},
                       "series": {"USA": {}}}, handle)

    def test_replaces_only_the_context(self):
        rc = self.fetch_econ.refresh_context(self.path)
        self.assertEqual(rc, 0)
        with open(self.path) as handle:
            result = json.load(handle)
        # The curated layer moved on; the fetched data did not.
        self.assertNotEqual(result["context"].get("as_of"), "1999-01-01")
        self.assertEqual(result["meta"]["observations"], 42)
        self.assertIn("USA", result["series"])

    def test_missing_snapshot_is_an_error_not_a_crash(self):
        self.assertEqual(
            self.fetch_econ.refresh_context(os.path.join(self.dir, "nope.json")), 2)


class ShippedSnapshotTests(unittest.TestCase):
    """Guards on the committed data/econ.json, so a bad refresh is caught."""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "data", "econ.json")
        if not os.path.exists(path):
            raise unittest.SkipTest("no snapshot committed yet")
        with open(path) as handle:
            cls.snap = json.load(handle)

    def test_shipped_snapshot_is_real_data(self):
        self.assertFalse(self.snap["meta"]["is_demo"])

    def test_shipped_snapshot_is_substantial(self):
        self.assertGreater(self.snap["meta"]["observations"], 4000)

    def test_every_country_scores(self):
        for iso3 in countries.ISO3_CODES:
            self.assertIsNotNone(self.snap["pulse"][iso3]["latest"], iso3)

    def test_every_indicator_came_back(self):
        # A silent indicator failure loses a whole dimension - the governance
        # series went missing exactly this way once already.
        self.assertEqual(self.snap["meta"]["errors"], [],
                         f"indicators failed: {[e['indicator'] for e in self.snap['meta']['errors']]}")

    def test_curated_context_covers_every_country(self):
        countries_ctx = self.snap.get("context", {}).get("countries", {})
        for iso3 in countries.ISO3_CODES:
            self.assertIn(iso3, countries_ctx, iso3)
            self.assertIn("policy_rate", countries_ctx[iso3], iso3)

    def test_history_really_does_go_back_fifty_years(self):
        self.assertLessEqual(self.snap["meta"]["start_year"], 1976)
        oldest = min(
            year
            for country in self.snap["series"].values()
            for series in country.values()
            for year, _ in series
        )
        self.assertLessEqual(oldest, 1976)


class CareersDataTests(unittest.TestCase):
    """Guards on data/careers.json — the hand-curated careers layer."""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "data", "careers.json")
        if not os.path.exists(path):
            raise unittest.SkipTest("no careers data yet")
        with open(path) as handle:
            cls.data = json.load(handle)

    def test_markets_match_the_tracked_countries(self):
        # The careers page carries its own market list so it need not load the
        # 400KB economic snapshot; this is what stops the two drifting apart.
        self.assertEqual([m["iso3"] for m in self.data["markets"]], countries.ISO3_CODES)
        for entry in self.data["markets"]:
            source = countries.get(entry["iso3"])
            self.assertEqual(entry["short"], source["short"])
            self.assertEqual(entry["name"], source["name"])

    def test_every_country_has_a_complete_pathway(self):
        for iso3 in countries.ISO3_CODES:
            with self.subTest(iso3):
                entry = self.data["countries"][iso3]
                for field in ("regulators", "designation", "typical_time",
                              "gate", "headline", "steps", "cpd", "bodies"):
                    self.assertIn(field, entry)
                self.assertGreaterEqual(len(entry["steps"]), 4)
                self.assertGreaterEqual(len(entry["bodies"]), 2)

    def test_pathway_steps_are_numbered_in_order(self):
        for iso3 in countries.ISO3_CODES:
            steps = self.data["countries"][iso3]["steps"]
            self.assertEqual([s["n"] for s in steps], list(range(1, len(steps) + 1)), iso3)

    def test_every_country_has_companies_with_full_modal_content(self):
        for iso3 in countries.ISO3_CODES:
            companies = self.data["companies"][iso3]
            self.assertGreaterEqual(len(companies), 5, iso3)
            for company in companies:
                with self.subTest(company=company.get("name")):
                    # Every field here is rendered in the modal; a missing one
                    # shows as a blank section rather than failing loudly.
                    for field in ("name", "ticker", "segment", "hq", "scale",
                                  "what", "why_watch", "entry", "url"):
                        self.assertTrue(company.get(field), field)
                    self.assertTrue(company["url"].startswith("https://"))

    def test_every_linked_body_and_source_is_https(self):
        for iso3 in countries.ISO3_CODES:
            for body in self.data["countries"][iso3]["bodies"]:
                self.assertTrue(body["url"].startswith("https://"), body["url"])


class SiteBuildTests(unittest.TestCase):
    """The published site renames pages, so the tab links must be rewritten."""

    def setUp(self):
        import build_site
        self.build_site = build_site

    def test_nav_links_are_rewritten_to_site_filenames(self):
        html = ('<a href="econ.html" data-nav="economy">Economy</a>'
                '<a href="careers.html" data-nav="careers">Careers</a>'
                '<a href="index.html" data-nav="markets">Markets</a>')
        out = self.build_site.rewrite_nav(html)
        self.assertIn('href="index.html" data-nav="economy"', out)
        self.assertIn('href="careers.html" data-nav="careers"', out)
        self.assertIn('href="markets.html" data-nav="markets"', out)

    def test_links_without_data_nav_are_left_alone(self):
        html = '<a href="https://example.com/index.html">Source</a>'
        self.assertEqual(self.build_site.rewrite_nav(html), html)

    def test_aria_current_survives_the_rewrite(self):
        html = '<a href="econ.html" data-nav="economy" aria-current="page">Economy</a>'
        self.assertIn('aria-current="page"', self.build_site.rewrite_nav(html))

    def test_every_dashboard_has_a_site_filename(self):
        import export_html
        self.assertEqual(set(self.build_site.SITE_NAMES), set(export_html.DASHBOARDS))


if __name__ == "__main__":
    unittest.main()
