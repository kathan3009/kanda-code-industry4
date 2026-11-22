import unittest
from dataclasses import replace
from itertools import combinations_with_replacement
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from analysis import (DATA_END, DATA_START, SEASON_MONTHS, STORAGE, Farm, arrivals_regression,
                      fill_prices, forecast_rows, load, plan_sales, proceeds, rolling_plan)

COLD = STORAGE["Cold"]
MONTHS = pd.period_range(DATA_START, DATA_END, freq="M")


def synthetic_market(seed=0, beta=-.3):
    """Seasonal prices that respond to arrivals with elasticity `beta`."""
    rng = np.random.default_rng(seed)
    season = np.sin(2 * np.pi * (MONTHS.month.to_numpy() - 4) / 12)
    log_arrivals = 9 - .5 * season + rng.normal(0, .2, len(MONTHS))
    log_price = 7 + .3 * season + beta * (log_arrivals - 9) + rng.normal(0, .05, len(MONTHS))
    return pd.DataFrame({"state": "S", "district": "D", "market": "A", "month": MONTHS,
                         "price_rs_q": np.exp(log_price), "arrivals_t": np.exp(log_arrivals)})


def synthetic_nearby(prices, seed=1):
    """Log prices at two nearby mandis that follow mandi A closely."""
    rng = np.random.default_rng(seed)
    log_a = np.log(prices.set_index("month").price_rs_q.interpolate())
    return pd.DataFrame({"B": log_a + .10 + rng.normal(0, .03, len(log_a)),
                         "C": log_a - .05 + rng.normal(0, .03, len(log_a))})


NO_NEARBY = pd.DataFrame(index=MONTHS)


def write_and_load(prices):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "prices.csv"
        prices.to_csv(path, index=False)
        return load(path)


class SalesPlanTest(unittest.TestCase):
    def test_flat_prices_sell_at_harvest(self):
        sold, held = plan_sales(np.repeat(12_000, SEASON_MONTHS), COLD, Farm())
        np.testing.assert_allclose(sold, [Farm().harvest_t] + [0] * 8)
        np.testing.assert_allclose(held, 0)

    def test_plan_obeys_constraints(self):
        farm = Farm()
        prices = np.array([8000] * 6 + [40_000, 25_000, 9000])
        sold, held = plan_sales(prices, COLD, farm)
        keep = 1 - COLD.monthly_loss
        np.testing.assert_allclose(sold + held, np.r_[farm.harvest_t, held[:-1] * keep])
        self.assertGreaterEqual(sold[0], farm.min_harvest_sale_t)
        self.assertGreater(held[0], 0)
        self.assertTrue((sold[1:] <= farm.max_monthly_sale_t + 1e-6).all())
        self.assertTrue((held <= farm.capacity_t + 1e-6).all())
        self.assertAlmostEqual(held[-1], 0)

    def test_storage_duration_and_curing(self):
        prices = np.array([5000] + [6000] * 7 + [60_000])
        sold, held = plan_sales(prices, replace(COLD, max_months=5), Farm(curing_days=45))
        self.assertAlmostEqual(sold[1], 0)
        np.testing.assert_allclose(held[5:], 0)

    def test_matches_enumeration_of_every_plan(self):
        farm = Farm(harvest_t=6, min_harvest_sale_t=1, max_monthly_sale_t=3, capacity_t=4)
        prices = np.random.default_rng(1).uniform(5000, 15_000, SEASON_MONTHS)
        keep = 1 - COLD.monthly_loss
        left = keep ** np.arange(SEASON_MONTHS)
        best = -np.inf
        # Stock in harvest tonnes can only fall; enumerate every falling path ending at zero.
        for path in combinations_with_replacement(range(farm.harvest_t + 1), SEASON_MONTHS - 1):
            stock = np.r_[sorted(path, reverse=True), 0]
            sold_h = np.r_[farm.harvest_t, stock[:-1]] - stock
            sold, held = sold_h * left, stock * left
            if (sold[0] >= farm.min_harvest_sale_t and (sold[1:] <= farm.max_monthly_sale_t).all()
                    and (held <= farm.capacity_t).all()):
                best = max(best, proceeds(prices, sold, held, COLD, farm))
        sold, held = plan_sales(prices, COLD, farm)
        self.assertAlmostEqual(proceeds(prices, sold, held, COLD, farm), best, places=6)

    def test_monthly_replan_with_exact_forecasts_matches_full_plan(self):
        prices = np.array([7000, 7500, 8200, 9000, 9900, 11_000, 13_000, 12_000, 10_000])
        updates = [prices[k:] for k in range(SEASON_MONTHS)]
        np.testing.assert_allclose(rolling_plan(updates, COLD, Farm()),
                                   plan_sales(prices, COLD, Farm()), atol=1e-6)


