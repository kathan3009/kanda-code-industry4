import unittest
from dataclasses import replace

import numpy as np
import pandas as pd

from analysis import (DATA_END, DATA_START, SEASON_MONTHS, STORAGE, Farm, forecast_season,
                      plan_sales, rolling_plan, signals)

COLD = STORAGE["Cold"]


def synthetic_panel(seed=0):
    rng = np.random.default_rng(seed)
    months = pd.period_range(DATA_START, DATA_END, freq="M")
    rows = []
    for market in ("A", "B"):
        season = 1 + .4 * np.sin(2 * np.pi * (months.month.to_numpy() - 4) / 12)
        rows.append(pd.DataFrame({
            "state": market, "market": market, "month": months,
            "price_rs_q": 1000 * season * np.exp(rng.normal(0, .1, len(months))),
            "arrivals_t": 5000 / season * np.exp(rng.normal(0, .1, len(months))),
            "rain_mm": rng.gamma(2, 30, len(months)),
            "tmax_c": 32 + rng.normal(0, 1, len(months)),
            "tmin_c": 18 + rng.normal(0, 1, len(months)), "observed": True}))
    return pd.concat(rows, ignore_index=True)


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
        self.assertGreaterEqual(sold[0], farm.min_harvest_sale_t - 1e-8)
        self.assertGreater(held[0], 0)
        self.assertTrue((sold[1:] <= farm.max_monthly_sale_t + 1e-8).all())
        self.assertTrue((held <= farm.capacity_t + 1e-8).all())
        self.assertAlmostEqual(held[-1], 0)

    def test_storage_duration_and_curing(self):
        prices = np.array([5000] + [6000] * 7 + [60_000])
        sold, held = plan_sales(prices, replace(COLD, max_months=5), Farm(curing_days=45))
        self.assertAlmostEqual(sold[1], 0)
        np.testing.assert_allclose(held[5:], 0)

    def test_monthly_replan_with_exact_forecasts_matches_full_plan(self):
        prices = np.array([7000, 7500, 8200, 9000, 9900, 11_000, 13_000, 12_000, 10_000])
        updates = [prices[k:] for k in range(SEASON_MONTHS)]
        np.testing.assert_allclose(rolling_plan(updates, COLD, Farm()),
                                   plan_sales(prices, COLD, Farm()), atol=1e-6)


class ForecastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = synthetic_panel()

    def forecast(self, panel):
        return forecast_season(2016, panel, signals(panel))

    def test_later_data_does_not_change_march_forecasts(self):
        original = self.forecast(self.panel)
        changed = self.panel.copy()
        later = changed.month.gt(pd.Period("2016-03", "M"))
        changed.loc[later, ["price_rs_q", "arrivals_t", "rain_mm"]] *= 3
        updated = self.forecast(changed)
        march = original.start.eq(0)
        np.testing.assert_allclose(original[march].forecast, updated[march].forecast)

    def test_same_month_last_year(self):
        f = self.forecast(self.panel)
        f = f[f.model.eq("Same month last year") & f.market.eq("A")]
        price = self.panel[self.panel.market.eq("A")].set_index("month").price_rs_q
        np.testing.assert_allclose(f.forecast, price.loc[f.target - 12].to_numpy())


if __name__ == "__main__":
    unittest.main()
