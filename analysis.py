from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parent
METHODS = ("Last price", "Same month last year", "Trend and month effects")
STORES = {"Ventilated": (1 - (1 - .5489)**.25, 250),
          "Cold": (1 - (1 - .0714)**.25, 700)}
HARVEST, CAPACITY, APRIL_MIN, LATER_MAX = 1000, 700, 250, 300


def prepare_agmarknet(path):
    keys = ["state", "district", "market", "date"]
    columns = keys + ["variety", "grade", "modal_price_rs_qtl", "arrivals_tonnes"]
    d = pd.read_parquet(path, columns=columns, filters=[
        ("state", "in", ["Maharashtra", "Gujarat"])])
    d = d.rename(columns={"modal_price_rs_qtl": "price", "arrivals_tonnes": "arrivals"})
    d = d[d.price.between(50, 20_000) & d.arrivals.gt(0)]
    d = d.sort_values(keys + ["price", "arrivals"]).drop_duplicates(keys + ["variety", "grade"])
    median = d.groupby(["state", "date"]).price.transform("median")
    d = d[d.price.between(.2 * median, 5 * median)].assign(weighted=lambda x: x.price * x.arrivals)
    days = d.groupby(keys).agg(arrivals=("arrivals", "sum"), weights=("weighted", "sum"),
                              price_mean=("price", "mean"), distinct=("arrivals", "nunique"),
                              max_arrivals=("arrivals", "max")).reset_index()
    # Some market totals are repeated on every variety row.
    repeated = days.distinct.eq(1)
    days.loc[repeated, "arrivals"] = days.loc[repeated, "max_arrivals"]
    days.loc[repeated, "weights"] = days.loc[repeated, "price_mean"] * days.loc[repeated, "arrivals"]
    days["month"] = pd.to_datetime(days.date).dt.to_period("M")
    monthly = days.groupby(["state", "month"]).agg(
        arrivals_t=("arrivals", "sum"), weight=("weights", "sum"), market_days=("market", "size"))
    monthly["price_rs_q"] = monthly.pop("weight") / monthly.arrivals_t
    return monthly.reset_index().rename(columns={"state": "market"})


def prepare_nhrdf(path):
    d = pd.read_csv(path)
    return pd.DataFrame({"market": "Lasalgaon (NHRDF)",
                         "month": pd.to_datetime(d.Time, format="%d-%m-%Y").dt.to_period("M"),
                         "arrivals_t": d["Arrival (q)"] / 10,
                         "price_rs_q": d["Modal Price (Rs/q)"]}).sort_values("month")


def forecast(history, months, method):
    if method == METHODS[0]:
        return np.repeat(history.iloc[-1], len(months))
    if method == METHODS[1]:
        return history.loc[months - 12].to_numpy()

    def design(index):
        month_effects = np.asarray(index.month)[:, None] == np.arange(2, 13)
        trend = (index.year - history.index[0].year) + (index.month - 1) / 12
        return np.column_stack([np.ones(len(index)), trend, month_effects])

    coef = np.linalg.lstsq(design(history.index), np.log(history), rcond=None)[0]
    return np.exp(design(months) @ coef)


def forecast_rows(prices, years):
    for year in years:
        months = pd.period_range(f"{year}-04", periods=9, freq="M")
        past = prices.loc[:months[0] - 1]
        actual = prices.loc[months].to_numpy()
        for method in METHODS:
            predicted = forecast(past, months, method)
            yield from zip(months.astype(str), [method] * len(months), predicted, actual)


