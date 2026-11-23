"""Onion price forecasts and sell-or-store plans for four Maharashtra mandis."""
import argparse
import warnings
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
from sklearn.linear_model import LassoCV, LinearRegression
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.sm_exceptions import ConvergenceWarning, EstimationWarning
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.stattools import adfuller

ROOT = Path(__file__).resolve().parent
MARKETS = ROOT / "markets.csv"

DATA_START, DATA_END = pd.Period("2011-01", "M"), pd.Period("2025-12", "M")
VALIDATION, TEST = range(2014, 2020), range(2020, 2026)   # 2011-13 history only
HARVEST_MONTH, SEASON_MONTHS = 4, 9                        # Apr-Dec
MAX_MISSING_SHARE, MAX_GAP_MONTHS = .05, 3
NEARBY_MIN_REPORTED = .8
ARIMA_ORDERS = list(product(range(3), range(2), range(3)))   # (p, d, q)
LOG_MODELS = ("Winters", "ARIMA")
PAST_SEASONS = "Past-seasons average"
STORE_SALE_MONTHS = [8, 9, 10]
QUINTALS_PER_TONNE = 10
DAYS_PER_MONTH = 30
MIN_GAIN_RS_T = 1
IMPROVED_BUILD_RS_T = 1670            # Rs 167/q


@dataclass(frozen=True)
class Storage:
    monthly_loss: float
    cost_rs_t_month: float
    max_months: int


