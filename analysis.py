"""Forecast onion prices in Maharashtra's four main onion districts and plan monthly sales from storage."""
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
VALIDATION, TEST = range(2014, 2020), range(2020, 2026)  # 2011-2013 are history only
HARVEST_MONTH, SEASON_MONTHS = 4, 9                       # April to December
MAX_MISSING_SHARE, MAX_GAP_MONTHS = .05, 3               # a record this complete is usable
NEARBY_MIN_REPORTED = .8                                  # nearby mandis used to fill gaps
ARIMA_ORDERS = list(product(range(3), range(2), range(3)))  # (p, d, q) on 12-month log changes


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
    min_harvest_sale_t: float = 250     # cash needed at harvest
    max_monthly_sale_t: float = 300     # labour, transport and market limit
    capacity_t: float = 700
    fee_share: float = .01              # market fee and commission paid by the seller
    selling_cost_rs_t: float = 500      # transport, loading and weighing
    quality_loss: float = .01           # price discount per month in storage
    interest_rate: float = .10          # yearly cost of the money tied up in stock

    def first_storage_sale(self):
        """Months after harvest before cured onions can leave storage."""
        return max(1, (self.harvest_day + self.curing_days) // 30)

    def discount(self):
        return 1 / (1 + self.interest_rate / 12)


def monthly_loss(total, days):
    return 1 - (1 - total) ** (30 / days)


# Traditional store: ICAR 120-day trial loss, rent Rs 140/q a season in Nashik (Khapte et al., 2023).
# Improved store: 10% loss over six months; Rs 167/q build cost spread over one season (same source).
# Cold store: ICAR 120-day trial loss; the rent is an assumption.
STORAGE = {"Traditional": Storage(monthly_loss(.5489, 120), 1400 / 6, 6),
           "Improved": Storage(monthly_loss(.10, 180), 1670 / 6, 6),
           "Cold": Storage(monthly_loss(.0714, 120), 700, 8)}
BASE = STORAGE["Improved"]
SENSITIVITY = {
    "Base": (BASE, Farm()),
    "Storage cost doubled": (replace(BASE, cost_rs_t_month=2 * BASE.cost_rs_t_month), Farm()),
    "Storage loss 20% over six months": (replace(BASE, monthly_loss=monthly_loss(.20, 180)), Farm()),
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
    """Positive values, at most MAX_MISSING_SHARE of months missing and no gap over MAX_GAP_MONTHS."""
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


# Missing months -----------------------------------------------------------------------------

def load_nearby(path):
    """Log price of every nearby mandi: one column per mandi, one row per month."""
    d = pd.read_csv(path)
    d["month"] = pd.PeriodIndex(d.month, freq="M")
    wide = d.pivot(index="month", columns="market", values="price_rs_q")
    return np.log(wide.reindex(pd.period_range(DATA_START, DATA_END, freq="M")))


def gap_runs(missing):
    """Runs of consecutive missing months, as lists of months."""
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
    """Unreported months from a regression on nearby mandis' log prices in the same month.

    The model is fitted on the months of `series` that were reported and sees nearby prices only up
    to the last month of `series`, so no later data are used. Gaps no nearby mandi reported, and
    gaps at the end of the record, fall back to interpolation of log price and the last report.
    """
    if series.notna().all():
        return series
    target = np.log(series)
    others = nearby.drop(columns=market, errors="ignore").reindex(series.index)
    # Nearby mandis' own gaps are interpolated so that every reported month can train the model.
    complete = others.interpolate(limit_area="inside").ffill().bfill()
    estimate = target.copy()
    for run in gap_runs(target.isna()):
        columns = others.columns[others.loc[run].notna().all()]
        if len(columns):
            model = make_model().fit(complete.loc[target.notna(), columns], target.dropna())
            estimate[run] = model.predict(others.loc[run, columns])
    return series.fillna(np.exp(estimate.interpolate(limit_area="inside"))).ffill().bfill()


def gap_filling_check(prices, nearby, gaps_per_mandi=60, seed=42):
    """Hide reported runs of one to three months and compare ways of filling them."""
    rng = np.random.default_rng(seed)
    study = prices.market.unique()
    rows = []
    for market, m in prices.groupby("market"):
        series = m.set_index("month").price_rs_q
        for _ in range(gaps_per_mandi):
            length = int(rng.integers(1, MAX_GAP_MONTHS + 1))
            # Two years before the gap give Winters a full seasonal history; a year after allows interpolation.
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


# Sales plan ---------------------------------------------------------------------------------

def net_price(price_rs_t, farm, start=0):
    months_stored = np.arange(start, start + len(price_rs_t))
    return (np.asarray(price_rs_t) * (1 - farm.fee_share) * (1 - farm.quality_loss * months_stored)
            - farm.selling_cost_rs_t)


def plan_sales(price_rs_t, storage, farm, start=0, stock=None):
    """Tonnes sold and held each month from `start` (0 is harvest), by backward induction on V_t(s)."""
    n = SEASON_MONTHS - start
    if len(price_rs_t) != n:
        raise ValueError(f"Expected {n} prices, received {len(price_rs_t)}")
    months = np.arange(start, SEASON_MONTHS)
    left = (1 - storage.monthly_loss) ** months         # tonnes left per harvest tonne
    weight = farm.discount() ** months * left           # present value per harvest tonne
    sale_value = weight * net_price(price_rs_t, farm, start)
    hold_cost = weight * storage.cost_rs_t_month
    last_stock = min(storage.max_months, SEASON_MONTHS - 1)

    # Stock is counted in harvest tonnes, so storage loss scales sales but keeps the grid exact.
    grid = np.arange(farm.harvest_t + 1)
    before, after = grid[:, None], grid[None, :]       # stock before and after this month's sales
    sold = before - after
    value = np.where(grid == 0, 0.0, -np.inf)          # nothing may remain after December
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
    """Present value at harvest of sales after selling costs, minus storage cost."""
    weight = farm.discount() ** np.arange(len(sold))
    return weight @ (net_price(price_rs_t, farm) * sold - storage.cost_rs_t_month * held)


def rolling_plan(forecasts, storage, farm):
    """Re-plan each month and carry out only that month's sales; forecasts[k] starts at month k."""
    sold, held, stock = [], [], None
    for start, prices in enumerate(forecasts):
        s, h = plan_sales(prices, storage, farm, start, stock)
        sold.append(s[0])
        held.append(h[0])
        stock = h[0]
    return np.array(sold), np.array(held)


# Forecasts ----------------------------------------------------------------------------------

def fitted(model):
    """Fit and report whether the likelihood optimiser converged."""
    with warnings.catch_warnings():
        # Convergence is checked from the result below; zero starting values are acceptable.
        warnings.simplefilter("ignore", ConvergenceWarning)
        warnings.simplefilter("ignore", EstimationWarning)
        result = model.fit()
    retvals = result.mle_retvals
    converged = bool(retvals["converged"] if "converged" in retvals else retvals["success"])
    return result, converged


def arima_forecast(history, horizon, order):
    """ARIMA on the 12-month change in log price, turned back into prices."""
    log_price = np.log(history.to_numpy())
    change = log_price[12:] - log_price[:-12]
    result, converged = fitted(ARIMA(change, order=order))
    # Every target is at most nine months ahead, so the price a year earlier is known.
    year_ago = log_price[len(log_price) - 12:len(log_price) - 12 + horizon]
    return np.exp(year_ago + result.forecast(horizon)), converged


def smoothing_forecasts(history, horizon):
    """No-change and Winters forecasts; Winters runs on log prices so seasonal effects are percentages."""
    values = history.to_numpy()
    winters, converged = fitted(ExponentialSmoothing(
        np.log(values), trend="add", seasonal="add", seasonal_periods=12,
        initialization_method="estimated"))
    if not converged:
        raise RuntimeError(f"Winters model did not converge at {history.index[-1]}")
    return {"No change": np.repeat(values[-1], horizon),
            "Winters": np.exp(winters.forecast(horizon))}


def forecast_rows(prices, nearby, years, orders):
    """Forecasts from the end of March and each later month to November, using data to that month."""
    rows, failures = [], []
    for market, m in prices.groupby("market"):
        series = m.set_index("month").price_rs_q
        for year, k in product(years, range(SEASON_MONTHS)):
            origin = pd.Period(f"{year}-{HARVEST_MONTH - 1:02d}", "M") + k
            history = fill_prices(series[:origin], nearby, market)   # data up to the origin only
            horizon = SEASON_MONTHS - k
            targets = pd.period_range(origin + 1, periods=horizon, freq="M")
            models = smoothing_forecasts(history, horizon) if orders is None else {}
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
    """Mean absolute error over reported months as a share of the mean price, averaged over mandis."""
    f = f[f.observed]
    by_market = f.assign(error=(f.forecast - f.actual).abs()).groupby("market")
    return (by_market.error.mean() / by_market.actual.mean()).mean()


def choose_arima(prices, nearby):
    """The (p, d, q) with the lowest validation error among orders that always converged."""
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
    """Errors on reported months only."""
    f = forecasts[forecasts.observed]
    f = f.assign(split=np.where(f.season.isin(VALIDATION), "validation", "test"),
                 abs_error=(f.forecast - f.actual).abs())
    out = []
    for origins, rows in (("March", f[f.start.eq(0)]), ("All", f)):
        s = rows.groupby(["split", "market", "model"], as_index=False).agg(
            mae_rs_q=("abs_error", "mean"), mean_price_rs_q=("actual", "mean"))
        out.append(s.assign(origins=origins, relative_mae=s.mae_rs_q / s.mean_price_rs_q))
    return pd.concat(out, ignore_index=True)


# Backtest -----------------------------------------------------------------------------------

def season_prices(series, year):
    months = pd.period_range(f"{year}-{HARVEST_MONTH:02d}", periods=SEASON_MONTHS, freq="M")
    return months, 10 * series.reindex(months).to_numpy()   # Rs per tonne


def backtest(forecasts, prices, nearby, models, scenarios, years):
    """Proceeds per tonne harvested from each strategy, against selling everything at harvest."""
    results, plans = [], []
    for market, m in prices.groupby("market"):
        reported = m.set_index("month").price_rs_q
        settled = fill_prices(reported, nearby, market)   # after the season, all data may be used
        for year in years:
            months, actual = season_prices(settled, year)
            filled = int(reported.reindex(months).isna().sum())
            # Past-seasons plan: the schedule that would have earned most over earlier seasons.
            known = fill_prices(reported[:months[0] - 1], nearby, market)
            past = np.mean([season_prices(known, y)[1] for y in range(DATA_START.year, year)], axis=0)
            for name, (storage, farm) in scenarios.items():
                harvest = net_price(actual[:1], farm)[0]
                strategies = {("Past seasons", ""): plan_sales(past, storage, farm),
                              ("Perfect foresight", ""): plan_sales(actual, storage, farm)}
                for model in models:
                    f = forecasts[forecasts.model.eq(model) & forecasts.market.eq(market)
                                  & forecasts.season.eq(year)]
                    updates = [10 * r.sort_values("target").forecast.to_numpy()
                               for _, r in f.groupby("start")]
                    strategies[("March plan", model)] = plan_sales(updates[0], storage, farm)
                    strategies[("Monthly re-plan", model)] = rolling_plan(updates, storage, farm)
                for (strategy, model), (sold, held) in strategies.items():
                    net = proceeds(actual, sold, held, storage, farm) / farm.harvest_t
                    results.append((market, year, name, strategy, model, net, harvest, net - harvest,
                                    filled))
                    plans.extend((market, year, name, strategy, model, str(month), s, h)
                                 for month, s, h in zip(months, sold, held))
    results = pd.DataFrame(results, columns=["market", "season", "storage", "strategy", "model",
                                             "net_rs_t", "harvest_sale_rs_t", "gain_rs_t",
                                             "filled_months"])
    results["split"] = np.where(results.season.isin(VALIDATION), "validation", "test")
    return results, pd.DataFrame(plans, columns=["market", "season", "storage", "strategy",
                                                 "model", "month", "sold_t", "end_stock_t"])


# Description --------------------------------------------------------------------------------

def arrivals_regression(m):
    """Log price on log arrivals with month-of-year dummies and a linear trend, on reported months."""
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
    """Average price relative to the year's mean, and share of the year's arrivals, by month."""
    year, cal = m.month.dt.year, m.month.dt.month
    index = (m.price_rs_q / m.groupby(year).price_rs_q.transform("mean")).groupby(cal).mean()
    share = (m.arrivals_t / m.groupby(year).arrivals_t.transform("sum")).groupby(cal).mean()
    return index, share


def describe(prices, nearby):
    rows = []
    for market, m in prices.groupby("market"):
        index, share = seasonal_profile(m)
        log_price = np.log(fill_prices(m.set_index("month").price_rs_q, nearby, market).to_numpy())
        rows.append({"district": m.district.iloc[0], "market": market,
                     "unreported_months": int(m.price_rs_q.isna().sum()),
                     "april_index": index[HARVEST_MONTH], "peak_month": index.idxmax(),
                     "peak_index": index.max(), "peak_arrivals_month": share.idxmax(),
                     "lowest_arrivals_month": share.idxmin(), **arrivals_regression(m),
                     "adf_p_log_price": adfuller(log_price, result_object=True).pvalue,
                     "adf_p_12_month_change": adfuller(log_price[12:] - log_price[:-12],
                                                       result_object=True).pvalue})
    summary = pd.DataFrame(rows)
    # How the four district mandis compare, month by month.
    wide = prices.pivot(index="month", columns="market", values="price_rs_q")
    correlation = wide.corr().where(~np.eye(wide.shape[1], dtype=bool))
    summary["price_vs_mandi_mean"] = summary.market.map(wide.div(wide.mean(axis=1), axis=0).mean())
    summary["lowest_price_correlation"] = summary.market.map(correlation.min())
    return summary


def seasonal_figure(prices, path):
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 9})
    fig, (left, right) = plt.subplots(1, 2, figsize=(6.8, 1.75), layout="constrained")
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
    prices = load(args.data)
    nearby = load_nearby(args.nearby)

    order, orders = choose_arima(prices, nearby)
    forecasts = all_forecasts(prices, nearby, order)
    scores = score(forecasts)
    models = list(forecasts.model.unique())
    scenarios = {name: (storage, Farm()) for name, storage in STORAGE.items()}
    results, plans = backtest(forecasts, prices, nearby, models, scenarios, [*VALIDATION, *TEST])

    # The plan uses the forecast with the lowest error in the validation seasons.
    validation = forecasts[forecasts.season.isin(VALIDATION)]
    selected = min(models, key=lambda model: relative_mae(validation[validation.model.eq(model)]))
    sensitivity, _ = backtest(forecasts, prices, nearby, [selected], SENSITIVITY, TEST)

    outputs = {"forecasts": forecasts, "forecast_scores": scores,
               "arima_orders": orders.assign(selected=orders.model.eq(f"ARIMA{order}")),
               "gap_filling_check": gap_filling_check(prices, nearby),
               "storage_results": results.assign(selected=results.model.eq(selected)),
               "sales_plan": plans, "sensitivity": sensitivity,
               "market_summary": describe(prices, nearby)}
    for name, data in outputs.items():
        data.to_csv(args.output / f"{name}.csv", index=False, float_format="%.4f")
    seasonal_figure(prices, args.output / "seasonal_pattern.png")


if __name__ == "__main__":
    main()
