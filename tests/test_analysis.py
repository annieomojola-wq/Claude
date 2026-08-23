import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stockmon import analysis


def series(pairs):
    return [(dt.date.fromisoformat(d), c) for d, c in pairs]


class ShiftMonthsTest(unittest.TestCase):
    def test_clamps_to_end_of_shorter_month(self):
        self.assertEqual(analysis.shift_months(dt.date(2026, 3, 31), -1), dt.date(2026, 2, 28))
        self.assertEqual(analysis.shift_months(dt.date(2024, 3, 31), -1), dt.date(2024, 2, 29))

    def test_crosses_year_boundary(self):
        self.assertEqual(analysis.shift_months(dt.date(2026, 1, 15), -1), dt.date(2025, 12, 15))
        self.assertEqual(analysis.shift_months(dt.date(2026, 1, 15), -2), dt.date(2025, 11, 15))

    def test_forward_shift(self):
        self.assertEqual(analysis.shift_months(dt.date(2026, 11, 30), 1), dt.date(2026, 12, 30))


class LookupTest(unittest.TestCase):
    def setUp(self):
        self.s = series([("2026-06-01", 10.0), ("2026-06-15", 11.0), ("2026-07-01", 12.0)])

    def test_exact_match(self):
        self.assertEqual(analysis.close_on_or_before(self.s, dt.date(2026, 6, 15)), (dt.date(2026, 6, 15), 11.0))

    def test_falls_back_to_previous_trading_day(self):
        # 20 June is a weekend/holiday gap - use the 15th, not the 1 July close.
        self.assertEqual(analysis.close_on_or_before(self.s, dt.date(2026, 6, 20)), (dt.date(2026, 6, 15), 11.0))

    def test_before_series_start(self):
        self.assertIsNone(analysis.close_on_or_before(self.s, dt.date(2026, 5, 1)))

    def test_last_close_of_month(self):
        self.assertEqual(analysis.last_close_of_month(self.s, 2026, 6), (dt.date(2026, 6, 15), 11.0))
        self.assertIsNone(analysis.last_close_of_month(self.s, 2026, 5))


class RollingBasisTest(unittest.TestCase):
    def test_computes_month_on_month_drop(self):
        s = series([("2026-05-20", 80.0), ("2026-06-20", 100.0), ("2026-07-20", 90.0)])
        m = analysis.compute(s, basis="rolling")
        self.assertEqual(m.status, analysis.OK)
        self.assertEqual(m.as_of, "2026-07-20")
        self.assertEqual(m.ref_date, "2026-06-20")
        self.assertEqual(m.mom_pct, -10.0)          # 100 -> 90
        self.assertEqual(m.prev_mom_pct, 25.0)      # 80 -> 100
        self.assertFalse(analysis.is_sustained_decline(m))

    def test_sustained_decline_needs_two_down_months(self):
        s = series([("2026-05-20", 120.0), ("2026-06-20", 100.0), ("2026-07-20", 90.0)])
        m = analysis.compute(s, basis="rolling")
        self.assertLess(m.mom_pct, 0)
        self.assertLess(m.prev_mom_pct, 0)
        self.assertTrue(analysis.is_sustained_decline(m))

    def test_uses_last_close_on_or_before_the_month_mark(self):
        # No trading on 20 June; the 18th is the reference.
        s = series([("2026-06-18", 50.0), ("2026-06-25", 60.0), ("2026-07-20", 45.0)])
        m = analysis.compute(s, basis="rolling")
        self.assertEqual(m.ref_date, "2026-06-18")
        self.assertEqual(m.mom_pct, -10.0)

    def test_three_month_change_and_drawdown(self):
        s = series([
            ("2026-04-20", 100.0), ("2026-05-20", 150.0),
            ("2026-06-20", 120.0), ("2026-07-20", 75.0),
        ])
        m = analysis.compute(s, basis="rolling")
        self.assertEqual(m.chg_3m_pct, -25.0)       # 100 -> 75
        self.assertEqual(m.high_3m, 150.0)
        self.assertEqual(m.drawdown_pct, -50.0)     # 150 -> 75

    def test_insufficient_history(self):
        self.assertEqual(analysis.compute(series([("2026-07-20", 10.0)])).status, analysis.INSUFFICIENT)
        m = analysis.compute(series([("2026-07-10", 10.0), ("2026-07-20", 9.0)]))
        self.assertEqual(m.status, analysis.INSUFFICIENT)
        self.assertEqual(m.price, 9.0)

    def test_ignores_null_closes(self):
        s = [(dt.date(2026, 6, 20), 100.0), (dt.date(2026, 7, 1), None), (dt.date(2026, 7, 20), 90.0)]
        self.assertEqual(analysis.compute(s).mom_pct, -10.0)

    def test_unsorted_input_is_sorted(self):
        s = series([("2026-07-20", 90.0), ("2026-05-20", 80.0), ("2026-06-20", 100.0)])
        self.assertEqual(analysis.compute(s).as_of, "2026-07-20")


