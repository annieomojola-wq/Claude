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