class ForecastTest(unittest.TestCase):
    def march(self, prices, nearby):
        f, failures = forecast_rows(prices, nearby, [2018], None)
        g, _ = forecast_rows(prices, nearby, [2018], [(1, 0, 1)])
        f = pd.concat([f, g])
        return f[f.start.eq(0)].sort_values(["model", "target"]).forecast.to_numpy()

    def test_later_prices_do_not_change_march_forecasts(self):
        # Unreported months before the origin are filled from data up to the origin only.
        prices = synthetic_market()
        nearby = synthetic_nearby(prices)
        prices.loc[prices.month.isin(pd.PeriodIndex(["2017-06", "2018-02"], freq="M")), "price_rs_q"] = np.nan
        changed, changed_nearby = prices.copy(), nearby.copy()
        changed.loc[changed.month.gt(pd.Period("2018-03", "M")), "price_rs_q"] *= 3
        changed_nearby.loc[changed_nearby.index > pd.Period("2018-03", "M")] += np.log(3)
        np.testing.assert_allclose(self.march(prices, nearby), self.march(changed, changed_nearby))

    def test_arima_returns_prices_from_twelve_month_changes(self):
        # Prices that repeat last year's shape about 5% higher: the 12-month change is nearly constant.
        shape = 1000 * (1.5 + np.sin(2 * np.pi * MONTHS.month.to_numpy() / 12))
        noise = np.exp(np.random.default_rng(2).normal(0, .02, len(MONTHS)))
        prices = pd.DataFrame({"market": "A", "month": MONTHS, "arrivals_t": 1.0,
                               "price_rs_q": shape * 1.05 ** (np.arange(len(MONTHS)) // 12) * noise})
        f, _ = forecast_rows(prices, NO_NEARBY, [2018], [(0, 0, 0)])
        np.testing.assert_allclose(f.forecast, f.actual, rtol=.1)


class DataTest(unittest.TestCase):
    def test_regression_recovers_arrivals_elasticity(self):
        fit = arrivals_regression(synthetic_market(beta=-.3))
        self.assertAlmostEqual(fit["arrivals_beta"], -.3, delta=.05)
        self.assertLess(fit["arrivals_p"], .01)

    def test_short_gap_is_kept_and_long_gap_rejected(self):
        prices = synthetic_market()
        short = prices[~prices.month.isin(pd.period_range("2020-04", "2020-06", freq="M"))]
        loaded = write_and_load(short)
        self.assertEqual(len(loaded), len(MONTHS))
        self.assertEqual(loaded.price_rs_q.isna().sum(), 3)
        long = prices[~prices.month.isin(pd.period_range("2020-04", "2020-07", freq="M"))]
        with self.assertRaises(ValueError):
            write_and_load(long)

    def test_lasso_fills_a_gap_from_nearby_mandis(self):
        prices = synthetic_market()
        series = prices.set_index("month").price_rs_q
        gap = pd.period_range("2019-09", "2019-11", freq="M")
        filled = fill_prices(series.where(~series.index.isin(gap)), synthetic_nearby(prices), "A")
        np.testing.assert_allclose(filled[gap], series[gap], rtol=.06)
        pd.testing.assert_series_equal(filled.drop(gap), series.drop(gap))

    def test_without_nearby_reports_gaps_are_interpolated_in_logs(self):
        months = pd.period_range("2020-01", periods=6, freq="M")
        series = pd.Series([100, np.nan, np.nan, 800, 900, np.nan], index=months)
        filled = fill_prices(series, NO_NEARBY, "A")
        np.testing.assert_allclose(filled.iloc[1:3], [200, 400])     # equal steps in log price
        self.assertEqual(filled.iloc[-1], 900)                       # no later report to use
        pd.testing.assert_series_equal(filled.dropna().loc[series.notna()], series.dropna())

if __name__ == "__main__":
    unittest.main()
