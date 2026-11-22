"""Forecast mandi onion prices and plan monthly sales from storage."""
from dataclasses import dataclass, replace
from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parent

# One timeline for every market. Data run from January 2008 to December 2025.
# A season runs from the April harvest to December; forecasts are made at the
# end of March and of every later month. Seasons 2011-2013 only train the
# models, 2014-2019 choose one and 2020-2025 test it. Every market must report
# every month from January 2013, so all markets are scored on the same seasons;
# earlier gaps only shorten the training history.
DATA_START, DATA_END = pd.Period("2008-01", "M"), pd.Period("2025-12", "M")
VALIDATION, TEST = range(2014, 2020), range(2020, 2026)
COMPLETE_FROM = pd.Period(f"{VALIDATION[0] - 1}-01", "M")  # last year's price is a baseline
HARVEST_MONTH, SEASON_MONTHS = 4, 9
ANOMALY_YEARS, MIN_ANOMALY_YEARS = 3, 2
MAX_GAP_MONTHS = 2
RIDGE_PENALTY = 10.0
MARKET_SIGNALS = ["price_anomaly", "arrivals_anomaly", "regional_arrivals_anomaly"]
WEATHER_SIGNALS = ["rain_anomaly", "tmax_anomaly"]
REGRESSIONS = {"Seasonal + market signals": MARKET_SIGNALS,
               "Seasonal + market signals + weather": MARKET_SIGNALS + WEATHER_SIGNALS}


@dataclass(frozen=True)
class Storage:
    monthly_loss: float
    cost_rs_t_month: float
    max_months: int


