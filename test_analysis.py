import unittest

import numpy as np
import pandas as pd

from analysis import APRIL_MIN, CAPACITY, HARVEST, LATER_MAX, METHODS, forecast, sell_plan


class AnalysisTest(unittest.TestCase):
    def test_flat_prices_sell_at_harvest(self):
        sold, stock = sell_plan(np.repeat(12_000, 9), .02, 700)
        np.testing.assert_allclose(sold, [HARVEST] + [0] * 8)
        np.testing.assert_allclose(stock, 0)

    def test_sold_and_stored_obey_constraints(self):
        loss = .02
        sold, stock = sell_plan(np.array([8000] * 7 + [40_000, 25_000]), loss, 700)
        np.testing.assert_allclose(sold + stock, np.r_[HARVEST, stock[:-1] * (1 - loss)])
        self.assertGreaterEqual(sold[0], APRIL_MIN)
        self.assertGreater(stock[0], 0)
        self.assertTrue((sold[1:] <= LATER_MAX + 1e-8).all())
        self.assertTrue((stock <= CAPACITY + 1e-8).all())
        self.assertAlmostEqual(stock[-1], 0)

    def test_seasonal_baseline_uses_previous_year(self):
        dates = pd.period_range("2022-01", "2023-03", freq="M")
        history = pd.Series(np.arange(len(dates)) + 100, index=dates)
        future = pd.period_range("2023-04", periods=9, freq="M")
        np.testing.assert_array_equal(forecast(history, future, METHODS[1]), np.arange(103, 112))


if __name__ == "__main__":
    unittest.main()