@dataclass(frozen=True)
class Farm:
    harvest_t: int = 1000
    harvest_day: int = 15
    curing_days: int = 15
    min_harvest_sale_t: float = 250     # cash sale
    max_monthly_sale_t: float = 300     # handling limit
    capacity_t: float = 700
    fee_share: float = .01
    selling_cost_rs_t: float = 500      # transport, hamali, weighing
    quality_loss: float = .01           # per month stored
    interest_rate: float = .10

    def first_storage_sale(self):
        return max(1, (self.harvest_day + self.curing_days) // DAYS_PER_MONTH)

    def discount(self):
        return 1 / (1 + self.interest_rate / 12)


def monthly_loss(total, days):
    return 1 - (1 - total) ** (DAYS_PER_MONTH / days)


# loss: ICAR-DOGR 120-day trials (chawl, cold store at 27 C), Khapte et al. 2023 (improved store)
# cost: chawl rent Rs 140/q a season, improved store Rs 167/q to build (Khapte); cold rent assumed
STORAGE = {"Chawl": Storage(monthly_loss(.5489, 120), 1400 / 6, 6),
           "Improved": Storage(monthly_loss(.10, 180), IMPROVED_BUILD_RS_T / 6, 6),
           "Cold": Storage(monthly_loss(.0714, 120), 700, 8)}
BASE = STORAGE["Improved"]
SENSITIVITY = {
    "Base": (BASE, Farm()),
    "Storage cost doubled": (replace(BASE, cost_rs_t_month=2 * BASE.cost_rs_t_month), Farm()),
    "Storage loss 20% over six months": (replace(BASE, monthly_loss=monthly_loss(.20, 180)), Farm()),
    "Store holds onion seven months": (replace(BASE, max_months=7), Farm()),
    "Store holds onion eight months": (replace(BASE, max_months=8), Farm()),
    "Quality discount 2% a month": (BASE, Farm(quality_loss=.02)),
    "Selling costs doubled": (BASE, Farm(fee_share=.02, selling_cost_rs_t=1000)),
    "Interest 20% a year": (BASE, Farm(interest_rate=.20)),
    "Half the harvest sold for cash": (BASE, Farm(min_harvest_sale_t=500)),
    "Curing takes 45 days": (BASE, Farm(curing_days=45)),
}


def longest_gap(series):
    missing = series.isna().to_numpy()
    longest = run = 0
    for gap in missing:
        run = run + 1 if gap else 0
        longest = max(longest, run)
    return longest


def usable(series):
    return bool(series.dropna().gt(0).all() and series.isna().mean() <= MAX_MISSING_SHARE
                and longest_gap(series) <= MAX_GAP_MONTHS)


def load(path):
    d = pd.read_csv(path)
    d["month"] = pd.PeriodIndex(d.month, freq="M")
    expected = pd.period_range(DATA_START, DATA_END, freq="M")
    rows = []
    for market, m in d.groupby("market"):
        m = m.set_index("month").reindex(expected).rename_axis("month").reset_index()
        m[["state", "district", "market"]] = m[["state", "district", "market"]].ffill().bfill()
        if not (usable(m.price_rs_q) and usable(m.arrivals_t)):
            raise ValueError(f"{market}: more than {MAX_MISSING_SHARE:.0%} of months or more than "
                             f"{MAX_GAP_MONTHS} months in a row unreported")
        rows.append(m)
    return pd.concat(rows, ignore_index=True)


# gap filling

def load_nearby(path):
    d = pd.read_csv(path)
    d["month"] = pd.PeriodIndex(d.month, freq="M")
    wide = d.pivot(index="month", columns="market", values="price_rs_q")
    return np.log(wide.reindex(pd.period_range(DATA_START, DATA_END, freq="M")))


def gap_runs(missing):
    runs, current = [], []
    for month, gap in missing.items():
        if gap:
            current.append(month)
        elif current:
            runs.append(current)
            current = []
    return runs + [current] if current else runs


def lasso():
    return LassoCV(cv=5, max_iter=50_000)


def fill_prices(series, nearby, market, make_model=lasso):
    # lasso on nearby mandis' log prices; log interpolation where no nearby mandi reported
    if series.notna().all():
        return series
    target = np.log(series)
    others = nearby.drop(columns=market, errors="ignore").reindex(series.index)
    # interpolate nearby gaps so every reported month can be used for training
    complete = others.interpolate(limit_area="inside").ffill().bfill()
    estimate = target.copy()
    for run in gap_runs(target.isna()):
        columns = others.columns[others.loc[run].notna().all()]
        if len(columns):
            model = make_model().fit(complete.loc[target.notna(), columns], target.dropna())
            estimate[run] = model.predict(others.loc[run, columns])
    return series.fillna(np.exp(estimate.interpolate(limit_area="inside"))).ffill().bfill()


def gap_filling_check(prices, nearby, gaps_per_mandi=60, seed=42):
    # hide known runs of 1-3 months and compare fill methods
    rng = np.random.default_rng(seed)
    study = prices.market.unique()
    rows = []
    for market, m in prices.groupby("market"):
        series = m.set_index("month").price_rs_q
        for _ in range(gaps_per_mandi):
            length = int(rng.integers(1, MAX_GAP_MONTHS + 1))
            # 2 years before the gap for Winters, 1 year after for interpolation
            starts = [i for i in range(24, len(series) - 12 - length)
                      if series.iloc[i:i + length].notna().all()]
            start = int(rng.choice(starts))
            gap = slice(start, start + length)
            hidden = series.copy()
            hidden.iloc[gap] = np.nan
            truth = series.iloc[gap].to_numpy()
            others = nearby[[s for s in study if s != market]]
            estimates = {
                "Lasso on nearby mandis": fill_prices(hidden, nearby, market).iloc[gap].to_numpy(),
                "Regression on the other study mandis":
                    fill_prices(hidden, others, market, LinearRegression).iloc[gap].to_numpy(),
                "Log interpolation": fill_prices(hidden, nearby.iloc[:, :0], market).iloc[gap].to_numpy(),
                **smoothing_forecasts(fill_prices(hidden.iloc[:start], nearby, market), length)}
            for method, values in estimates.items():
                rows.append({"market": market, "method": method, "gap_months": length,
                             "abs_pct_error": np.abs(values / truth - 1).mean()})
    return pd.DataFrame(rows)


# sales plan

def net_price(price_rs_t, farm, start=0):
    months_stored = np.arange(start, start + len(price_rs_t))
    return (np.asarray(price_rs_t) * (1 - farm.fee_share) * (1 - farm.quality_loss * months_stored)
            - farm.selling_cost_rs_t)


def plan_sales(price_rs_t, storage, farm, start=0, stock=None):
    n = SEASON_MONTHS - start
    if len(price_rs_t) != n:
        raise ValueError(f"Expected {n} prices, received {len(price_rs_t)}")
    months = np.arange(start, SEASON_MONTHS)
    left = (1 - storage.monthly_loss) ** months
    weight = farm.discount() ** months * left
    sale_value = weight * net_price(price_rs_t, farm, start)
    hold_cost = weight * storage.cost_rs_t_month
    last_stock = min(storage.max_months, SEASON_MONTHS - 1)

    # backward induction; stock counted in harvest tonnes (1 t grid)
    grid = np.arange(farm.harvest_t + 1)
    before, after = grid[:, None], grid[None, :]
    sold = before - after
    value = np.where(grid == 0, 0.0, -np.inf)          # empty by December
    policy = [None] * n
    for k in reversed(range(n)):
        month = months[k]
        allowed = sold >= 0
        if month == 0:
            allowed &= sold >= farm.min_harvest_sale_t
        elif month < farm.first_storage_sale():
            allowed &= sold == 0
        else:
            allowed &= sold * left[k] <= farm.max_monthly_sale_t + 1e-9
        allowed &= after * left[k] <= farm.capacity_t + 1e-9
        if month >= last_stock:
            allowed &= after == 0
        total = np.where(allowed, sale_value[k] * sold - hold_cost[k] * after + value[None, :], -np.inf)
        policy[k] = total.argmax(axis=1)
        value = total.max(axis=1)

    if start == 0:
        state = farm.harvest_t
    else:
        state = int(round(stock / (1 - storage.monthly_loss) ** (start - 1)))
    if not np.isfinite(value[state]):
        raise RuntimeError(f"No feasible sales plan from month {start} with {stock} t in store")
    path = [state]
    for k in range(n):
        path.append(policy[k][path[-1]])
    path = np.array(path)
    return (path[:-1] - path[1:]) * left, path[1:] * left


def proceeds(price_rs_t, sold, held, storage, farm):
    weight = farm.discount() ** np.arange(len(sold))
    return weight @ (net_price(price_rs_t, farm) * sold - storage.cost_rs_t_month * held)


def rolling_plan(forecasts, storage, farm):
    # re-solve each month, keep only that month's sale
    sold, held, stock = [], [], None
    for start, prices in enumerate(forecasts):
        s, h = plan_sales(prices, storage, farm, start, stock)
        sold.append(s[0])
        held.append(h[0])
        stock = h[0]
    return np.array(sold), np.array(held)


# forecasts

def fitted(model):
    with warnings.catch_warnings():
        # convergence is checked below
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", EstimationWarning)
        result = model.fit()
    retvals = result.mle_retvals
    converged = bool(retvals["converged"] if "converged" in retvals else retvals["success"])
    return result, converged


def arima_forecast(history, horizon, order):
    # ARIMA on 12-month log changes
    log_price = np.log(history.to_numpy())
    change = log_price[12:] - log_price[:-12]
    result, converged = fitted(ARIMA(change, order=order))
    # horizon <= 9, so last year's price is known
    year_ago = log_price[len(log_price) - 12:len(log_price) - 12 + horizon]
    return np.exp(year_ago + result.forecast(horizon)), converged


def smoothing_forecasts(history, horizon):
    # Winters on log prices
    values = history.to_numpy()
    winters, converged = fitted(ExponentialSmoothing(
        np.log(values), trend="add", seasonal="add", seasonal_periods=12,
        initialization_method="estimated"))
    if not converged:
        raise RuntimeError(f"Winters model did not converge at {history.index[-1]}")
    return {"No change": np.repeat(values[-1], horizon),
            "Winters": np.exp(winters.forecast(horizon))}


def past_seasons_forecast(history, targets):
    return history.groupby(history.index.month).mean().reindex(targets.month).to_numpy()


def forecast_rows(prices, nearby, years, orders):
    # forecast origins: end of March to end of November
    rows, failures = [], []
    for market, m in prices.groupby("market"):
        series = m.set_index("month").price_rs_q
        for year, k in product(years, range(SEASON_MONTHS)):
            origin = pd.Period(f"{year}-{HARVEST_MONTH - 1:02d}", "M") + k
            history = fill_prices(series[:origin], nearby, market)   # no look-ahead
            horizon = SEASON_MONTHS - k
            targets = pd.period_range(origin + 1, periods=horizon, freq="M")
            models = {}
            if orders is None:
                models = {**smoothing_forecasts(history, horizon),
                          PAST_SEASONS: past_seasons_forecast(history, targets)}
            for order in orders or []:
                models[f"ARIMA{order}"], converged = arima_forecast(history, horizon, order)
                if not converged:
                    failures.append((market, str(origin), f"ARIMA{order}"))
            actual = series.reindex(targets).to_numpy()
            for name, values in models.items():
                rows.append(pd.DataFrame({"market": market, "season": year, "start": k,
                                          "origin": origin, "target": targets,
                                          "horizon": np.arange(1, horizon + 1), "model": name,
                                          "forecast": values, "actual": actual,
                                          "observed": ~np.isnan(actual)}))
    return pd.concat(rows, ignore_index=True), failures


def relative_mae(f):
    f = f[f.observed]
    by_market = f.assign(error=(f.forecast - f.actual).abs()).groupby("market")
    return (by_market.error.mean() / by_market.actual.mean()).mean()


def choose_arima(prices, nearby):
    grid, failures = forecast_rows(prices, nearby, VALIDATION, ARIMA_ORDERS)
    failed = {name for _, _, name in failures}
    table = pd.DataFrame([{"model": name, "validation_relative_mae": relative_mae(rows),
                           "converged_every_fit": name not in failed}
                          for name, rows in grid.groupby("model")])
    usable_orders = table[table.converged_every_fit]
    if usable_orders.empty:
        raise RuntimeError("No ARIMA order converged at every validation origin")
    best = usable_orders.loc[usable_orders.validation_relative_mae.idxmin(), "model"]
    order = next(o for o in ARIMA_ORDERS if f"ARIMA{o}" == best)
    return order, table.sort_values("validation_relative_mae")


def all_forecasts(prices, nearby, order):
    smooth, _ = forecast_rows(prices, nearby, [*VALIDATION, *TEST], None)
    arima, failures = forecast_rows(prices, nearby, [*VALIDATION, *TEST], [order])
    if failures:
        raise RuntimeError(f"ARIMA{order} did not converge at {failures}")
    arima["model"] = "ARIMA"
    return pd.concat([smooth, arima], ignore_index=True)


def score(forecasts):
    f = forecasts[forecasts.observed]
    f = f.assign(split=np.where(f.season.isin(VALIDATION), "validation", "test"),
                 abs_error=(f.forecast - f.actual).abs())
    out = []
    for origins, rows in (("March", f[f.start.eq(0)]), ("All", f)):
        s = rows.groupby(["split", "market", "model"], as_index=False).agg(
            mae_rs_q=("abs_error", "mean"), mean_price_rs_q=("actual", "mean"))
        out.append(s.assign(origins=origins, relative_mae=s.mae_rs_q / s.mean_price_rs_q))
    return pd.concat(out, ignore_index=True)


# backtest

def season_prices(series, year):
    months = pd.period_range(f"{year}-{HARVEST_MONTH:02d}", periods=SEASON_MONTHS, freq="M")
    return months, QUINTALS_PER_TONNE * series.reindex(months).to_numpy()   # Rs/t


def mean_factors(forecasts, model, seasons):
    # exp(s2/2) by horizon: median -> mean for log-price models
    f = forecasts[forecasts.model.eq(model) & forecasts.season.isin(seasons) & forecasts.observed]
    return np.exp((np.log(f.actual / f.forecast) ** 2).groupby(f.horizon).mean() / 2)


def season_inputs(prices, nearby, years):
    inputs = {}
    for market, m in prices.groupby("market"):
        reported = m.set_index("month").price_rs_q
        settled = fill_prices(reported, nearby, market)   # used only to value plans
        for year in years:
            months, actual = season_prices(settled, year)
            # mean price path of earlier seasons
            known = fill_prices(reported[:months[0] - 1], nearby, market)
            past = np.mean([season_prices(known, y)[1] for y in range(DATA_START.year, year)], axis=0)
            inputs[market, year] = months, actual, int(reported.reindex(months).isna().sum()), past
    return inputs


def plan_prices(forecasts, model, market, year):
    f = forecasts[forecasts.model.eq(model) & forecasts.market.eq(market) & forecasts.season.eq(year)]
    # leave the planned season out
    factors = (mean_factors(forecasts, model, [v for v in VALIDATION if v != year])
               if model in LOG_MODELS else None)
    updates = []
    for _, r in f.groupby("start"):
        r = r.sort_values("target")
        scale = 1 if factors is None else factors.reindex(r.horizon).to_numpy()
        updates.append(QUINTALS_PER_TONNE * r.forecast.to_numpy() * scale)
    return updates


def backtest(forecasts, inputs, models, scenarios):
    results, plans = [], []
    for (market, year), (months, actual, filled, past) in inputs.items():
        updates = {model: plan_prices(forecasts, model, market, year) for model in models}
        for name, (storage, farm) in scenarios.items():
            harvest = net_price(actual[:1], farm)[0]
            strategies = {("Past seasons", ""): plan_sales(past, storage, farm),
                          ("Perfect foresight", ""): plan_sales(actual, storage, farm)}
            for model in models:
                strategies[("March plan", model)] = plan_sales(updates[model][0], storage, farm)
                strategies[("Monthly re-plan", model)] = rolling_plan(updates[model], storage, farm)
            for (strategy, model), (sold, held) in strategies.items():
                net = proceeds(actual, sold, held, storage, farm) / farm.harvest_t
                charge = farm.discount() ** np.arange(len(held)) @ held * storage.cost_rs_t_month
                results.append((market, year, name, strategy, model, net, harvest, net - harvest,
                                charge / farm.harvest_t, filled))
                plans.extend((market, year, name, strategy, model, str(month), s, h)
                             for month, s, h in zip(months, sold, held))
    results = pd.DataFrame(results, columns=["market", "season", "storage", "strategy", "model",
                                             "net_rs_t", "harvest_sale_rs_t", "gain_rs_t",
                                             "storage_charge_rs_t", "filled_months"])
    results["split"] = np.where(results.season.isin(VALIDATION), "validation", "test")
    return results, pd.DataFrame(plans, columns=["market", "season", "storage", "strategy",
                                                 "model", "month", "sold_t", "end_stock_t"])


def march_plan_gain(forecasts, inputs, model, storage, farm=Farm()):
    gains = []
    for (market, year), (_, actual, _, _) in inputs.items():
        sold, held = plan_sales(plan_prices(forecasts, model, market, year)[0], storage, farm)
        gains.append(proceeds(actual, sold, held, storage, farm) / farm.harvest_t
                     - net_price(actual[:1], farm)[0])
    return np.mean(gains)


def bisect(pays, low, high, steps=16):
    if not pays(low) or pays(high):
        raise ValueError("No change of sign in the search interval")
    for _ in range(steps):
        middle = (low + high) / 2
        low, high = (middle, high) if pays(middle) else (low, middle)
    return (low + high) / 2


def break_even(forecasts, inputs, model):
    loss = bisect(lambda l: march_plan_gain(forecasts, inputs, model,
                                            replace(BASE, monthly_loss=l)) > MIN_GAIN_RS_T,
                  BASE.monthly_loss, STORAGE["Chawl"].monthly_loss)
    improved = march_plan_gain(forecasts, inputs, model, BASE)
    cold = STORAGE["Cold"]
    rent = bisect(lambda c: march_plan_gain(forecasts, inputs, model,
                                            replace(cold, cost_rs_t_month=c)) > improved,
                  0, cold.cost_rs_t_month)
    return pd.DataFrame([
        {"quantity": "Improved-store monthly loss at which the March plan stops gaining",
         "value": loss, "loss_over_four_months": 1 - (1 - loss) ** 4,
         "loss_over_six_months": 1 - (1 - loss) ** 6},
        {"quantity": "Cold-store rent (Rs/t a month) at which it gains as much as the improved store",
         "value": rent}])


def season_tests(results, scores_by_season):
    # seasons are the unit: the mandis' prices move together
    def improved(strategy, selected):
        rows = results[results.storage.eq("Improved") & results.strategy.eq(strategy)]
        return rows[rows.selected.eq(selected)].groupby("season").gain_rs_t.mean()

    march = improved("March plan", True)
    comparisons = {"Improved-store gain of the March plan": march,
                   "March plan minus past-seasons plan, improved store":
                       march - improved("Past seasons", False),
                   **scores_by_season}
    rows = []
    for name, by_season in comparisons.items():
        for split, seasons in (("test", TEST), ("all", [*VALIDATION, *TEST])):
            x = by_season[by_season.index.isin(seasons)]
            rows.append({"comparison": name, "seasons": split, "n": len(x), "mean": x.mean(),
                         "positive": int((x > 0).sum()), "t": stats.ttest_1samp(x, 0).statistic,
                         "t_p": stats.ttest_1samp(x, 0).pvalue,
                         "sign_p": stats.binomtest(int((x > 0).sum()), len(x)).pvalue})
    return pd.DataFrame(rows)


def forecast_differences(forecasts, model, benchmark):
    out = {}
    for origins, f in (("March", forecasts[forecasts.start.eq(0)]), ("All", forecasts)):
        error = {name: f[f.model.eq(name)].groupby("season").apply(relative_mae)
                 for name in (model, benchmark)}
        out[f"{model} minus {benchmark} relative MAE, {origins} origins"] = error[model] - error[benchmark]
    return out


# data description

def arrivals_regression(m):
    m = m.assign(cal=m.month.dt.month, t=np.arange(len(m)) / 12,
                 log_price=np.log(m.price_rs_q), log_arrivals=np.log(m.arrivals_t))
    fit = smf.ols("log_price ~ log_arrivals + C(cal) + t", m, missing="drop").fit()
    column = fit.model.exog_names.index("log_arrivals")
    residual = fit.resid.to_numpy()
    return {"arrivals_beta": fit.params.log_arrivals, "arrivals_se": fit.bse.log_arrivals,
            "arrivals_t": fit.tvalues.log_arrivals, "arrivals_p": fit.pvalues.log_arrivals,
            "r2": fit.rsquared, "adj_r2": fit.rsquared_adj, "f_stat": fit.fvalue, "f_p": fit.f_pvalue,
            "arrivals_vif": variance_inflation_factor(fit.model.exog, column),
            "residual_lag1_corr": np.corrcoef(residual[1:], residual[:-1])[0, 1], "n_months": int(fit.nobs)}


def seasonal_profile(m):
    year, cal = m.month.dt.year, m.month.dt.month
    index = (m.price_rs_q / m.groupby(year).price_rs_q.transform("mean")).groupby(cal).mean()
    share = (m.arrivals_t / m.groupby(year).arrivals_t.transform("sum")).groupby(cal).mean()
    return index, share


def describe(prices, nearby):
    rows = []
    for market, m in prices.groupby("market"):
        index, share = seasonal_profile(m)
        log_price = np.log(fill_prices(m.set_index("month").price_rs_q, nearby, market).to_numpy())
        regression = arrivals_regression(m)
        # Aug-Oct arrivals in the test years
        selling = m[m.month.dt.month.isin(STORE_SALE_MONTHS)
                    & m.month.dt.year.isin(TEST)].arrivals_t.mean()
        rows.append({"district": m.district.iloc[0], "market": market,
                     "unreported_months": int(m.price_rs_q.isna().sum()),
                     "april_index": index[HARVEST_MONTH], "peak_month": index.idxmax(),
                     "peak_index": index.max(),
                     "aug_oct_over_april": index.loc[STORE_SALE_MONTHS].mean() / index[HARVEST_MONTH],
                     "peak_arrivals_month": share.idxmax(), "lowest_arrivals_month": share.idxmin(),
                     **regression, "aug_oct_arrivals_t": selling,
                     "price_change_300t": np.expm1(regression["arrivals_beta"]
                                                   * np.log1p(Farm().max_monthly_sale_t / selling)),
                     "adf_p_log_price": adfuller(log_price, result_object=True).pvalue,
                     "adf_p_12_month_change": adfuller(log_price[12:] - log_price[:-12],
                                                       result_object=True).pvalue})
    summary = pd.DataFrame(rows)
    wide = prices.pivot(index="month", columns="market", values="price_rs_q")
    correlation = wide.corr().where(~np.eye(wide.shape[1], dtype=bool))
    summary["price_vs_mandi_mean"] = summary.market.map(wide.div(wide.mean(axis=1), axis=0).mean())
    summary["lowest_price_correlation"] = summary.market.map(correlation.min())
    return summary


def key_figures(prices, forecasts, scores, results, plans, sensitivity, gaps, summary, selected):
    # headline figures summarised from the other outputs
    rows = []

    def add(section, quantity, value):
        rows.append({"section": section, "quantity": quantity, "value": float(value)})

    cal = prices.month.dt.month
    add("Data", "Mandi-months", len(prices))
    add("Data", "Unreported mandi-months", prices.price_rs_q.isna().sum())
    for name, month in (("April", HARVEST_MONTH), ("November", 11)):
        add("Data", f"{name} mean price, Rs/q", prices[cal.eq(month)].price_rs_q.mean())
    mean = prices.pivot(index="month", columns="market", values="price_rs_q").mean(axis=1)

    def april(year):
        return mean[pd.Period(f"{year}-{HARVEST_MONTH:02d}", "M")]

    for year in range(DATA_START.year, DATA_END.year + 1):
        add("Data", f"November / April price, {year}", mean[pd.Period(f"{year}-11", "M")] / april(year))
    last = TEST[-1]
    for month in STORE_SALE_MONTHS:
        add("Data", f"Price rise from April to {pd.Period(f'{last}-{month:02d}', 'M').strftime('%B %Y')}",
            mean[pd.Period(f"{last}-{month:02d}", "M")] / april(last) - 1)
    for row in summary.itertuples():
        add("Data", f"Monthly sale as share of Aug-Oct arrivals, {row.market}",
            Farm().max_monthly_sale_t / row.aug_oct_arrivals_t)

    for method, error in gaps.groupby("method").abs_pct_error.mean().items():
        add("Gap filling", f"Mean error, {method}", error)

    for (origins, split, model), g in scores.groupby(["origins", "split", "model"]):
        add("Forecasts", f"Relative MAE, {model}, {split}, {origins} origins", g.relative_mae.mean())
        add("Forecasts", f"MAE Rs/q, {model}, {split}, {origins} origins", g.mae_rs_q.mean())
    for horizon, factor in mean_factors(forecasts, selected, VALIDATION).items():
        add("Forecasts", f"{selected} mean correction factor, {horizon} months ahead", factor)

    test = results[results.split.eq("test")]
    add("Storage", "April sale net, Rs/t, test", test.harvest_sale_rs_t.mean())
    kept = results[~results.model.eq("No change")]          # never stores, so always 0
    plan_model = kept.model.where(kept.model.isin(LOG_MODELS), "")
    for (split, storage, strategy, model), g in kept.groupby(["split", "storage", "strategy", plan_model]):
        add("Storage", f"Gain Rs/t, {storage}, {strategy}{f' ({model})' if model else ''}, {split}",
            g.gain_rs_t.mean())

    chosen = test[test.selected & test.strategy.eq("March plan")]
    improved, cold = chosen[chosen.storage.eq("Improved")], chosen[chosen.storage.eq("Cold")]
    gain = improved.gain_rs_t.mean()
    add("Storage", "Improved March plan gain as share of April sale", gain / test.harvest_sale_rs_t.mean())
    add("Storage", "Improved March plan, test market-seasons with a gain", (improved.gain_rs_t > 0).sum())
    add("Storage", "Improved March plan, test market-seasons", len(improved))
    add("Storage", f"Improved March plan gain Rs/t, {last}", improved[improved.season.eq(last)].gain_rs_t.mean())
    add("Storage", "Improved March plan gain Rs/t, without filled months",
        improved[improved.filled_months.eq(0)].gain_rs_t.mean())
    held = plans[plans.season.isin(TEST) & plans.strategy.eq("March plan") & plans.model.eq(selected)]
    april_rows = held[held.month.str.endswith(f"-{HARVEST_MONTH:02d}")]
    for storage, g in april_rows.groupby("storage"):
        add("Storage", f"{storage} March plan, test market-seasons that store", (g.end_stock_t > 0).sum())
    sold = held[held.storage.eq("Improved")].groupby(held.month.str[-2:]).sold_t.mean()
    for month, tonnes in sold.items():
        add("Storage", f"Improved March plan, mean tonnes sold in month {int(month)}", tonnes)
    for market, g in improved.groupby("market"):
        add("Storage", f"Improved minus cold store, Rs/t, {market}",
            g.gain_rs_t.mean() - cold[cold.market.eq(market)].gain_rs_t.mean())
    district = test[test.storage.eq("Improved")
                    & (test.selected | test.strategy.isin(["Past seasons", "Perfect foresight"]))]
    for (market, strategy), g in district.groupby(["market", "strategy"]):
        add("Storage", f"Improved gain Rs/t, {market}, {strategy}", g.gain_rs_t.mean())

    farm = Farm()
    build = IMPROVED_BUILD_RS_T * farm.capacity_t
    add("Investment", "Improved store build cost, Rs lakh", build / 1e5)
    add("Investment", "Improved storage charge in the plans, Rs/t harvested", improved.storage_charge_rs_t.mean())
    add("Investment", "Improved gain on the harvest with the whole build cost in one season, Rs lakh",
        (gain + improved.storage_charge_rs_t.mean() - build / farm.harvest_t) * farm.harvest_t / 1e5)

    march = sensitivity[sensitivity.strategy.eq("March plan")]
    for scenario, g in march.groupby("scenario", sort=False):
        add("Sensitivity", f"Improved March plan gain Rs/t, {scenario}", g.gain_rs_t.mean())
    return pd.DataFrame(rows)


def seasonal_figure(prices, path):
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 9})
    fig, (left, right) = plt.subplots(1, 2, figsize=(6.8, 1.6), layout="constrained")
    months = np.arange(1, 13)
    for district, m in prices.groupby("district"):
        index, share = seasonal_profile(m)
        left.plot(months, index.to_numpy(), marker="o", markersize=2.5, linewidth=1, label=district)
        right.plot(months, 100 * share.to_numpy(), marker="o", markersize=2.5, linewidth=1, label=district)
    for ax, title in ((left, "Price relative to the year's mean"), (right, "Share of the year's arrivals (%)")):
        ax.set_xticks(months, list("JFMAMJJASOND"))
        ax.set_title(title, fontsize=9)
        ax.axvspan(3.5, 4.5, color="0.9", zorder=0)
        ax.spines[["top", "right"]].set_visible(False)
    left.axhline(1, color="0.6", linewidth=.6)
    fig.legend(*left.get_legend_handles_labels(), loc="outside lower center", ncol=4, frameon=False)
    fig.savefig(path, dpi=300, metadata={"Software": None})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "mandi_monthly.csv")
    parser.add_argument("--nearby", type=Path, default=ROOT / "data" / "nearby_prices.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    print("1/7 Loading data")
    prices = load(args.data)
    nearby = load_nearby(args.nearby)

    print("2/7 Choosing the ARIMA order on the validation seasons")
    order, orders = choose_arima(prices, nearby)
    print(f"3/7 Forecasting {VALIDATION[0]}-{TEST[-1]} from every forecast date (the slow step)")
    forecasts = all_forecasts(prices, nearby, order)
    scores = score(forecasts)

    # plans use the model with the lowest validation error
    validation = forecasts[forecasts.season.isin(VALIDATION)]
    selected = min(forecasts.model.unique(),
                   key=lambda model: relative_mae(validation[validation.model.eq(model)]))
    # past-seasons average is planned as its own strategy
    models = [model for model in forecasts.model.unique() if model != PAST_SEASONS]
    if selected not in models:
        raise RuntimeError(f"{selected} has the lowest validation error; plan it as 'Past seasons'")
    print(f"4/7 Planning sales for each store, strategy and season ({selected} forecasts selected)")
    inputs = season_inputs(prices, nearby, [*VALIDATION, *TEST])
    test_inputs = {key: value for key, value in inputs.items() if key[1] in TEST}
    scenarios = {name: (storage, Farm()) for name, storage in STORAGE.items()}
    results, plans = backtest(forecasts, inputs, models, scenarios)
    results = results.assign(selected=results.model.eq(selected))

    print("5/7 Sensitivity runs, break-even search and tests")
    sensitivity, _ = backtest(forecasts, test_inputs, [selected], SENSITIVITY)
    sensitivity = sensitivity.rename(columns={"storage": "scenario"})
    even = break_even(forecasts, test_inputs, selected)
    differences = {**forecast_differences(forecasts, selected, "No change"),
                   **forecast_differences(forecasts, selected, PAST_SEASONS)}
    tests = season_tests(results, differences)

    print("6/7 Checking gap filling and describing the data")
    gaps = gap_filling_check(prices, nearby)
    summary = describe(prices, nearby)

    outputs = {"forecasts": forecasts, "forecast_scores": scores,
               "arima_orders": orders.assign(selected=orders.model.eq(f"ARIMA{order}")),
               "gap_filling_check": gaps,
               "storage_results": results, "sales_plan": plans, "sensitivity": sensitivity,
               "break_even": even, "season_tests": tests, "market_summary": summary,
               "key_figures": key_figures(prices, forecasts, scores, results, plans, sensitivity,
                                          gaps, summary, selected)}
    print(f"7/7 Writing {len(outputs) + 1} files to {args.output}")
    for name, data in outputs.items():
        data.to_csv(args.output / f"{name}.csv", index=False, float_format="%.4f")
    seasonal_figure(prices, args.output / "seasonal_pattern.png")
    print("Done")


if __name__ == "__main__":
    main()