@dataclass(frozen=True)
class Farm:
    harvest_t: float = 1000
    harvest_day: int = 15
    curing_days: int = 15
    min_harvest_sale_t: float = 250     # cash needed at harvest
    max_monthly_sale_t: float = 300     # labour, transport and market limit
    capacity_t: float = 700
    fee_share: float = .01              # market fee and commission paid by the seller
    selling_cost_rs_t: float = 500      # transport, loading and weighing
    quality_loss: float = .01           # price discount per month in storage

    def first_storage_sale(self):
        """Months after harvest before cured onions can leave storage."""
        return max(1, (self.harvest_day + self.curing_days) // 30)


def monthly_loss(total, days):
    return 1 - (1 - total) ** (30 / days)


# ICAR-DOGR trial losses over 120 days; costs and durations are assumptions.
STORAGE = {"Ventilated": Storage(monthly_loss(.5489, 120), 250, 6),
           "Cold": Storage(monthly_loss(.0714, 120), 700, 8)}
SENSITIVITY = {
    "Base": (STORAGE["Cold"], Farm()),
    "Storage loss 5% a month": (replace(STORAGE["Cold"], monthly_loss=.05), Farm()),
    "Storage cost doubled": (replace(STORAGE["Cold"], cost_rs_t_month=1400), Farm()),
    "Quality loss 2% a month": (STORAGE["Cold"], Farm(quality_loss=.02)),
    "Selling costs doubled": (STORAGE["Cold"], Farm(fee_share=.02, selling_cost_rs_t=1000)),
    "Half the harvest sold for cash": (STORAGE["Cold"], Farm(min_harvest_sale_t=500)),
    "Curing takes 45 days": (STORAGE["Cold"], Farm(curing_days=45)),
}


def net_price(price_rs_t, farm, start=0):
    months_stored = np.arange(start, start + len(price_rs_t))
    return (np.asarray(price_rs_t) * (1 - farm.fee_share) * (1 - farm.quality_loss * months_stored)
            - farm.selling_cost_rs_t)


def plan_sales(price_rs_t, storage, farm, start=0, stock=None):
    """Tonnes sold and held in each month from `start` (0 is the harvest month).

    Variables are the monthly sales followed by the end-of-month stocks.
    """
    n = SEASON_MONTHS - start
    if len(price_rs_t) != n:
        raise ValueError(f"Expected {n} prices, received {len(price_rs_t)}")
    keep = 1 - storage.monthly_loss
    balance = np.hstack([np.eye(n), np.eye(n) - keep * np.eye(n, k=-1)])
    opening = farm.harvest_t if start == 0 else keep * stock
    months = range(start, SEASON_MONTHS)
    sale_bounds = [(farm.min_harvest_sale_t, None) if t == 0 else
                   (0, 0) if t < farm.first_storage_sale() else
                   (0, farm.max_monthly_sale_t) for t in months]
    last_stock = min(storage.max_months, SEASON_MONTHS - 1)
    stock_bounds = [(0, farm.capacity_t) if t < last_stock else (0, 0) for t in months]
    result = linprog(np.r_[-net_price(price_rs_t, farm, start), np.repeat(storage.cost_rs_t_month, n)],
                     A_eq=balance, b_eq=np.r_[opening, np.zeros(n - 1)],
                     bounds=sale_bounds + stock_bounds, method="highs")
    if not result.success:
        raise RuntimeError(f"Sales plan from month {start} is infeasible: {result.message}")
    return result.x[:n], result.x[n:]


def proceeds(price_rs_t, sold, held, storage, farm):
    return net_price(price_rs_t, farm) @ sold - storage.cost_rs_t_month * held.sum()


def rolling_plan(forecasts, storage, farm):
    """Re-plan at the end of every month and carry out only the next month's sales.

    `forecasts[k]` holds the prices forecast at the end of month k - 1 for months k onward.
    """
    sold, held, stock = [], [], None
    for start, prices in enumerate(forecasts):
        s, h = plan_sales(prices, storage, farm, start, stock)
        sold.append(s[0])
        held.append(h[0])
        stock = h[0]
    return np.array(sold), np.array(held)


def fill_short_gaps(series):
    """Interpolate, in logs, runs of up to MAX_GAP_MONTHS missing months between two reports.

    Longer runs and months before the first or after the last report stay missing.
    """
    missing = series.isna()
    run = (~missing).cumsum()
    length = missing.groupby(run).transform("sum")
    fill = missing & length.le(MAX_GAP_MONTHS) & run.gt(0) & run.lt(run.max())
    return series.where(~fill, np.exp(np.log(series).interpolate(limit_area="inside")))


def is_complete(series):
    """True when the series is positive in every month once short gaps are filled."""
    return bool(fill_short_gaps(series).gt(0).all())


def load(path):
    d = pd.read_csv(path)
    d["month"] = pd.PeriodIndex(d.month, freq="M")
    expected = pd.period_range(DATA_START, DATA_END, freq="M")
    filled = []
    for market, rows in d.groupby("market"):
        rows = rows.set_index("month").reindex(expected).rename_axis("month")
        if rows[["price_rs_q", "arrivals_t"]].le(0).any().any():
            raise ValueError(f"{market}: prices and arrivals must be positive")
        if rows[["rain_mm", "tmax_c", "tmin_c"]].isna().any().any():
            raise ValueError(f"{market}: weather is incomplete")
        rows["observed"] = rows.price_rs_q.notna()
        for column in ("price_rs_q", "arrivals_t"):
            if not is_complete(rows.loc[COMPLETE_FROM:, column]):
                raise ValueError(f"{market}: {column} misses more than {MAX_GAP_MONTHS} months "
                                 f"in a row, or the first or last month, after {COMPLETE_FROM}")
            rows[column] = fill_short_gaps(rows[column])
        filled.append(rows.reset_index())
    return pd.concat(filled, ignore_index=True)


def anomaly(values):
    """Value relative to the same calendar month in the previous three years.

    At least MIN_ANOMALY_YEARS of those years must be reported.
    """
    past = pd.concat([values.shift(12 * k) for k in range(1, ANOMALY_YEARS + 1)], axis=1)
    return values - past.mean(axis=1).where(past.count(axis=1).ge(MIN_ANOMALY_YEARS))


def signals(d):
    """Information available at the end of each month, by market."""
    out = []
    # Missing in any month in which a market did not report.
    regional = d.groupby("month").arrivals_t.sum(min_count=d.market.nunique()).rolling(3).sum()
    regional = anomaly(np.log(regional)).rename("regional_arrivals_anomaly")
    for market, m in d.groupby("market"):
        m = m.set_index("month")
        out.append(pd.DataFrame({
            "market": market,
            "price": m.price_rs_q,
            "price_anomaly": anomaly(np.log(m.price_rs_q)),
            "arrivals_anomaly": anomaly(np.log(m.arrivals_t.rolling(3).sum())),
            "rain_anomaly": anomaly(np.log1p(m.rain_mm.rolling(3).sum())),
            "tmax_anomaly": anomaly(m.tmax_c.rolling(3).mean()),
        }).join(regional))
    return pd.concat(out).rename_axis("month").reset_index()


def season_pairs(markets, years):
    """Every (origin, target) pair: origins March to November, targets to December."""
    rows = []
    for year in years:
        for k in range(SEASON_MONTHS):
            origin = pd.Period(f"{year}-{HARVEST_MONTH:02d}", "M") + k - 1
            for h in range(1, SEASON_MONTHS - k + 1):
                rows.append((year, k, origin, origin + h, h))
    pairs = pd.DataFrame(rows, columns=["season", "start", "origin", "target", "horizon"])
    return pairs.merge(pd.DataFrame({"market": markets}), how="cross")


def seasonal_ratio(prices, before):
    """Median ratio of each target month to each origin month in seasons before `before`."""
    history = prices[prices.month.dt.year < before]
    wide = history.assign(year=history.month.dt.year, cal=history.month.dt.month).pivot_table(
        index=["market", "year"], columns="cal", values="price_rs_q")
    ratios = {}
    for origin_cal in range(HARVEST_MONTH - 1, 12):
        for target_cal in range(origin_cal + 1, 13):
            ratio = (wide[target_cal] / wide[origin_cal]).groupby(level="market").median()
            for market, value in ratio.items():
                ratios[(market, origin_cal, target_cal)] = value
    return ratios


def design(rows, features):
    x = rows[features].to_numpy(float)
    return np.column_stack([x, x * rows.horizon.to_numpy()[:, None] / SEASON_MONTHS])


def forecast_season(year, prices, info):
    """All model forecasts for one season, using only data dated before each origin."""
    first = DATA_START.year + ANOMALY_YEARS
    pairs = season_pairs(sorted(prices.market.unique()), range(first, year + 1))
    price = prices.set_index(["market", "month"]).price_rs_q
    observed = prices.set_index(["market", "month"]).observed
    season = pairs[pairs.season.eq(year)].merge(info.rename(columns={"month": "origin"}),
                                                on=["market", "origin"], how="left")
    season["actual"] = price.reindex(pd.MultiIndex.from_frame(season[["market", "target"]])).to_numpy()
    season["observed"] = observed.reindex(pd.MultiIndex.from_frame(season[["market", "target"]])).to_numpy()
    season["same_month_last_year"] = price.reindex(pd.MultiIndex.from_arrays(
        [season.market, season.target - 12])).to_numpy()
    ratios = seasonal_ratio(prices, year)
    season["profile"] = [ratios[(m, o.month, t.month)] for m, o, t in
                         zip(season.market, season.origin, season.target)]

    # Training rows: earlier seasons, each with the profile known at the time.
    history = []
    for past in range(first, year):
        rows = pairs[pairs.season.eq(past)].merge(info.rename(columns={"month": "origin"}),
                                                  on=["market", "origin"], how="left")
        past_ratios = seasonal_ratio(prices, past)
        rows["profile"] = [past_ratios[(m, o.month, t.month)] for m, o, t in
                           zip(rows.market, rows.origin, rows.target)]
        rows["actual"] = price.reindex(pd.MultiIndex.from_frame(rows[["market", "target"]])).to_numpy()
        history.append(rows)
    # Seasons before COMPLETE_FROM may have gaps; those pairs cannot train.
    history = pd.concat(history, ignore_index=True)

    forecasts = {"Last price": season.price,
                 "Same month last year": season.same_month_last_year,
                 "Seasonal profile": season.price * season.profile}
    for name, features in REGRESSIONS.items():
        if season[features].isna().any().any():
            raise ValueError(f"{year}: missing inputs for {name}")
        train = history.dropna(subset=[*features, "price", "profile", "actual"])
        x, z = design(train, features), design(season, features)
        mean, scale = x.mean(axis=0), x.std(axis=0)
        x = np.column_stack([np.ones(len(x)), (x - mean) / scale])
        z = np.column_stack([np.ones(len(z)), (z - mean) / scale])
        y = np.log(train.actual / (train.price * train.profile)).to_numpy()
        penalty = np.diag(np.r_[0, np.full(x.shape[1] - 1, RIDGE_PENALTY)])
        beta = np.linalg.solve(x.T @ x + penalty, x.T @ y)
        forecasts[name] = season.price * season.profile * np.exp(z @ beta)
    for name, values in forecasts.items():
        if values.isna().any():
            raise ValueError(f"{year}: {name} has missing forecasts")
    keys = season[["market", "season", "start", "origin", "target", "horizon", "actual", "observed"]]
    return pd.concat([keys.assign(model=name, forecast=values.to_numpy())
                      for name, values in forecasts.items()], ignore_index=True)


def score(forecasts):
    """Errors on observed months only; interpolated months are not scored."""
    forecasts = forecasts[forecasts.observed.astype(bool)]
    f = forecasts.assign(split=np.where(forecasts.season.isin(VALIDATION), "validation", "test"),
                         abs_error=(forecasts.forecast - forecasts.actual).abs())
    f["abs_pct_error"] = 100 * f.abs_error / f.actual
    by_origin = []
    for origins, rows in (("March", f[f.start.eq(0)]), ("All", f)):
        s = rows.groupby(["split", "market", "model"], as_index=False).agg(
            mae_rs_q=("abs_error", "mean"), mape_pct=("abs_pct_error", "mean"))
        by_origin.append(s.assign(origins=origins))
    return pd.concat(by_origin, ignore_index=True)


def backtest(forecasts, prices, model, scenarios, years):
    """Realised proceeds per tonne harvested for each strategy, season and market."""
    price = prices.set_index(["market", "month"]).price_rs_q
    chosen = forecasts[forecasts.model.eq(model)]
    results, plans = [], []
    for (market, year), rows in chosen[chosen.season.isin(years)].groupby(["market", "season"]):
        months = pd.period_range(f"{year}-{HARVEST_MONTH:02d}", periods=SEASON_MONTHS, freq="M")
        actual = 10 * price.loc[market].reindex(months).to_numpy()
        march = 10 * rows[rows.start.eq(0)].sort_values("target").forecast.to_numpy()
        updates = [10 * r.sort_values("target").forecast.to_numpy() for _, r in rows.groupby("start")]
        for name, (storage, farm) in scenarios.items():
            strategies = {"March plan": plan_sales(march, storage, farm),
                          "Monthly re-plan": rolling_plan(updates, storage, farm),
                          "Perfect foresight": plan_sales(actual, storage, farm)}
            harvest = net_price(actual[:1], farm)[0]
            for strategy, (sold, held) in strategies.items():
                net = proceeds(actual, sold, held, storage, farm) / farm.harvest_t
                results.append((market, year, name, strategy, net, harvest, net - harvest))
                plans.extend((market, year, name, strategy, str(month), s, h)
                             for month, s, h in zip(months, sold, held))
    return (pd.DataFrame(results, columns=["market", "season", "scenario", "strategy",
                                           "net_rs_t", "harvest_sale_rs_t", "gain_rs_t"]),
            pd.DataFrame(plans, columns=["market", "season", "scenario", "strategy",
                                         "month", "sold_t", "end_stock_t"]))


def describe(prices, nhrdf_path):
    rows = []
    for market, m in prices.groupby("market"):
        # The same complete years for every market.
        m = m[m.month.ge(COMPLETE_FROM)]
        m = m.assign(year=m.month.dt.year, cal=m.month.dt.month)
        index = (m.price_rs_q / m.groupby("year").price_rs_q.transform("mean")).groupby(m.cal).mean()
        share = (m.arrivals_t / m.groupby("year").arrivals_t.transform("sum")).groupby(m.cal).mean()
        m["log_price"], m["log_arrivals"] = np.log(m.price_rs_q), np.log(m.arrivals_t)
        fit = smf.ols("log_price ~ log_arrivals + C(cal) + C(year)", m).fit(
            cov_type="HAC", cov_kwds={"maxlags": 3})
        rows.append({"state": m.state.iloc[0], "market": market,
                     "april_index": index[HARVEST_MONTH], "peak_month": index.idxmax(),
                     "peak_index": index.max(), "peak_arrivals_month": share.idxmax(),
                     "march_may_arrivals_share": share[[3, 4, 5]].sum(),
                     "arrivals_beta": fit.params.log_arrivals, "hac_p": fit.pvalues.log_arrivals})
    summary = pd.DataFrame(rows)
    # Cross-check the Lasalgaon series against the independent NHRDF archive.
    nhrdf = pd.read_csv(nhrdf_path)
    nhrdf = pd.Series(nhrdf["Modal Price (Rs/q)"].to_numpy(),
                      index=pd.to_datetime(nhrdf.Time, format="%d-%m-%Y").dt.to_period("M"))
    lasalgaon = prices[prices.market.str.contains("Lasalgaon")].set_index("month").price_rs_q
    common = lasalgaon.index.intersection(nhrdf.index)
    if len(common):
        gap = (lasalgaon[common] / nhrdf[common] - 1).abs()
        summary.loc[summary.market.str.contains("Lasalgaon"), ["nhrdf_months", "nhrdf_corr",
                                                               "nhrdf_median_gap"]] = [
            len(common), np.corrcoef(lasalgaon[common], nhrdf[common])[0, 1], gap.median()]
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "mandi_monthly.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    prices = load(args.data)
    info = signals(prices)
    forecasts = pd.concat([forecast_season(year, prices, info)
                           for year in [*VALIDATION, *TEST]], ignore_index=True)
    scores = score(forecasts)
    # Choose the model whose sales plans earned most in the validation seasons.
    scenarios = {name: (storage, Farm()) for name, storage in STORAGE.items()}
    runs = {model: backtest(forecasts, prices, model, scenarios, [*VALIDATION, *TEST])
            for model in forecasts.model.unique()}
    results = pd.concat([r.assign(model=model) for model, (r, _) in runs.items()], ignore_index=True)
    results["split"] = np.where(results.season.isin(VALIDATION), "validation", "test")
    planned = results[results.split.eq("validation") & results.strategy.ne("Perfect foresight")]
    selected = planned.groupby("model").gain_rs_t.mean().idxmax()
    plans = runs[selected][1]
    sensitivity, _ = backtest(forecasts, prices, selected, SENSITIVITY, TEST)
    outputs = {"forecasts": forecasts, "forecast_scores": scores, "storage_results": results,
               "sales_plan": plans, "sensitivity": sensitivity,
               "market_summary": describe(prices, ROOT / "data" / "lasalgaon_nhrdf.csv").assign(
                   selected_model=selected)}
    for name, data in outputs.items():
        data.to_csv(args.output / f"{name}.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