class YearOnYearTest(unittest.TestCase):
    def test_rolling_year_on_year(self):
        s = series([
            ("2025-07-20", 200.0),   # exactly a year before the anchor
            ("2026-06-20", 110.0),
            ("2026-07-20", 150.0),
        ])
        m = analysis.compute(s, basis="rolling")
        self.assertEqual(m.yoy_ref_date, "2025-07-20")
        self.assertEqual(m.yoy_ref_price, 200.0)
        self.assertEqual(m.yoy_pct, -25.0)       # 200 -> 150
        self.assertGreater(m.mom_pct, 0)         # up on the month, down on the year

    def test_year_on_year_falls_back_to_previous_trading_day(self):
        # Nothing trades on 20 July 2025; the 18th is the reference.
        s = series([("2025-07-18", 100.0), ("2026-06-20", 90.0), ("2026-07-20", 120.0)])
        m = analysis.compute(s, basis="rolling")
        self.assertEqual(m.yoy_ref_date, "2025-07-18")
        self.assertEqual(m.yoy_pct, 20.0)

    def test_growth_as_well_as_drop(self):
        s = series([("2025-07-20", 50.0), ("2026-06-20", 90.0), ("2026-07-20", 100.0)])
        self.assertEqual(analysis.compute(s).yoy_pct, 100.0)

    def test_absent_without_a_year_of_history(self):
        s = series([("2026-05-20", 100.0), ("2026-06-20", 110.0), ("2026-07-20", 90.0)])
        m = analysis.compute(s)
        self.assertEqual(m.status, analysis.OK)   # the month view still works
        self.assertIsNone(m.yoy_pct)
        self.assertIsNone(m.yoy_ref_date)
        self.assertIsNone(m.high_52w)
        self.assertIsNone(m.spark_year)
        self.assertIsNotNone(m.mom_pct)

    def test_calendar_basis_compares_the_same_month_a_year_earlier(self):
        s = series([
            ("2025-06-30", 400.0),   # June 2025, the year-ago month
            ("2025-07-31", 999.0),   # July 2025 - must NOT be picked
            ("2026-05-29", 100.0),
            ("2026-06-30", 200.0),   # last completed month
            ("2026-07-15", 60.0),    # current, incomplete
        ])
        m = analysis.compute(s, basis="calendar")
        self.assertEqual(m.as_of, "2026-06-30")
        self.assertEqual(m.yoy_ref_date, "2025-06-30")
        self.assertEqual(m.yoy_pct, -50.0)       # 400 -> 200

    def test_52_week_high_and_drawdown(self):
        s = series([
            ("2025-07-20", 100.0),
            ("2025-11-20", 250.0),   # the 52-week high
            ("2026-06-20", 140.0),
            ("2026-07-20", 125.0),
        ])
        m = analysis.compute(s)
        self.assertEqual(m.high_52w, 250.0)
        self.assertEqual(m.drawdown_52w_pct, -50.0)

    def test_52_week_high_ignores_older_peaks(self):
        s = series([
            ("2024-07-20", 900.0),   # more than a year back - out of the window
            ("2025-07-20", 100.0),
            ("2026-07-20", 150.0),
        ])
        self.assertEqual(analysis.compute(s).high_52w, 150.0)


class WeeklySamplingTest(unittest.TestCase):
    def test_thins_to_about_one_point_a_week(self):
        obs = series([(f"2026-0{1 + i // 28}-{1 + i % 28:02d}", float(i)) for i in range(50)])
        sampled = analysis._weekly(obs)
        self.assertLess(len(sampled), len(obs))
        self.assertEqual(sampled[0], 0.0)
        self.assertEqual(sampled[-1], 49.0)   # the latest close is always kept

    def test_empty_input(self):
        self.assertEqual(analysis._weekly([]), [])

    def test_short_input_keeps_endpoints(self):
        obs = series([("2026-07-01", 1.0), ("2026-07-02", 2.0)])
        self.assertEqual(analysis._weekly(obs), [1.0, 2.0])


class CalendarBasisTest(unittest.TestCase):
    def test_compares_completed_months(self):
        s = series([
            ("2026-04-30", 200.0),
            ("2026-05-29", 100.0),
            ("2026-06-30", 80.0),
            ("2026-07-15", 60.0),   # current, incomplete month - excluded
        ])
        m = analysis.compute(s, basis="calendar")
        self.assertEqual(m.as_of, "2026-06-30")     # last completed month
        self.assertEqual(m.ref_date, "2026-05-29")
        self.assertEqual(m.mom_pct, -20.0)          # 100 -> 80
        self.assertEqual(m.prev_mom_pct, -50.0)     # 200 -> 100
        self.assertTrue(analysis.is_sustained_decline(m))

    def test_missing_month_is_insufficient(self):
        s = series([("2026-06-30", 80.0), ("2026-07-15", 60.0)])
        self.assertEqual(analysis.compute(s, basis="calendar").status, analysis.INSUFFICIENT)

    def test_unknown_basis_rejected(self):
        with self.assertRaises(ValueError):
            analysis.compute(series([("2026-06-30", 1.0), ("2026-07-30", 2.0)]), basis="weekly")


class PctChangeTest(unittest.TestCase):
    def test_guards_divide_by_zero_and_none(self):
        self.assertIsNone(analysis.pct_change(10, 0))
        self.assertIsNone(analysis.pct_change(10, None))
        self.assertIsNone(analysis.pct_change(None, 10))
        self.assertAlmostEqual(analysis.pct_change(110, 100), 10.0)


if __name__ == "__main__":
    unittest.main()
