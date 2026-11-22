import unittest

import numpy as np
import pandas as pd

from regional.run import BASELINE, INPUT, MARCH_FEATURES, make_panel, predict_season, storage


class RegionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        monthly = pd.read_csv(INPUT)
        monthly["month"] = pd.PeriodIndex(monthly.month, freq="M")
        cls.panel = make_panel(monthly)

    def test_later_prices_and_features_do_not_enter_forecast(self):
        original, _ = predict_season(self.panel, 2023)
        changed = self.panel.copy()
        changed.loc[changed.year.ge(2023), "actual"] *= 2
        changed.loc[changed.year.gt(2023), MARCH_FEATURES] *= 2
        forecast, _ = predict_season(changed, 2023)
        np.testing.assert_array_equal(original.forecast, forecast.forecast)

    def test_missing_march_feature_fails(self):
        changed = self.panel.copy()
        changed.loc[changed.year.eq(2023), "rain"] = np.nan
        with self.assertRaisesRegex(ValueError, "observed March"):
            predict_season(changed, 2023)

    def test_incomplete_season_has_plan_but_no_realised_gain(self):
        forecast, _ = predict_season(self.panel, 2023)
        forecast = forecast.loc[forecast.state.eq("Bihar")].assign(split="test", region="East")
        plan, gains = storage(forecast, BASELINE)
        self.assertEqual(len(plan), 36)
        self.assertTrue(gains.gain_rs_t.isna().all())
        self.assertTrue(gains.observed_months.eq(8).all())