def sell_plan(price_rs_t, loss, holding_cost):
    # Variables are nine monthly sales followed by nine end-of-month stocks.
    n = len(price_rs_t)
    balance = np.hstack([np.eye(n), np.eye(n) - (1 - loss) * np.eye(n, k=-1)])
    bounds = [(APRIL_MIN, None)] + [(0, LATER_MAX)] * (n - 1)
    bounds += [(0, CAPACITY)] * (n - 1) + [(0, 0)]
    result = linprog(np.r_[-price_rs_t, np.repeat(holding_cost, n)],
                     A_eq=balance, b_eq=np.r_[HARVEST, np.zeros(n - 1)],
                     bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(result.message)
    return result.x[:n], result.x[n:]


def evaluate(monthly, out):
    forecasts, scores, plans, gains, summaries = [], [], [], [], []
    for market, d in monthly.groupby("market"):
        d = d.set_index("month").sort_index()
        prices = d.price_rs_q
        if (not prices.index.is_unique or
                not prices.index.equals(pd.period_range(prices.index[0], prices.index[-1], freq="M")) or
                not prices.gt(0).all()):
            raise ValueError(f"{market}: expected a complete, positive monthly series")
        archive = market == "Lasalgaon (NHRDF)"
        validation, test = (range(2013, 2017), range(2017, 2019)) if archive else (
            range(2019, 2023), range(2023, 2025))
        model_scores = []
        for split, years in (("validation", validation), ("test", test)):
            rows = pd.DataFrame(forecast_rows(prices, years),
                                columns=["month", "method", "forecast_rs_q", "actual_rs_q"])
            rows.insert(0, "market", market)
            rows["split"] = split
            rows["abs_error"] = (rows.forecast_rs_q - rows.actual_rs_q).abs()
            rows["abs_pct_error"] = 100 * rows.abs_error / rows.actual_rs_q
            m = rows.groupby("method").agg(mae_rs_q=("abs_error", "mean"),
                                             mape_pct=("abs_pct_error", "mean")).reset_index()
            m.insert(0, "market", market)
            m["split"] = split
            model_scores.append(m)
            forecasts.append(rows)
        scores.extend(model_scores)
        chosen = model_scores[0].sort_values("mape_pct").iloc[0].method

        complete = prices.groupby(prices.index.year).filter(lambda year: len(year) == 12)
        by_year = complete.groupby(complete.index.year).transform("mean")
        seasonal = (complete / by_year).groupby(complete.index.month).mean()
        summaries.append({"market": market, "months": len(prices), "min_rs_q": prices.min(),
                          "max_rs_q": prices.max(), "april_index": seasonal[4],
                          "lowest_month": seasonal.idxmin(), "peak_month": seasonal.idxmax(),
                          "peak_index": seasonal.max(), "selected_model": chosen})
        if not archive:
            d["year"], d["calendar_month"] = d.index.year, d.index.month
            d["log_price"] = np.log(d.price_rs_q)
            d["log_arrivals"] = np.log(d.arrivals_t / d.market_days)
            fit = smf.ols("log_price ~ log_arrivals + C(calendar_month) + C(year)", d).fit(
                cov_type="HAC", cov_kwds={"maxlags": 3})
            summaries[-1].update(arrivals_beta=fit.params.log_arrivals, hac_p=fit.pvalues.log_arrivals)

        selected = forecasts[-1].query("method == @chosen")
        for year in test:
            season = selected[selected.month.str.startswith(str(year))]
            predicted, actual = season.forecast_rs_q.to_numpy() * 10, season.actual_rs_q.to_numpy() * 10
            scenarios = {**STORES, "Cold, 5% loss": (.05, 700), "Cold, double cost": (STORES["Cold"][0], 1400)}
            for store, (loss, cost) in scenarios.items():
                sales, stock = sell_plan(predicted, loss, cost)
                realised = (actual @ sales - cost * stock.sum()) / HARVEST
                gains.append((market, year, store, realised, actual[0], realised - actual[0]))
                plans.extend((market, month, store, sold, remaining) for month, sold, remaining
                             in zip(season.month, sales, stock))

    pd.concat(forecasts).to_csv(out / "forecasts.csv", index=False, float_format="%.4f")
    pd.concat(scores).to_csv(out / "forecast_scores.csv", index=False, float_format="%.4f")
    pd.DataFrame(plans, columns=["market", "month", "store", "sold_t", "end_stock_t"]).to_csv(
        out / "sales_plan.csv", index=False, float_format="%.4f")
    pd.DataFrame(gains, columns=["market", "year", "store", "net_rs_t", "april_rs_t", "gain_rs_t"]).to_csv(
        out / "storage_results.csv", index=False, float_format="%.4f")
    pd.DataFrame(summaries).to_csv(out / "market_summary.csv", index=False, float_format="%.4f")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", type=Path, help="Rebuild the two Agmarknet state extracts.")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state_file = ROOT / "data" / "agmarknet_monthly.csv"
    if args.parquet:
        prepare_agmarknet(args.parquet).to_csv(state_file, index=False, float_format="%.6f")
    states = pd.read_csv(state_file)
    states["month"] = pd.PeriodIndex(states.month, freq="M")
    monthly = pd.concat([states, prepare_nhrdf(ROOT / "data" / "lasalgaon_nhrdf.csv")])
    evaluate(monthly, args.output)


if __name__ == "__main__":
    main()
