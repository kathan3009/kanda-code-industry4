import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import STORAGE, Farm, Storage, plan_sales, proceeds

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "data" / "monthly.csv"
SEASONS = {2022: "validation", 2023: "test", 2024: "test"}
MONTHS = tuple(range(4, 13))
# The earlier eight-state comparison: no selling costs, quality loss or duration limit.
FARM = Farm(fee_share=0, selling_cost_rs_t=0, quality_loss=0)
SCENARIOS = {"Ventilated": replace(STORAGE["Ventilated"], max_months=len(MONTHS)),
             "Cold": replace(STORAGE["Cold"], max_months=len(MONTHS)),
             "Cold, 5% loss": Storage(.05, 700, len(MONTHS)),
             "Cold, double cost": replace(STORAGE["Cold"], cost_rs_t_month=1400, max_months=len(MONTHS))}
WEATHER = ["rain", "tmax", "tmin"]
MARCH_FEATURES = ["march_price", "march_arrivals", *WEATHER]
BASELINE = "Pooled seasonality"
REGRESSIONS = {
    "Calendar ridge": ["march_price"],
    "Calendar + arrivals": ["march_price", "march_arrivals"],
    "Calendar + arrivals + weather": MARCH_FEATURES,
}


def prepare_agmarknet(path, states):
    keys = ["state", "district", "market", "date"]
    columns = keys + ["variety", "grade", "modal_price_rs_qtl", "arrivals_tonnes"]
    d = pd.read_parquet(path, columns=columns, filters=[("state", "in", list(states))])
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
    return monthly.reset_index()


def prepare(path, states):
    monthly = prepare_agmarknet(path, states)
    keys = ["state", "district", "market", "date"]
    weather = pd.read_parquet(path, columns=keys + WEATHER, filters=[
        ("state", "in", list(states))])
    # Average reported market-days, not state-wide land area.
    days = weather.dropna(subset=WEATHER).groupby(keys, as_index=False)[WEATHER].mean()
    days["month"] = days.date.dt.to_period("M")
    climate = days.groupby(["state", "month"])[WEATHER].mean()
    return monthly.merge(climate, on=["state", "month"], how="left", validate="one_to_one")


def make_panel(monthly):
    if monthly.duplicated(["state", "month"]).any():
        raise ValueError("Duplicate state-month observations")
    values = monthly[["price_rs_q", "arrivals_t", "market_days"]]
    if not np.isfinite(values).all().all() or not values.gt(0).all().all():
        raise ValueError("Observed price, arrivals and market days must be finite and positive")
    d = monthly.assign(year=monthly.month.dt.year, target=monthly.month.dt.month)
    march = d.loc[d.target.eq(3), ["state", "year", "price_rs_q", "arrivals_t", "market_days", *WEATHER]]
    march = march.assign(march_arrivals=march.arrivals_t / march.market_days).rename(
        columns={"price_rs_q": "march_price"})
    index = pd.MultiIndex.from_product(
        [sorted(d.state.unique()), range(d.year.min(), d.year.max() + 1), MONTHS],
        names=["state", "year", "target"])
    targets = d.set_index(["state", "year", "target"]).price_rs_q.reindex(index).rename("actual")
    return targets.reset_index().merge(
        march[["state", "year", *MARCH_FEATURES]], on=["state", "year"], how="left", validate="many_to_one")


def ridge(train, future, features):
    categories = [f"{state}:{month}" for state in sorted(future.state.unique()) for month in MONTHS]

    def design(rows):
        state_month = rows.state + ":" + rows.target.astype(str)
        # Shared month effects plus state-specific deviations.
        months = pd.get_dummies(pd.Categorical(rows.target, categories=MONTHS)).to_numpy(float)
        states = pd.get_dummies(pd.Categorical(state_month, categories=categories)).to_numpy(float)
        numeric = rows[features].to_numpy(float).copy()
        for i, feature in enumerate(features):
            if feature in {"march_price", "march_arrivals"}:
                numeric[:, i] = np.log(numeric[:, i])
            elif feature == "rain":
                numeric[:, i] = np.log1p(numeric[:, i])
        return np.column_stack([months, states]), numeric

    xcat, x = design(train)
    zcat, z = design(future)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    if np.any(scale == 0):
        raise ValueError("A regression input is constant in training")
    x = np.column_stack([np.ones(len(x)), xcat, (x - mean) / scale])
    z = np.column_stack([np.ones(len(z)), zcat, (z - mean) / scale])
    y = np.log(train.actual / train.march_price)
    penalty = np.diag(np.r_[0, np.full(x.shape[1] - 1, 10.)])
    return future.march_price.to_numpy() * np.exp(z @ np.linalg.solve(x.T @ x + penalty, x.T @ y))


def predict_season(panel, year):
    future = panel.loc[panel.year.eq(year)].copy()
    if future.empty or not np.isfinite(future[MARCH_FEATURES]).all().all():
        raise ValueError(f"{year}: every state needs observed March price, arrivals and weather")
    history = panel.loc[panel.year.lt(year)].dropna(subset=["actual", "march_price"]).copy()
    history["ratio"] = history.actual / history.march_price
    yearly = history.groupby(["year", "target"], as_index=False).ratio.median()
    seasonal = yearly.groupby("target").ratio.median()
    weights = np.exp2((yearly.year - year) / 2)
    weighted = (yearly.ratio * weights).groupby(yearly.target).sum() / weights.groupby(yearly.target).sum()
    train = history.dropna(subset=MARCH_FEATURES)
    if set(train.target) != set(MONTHS):
        raise ValueError(f"{year}: training does not cover all target months")
    forecasts = {
        "March price": future.march_price,
        BASELINE: future.march_price * future.target.map(seasonal),
        "Recent seasonality": future.march_price * future.target.map(weighted),
        **{name: ridge(train, future, features) for name, features in REGRESSIONS.items()},
    }
    result = future[["state", "year", "target", "actual"]].assign(**forecasts)
    predictions = result.melt(id_vars=["state", "year", "target", "actual"],
                              var_name="model", value_name="forecast")
    if not np.isfinite(predictions.forecast).all() or not predictions.forecast.gt(0).all():
        raise ValueError(f"{year}: invalid forecast")
    return predictions, train.groupby("state").size().rename("training_rows").reset_index().assign(year=year)


def storage(predictions, selected):
    plans, results = [], []
    groups = predictions.loc[
        predictions.split.eq("test") & predictions.model.isin([selected, BASELINE])]
    for (region, state, year, model), rows in groups.groupby(["region", "state", "year", "model"]):
        rows = rows.sort_values("target")
        observed = int(rows.actual.notna().sum())
        for name, store in SCENARIOS.items():
            sales, stock = plan_sales(rows.forecast.to_numpy() * 10, store, FARM)
            plans.extend((region, state, year, model, name, month, sold, held)
                         for month, sold, held in zip(rows.target, sales, stock))
            # Publish the plan, but don't report realized proceeds without a full season.
            actual = rows.actual.to_numpy() * 10
            gain = (proceeds(actual, sales, stock, store, FARM) / FARM.harvest_t - actual[0]
                    if observed == len(MONTHS) else np.nan)
            results.append((region, state, year, model, name, observed, gain))
    return (
        pd.DataFrame(plans, columns=["region", "state", "year", "model", "store", "month", "sold_t", "held_t"]),
        pd.DataFrame(results, columns=["region", "state", "year", "model", "store", "observed_months", "gain_rs_t"]),
    )


def evaluate(monthly, states, output):
    panel = make_panel(monthly)
    predictions, training = zip(*(predict_season(panel, year) for year in SEASONS))
    p = pd.concat(predictions, ignore_index=True).merge(states, on="state", validate="many_to_one")
    p["split"] = p.year.map(SEASONS)
    balanced = p.loc[p.model.eq(BASELINE)].groupby(["year", "target"]).actual.count()
    p = p.join(balanced.eq(len(states)).rename("balanced"), on=["year", "target"])
    scored = p.loc[p.balanced].copy()
    if set(scored.year) != set(SEASONS):
        raise ValueError("Each season needs at least one matched observation across eight states")
    scored["abs_error"] = (scored.actual - scored.forecast).abs()
    scored["ape"] = 100 * scored.abs_error / scored.actual
    keys = ["split", "region", "state", "model"]
    scores = scored.groupby(keys, as_index=False).agg(
        months=("target", "size"), mape_pct=("ape", "mean"), mae_rs_q=("abs_error", "mean"))
    overall = scores.groupby(["split", "model"], as_index=False).agg(
        mape_pct=("mape_pct", "mean"), mae_rs_q=("mae_rs_q", "mean"))
    selected = overall.loc[overall.split.eq("validation")].sort_values(["mape_pct", "model"]).iloc[0].model
    plans, gains = storage(p, selected)
    complete_years = gains.groupby("year").gain_rs_t.apply(lambda x: x.notna().all())
    balanced_gains = gains.loc[gains.year.isin(complete_years[complete_years].index) & gains.model.eq(selected)]
    if balanced_gains.empty:
        raise ValueError("No fully observed test season across all eight states")
    regional = scores.loc[scores.split.eq("test") & scores.model.eq(selected)].groupby("region", as_index=False).agg(
        mape_pct=("mape_pct", "mean"), mae_rs_q=("mae_rs_q", "mean"))
    regional_storage = balanced_gains.groupby(["region", "year", "store"], as_index=False).agg(
        gain_rs_t=("gain_rs_t", "mean"), states_positive=("gain_rs_t", lambda x: x.gt(.01).sum()))
    coverage = panel.assign(observed_months=panel.actual.notna()).groupby(
        ["state", "year"], as_index=False)["observed_months"].sum()
    years = monthly.assign(year=monthly.month.dt.year, calendar_month=monthly.month.dt.month)
    full = years.groupby(["state", "year"]).price_rs_q.transform("size").eq(12)
    complete = years.loc[full].copy()
    complete["price_index"] = complete.price_rs_q / complete.groupby(
        ["state", "year"]).price_rs_q.transform("mean")
    seasonality = complete.groupby(["state", "calendar_month"], as_index=False).agg(
        complete_years=("year", "size"), price_index=("price_index", "mean"))
    train_counts = pd.concat(training, ignore_index=True)
    train_index = pd.MultiIndex.from_product([sorted(states.state), list(SEASONS)], names=["state", "year"])
    train_counts = train_counts.set_index(["state", "year"]).reindex(train_index, fill_value=0).reset_index()
    outputs = {"coverage": coverage, "seasonality": seasonality, "training_rows": train_counts,
               "forecasts": p, "state_scores": scores,
               "model_scores": overall, "regional_scores": regional, "sales_plans": plans,
               "storage_results": gains, "regional_storage": regional_storage,
               "selected_model": pd.DataFrame({"model": [selected]})}
    for name, data in outputs.items():
        data.to_csv(output / f"{name}.csv", index=False, float_format="%.6f")


def main():
    parser = argparse.ArgumentParser(description="Eight-state onion forecasts and storage backtest")
    parser.add_argument("--parquet", type=Path, help="Rebuild the monthly extract from the published Parquet")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    states = pd.read_csv(ROOT / "states.csv")
    if states.state.duplicated().any() or states.groupby("region").size().to_dict() != dict(
            North=2, South=2, East=2, West=2):
        raise ValueError("Expected two distinct states per region")
    if args.parquet:
        INPUT.parent.mkdir(parents=True, exist_ok=True)
        prepare(args.parquet, states.state).to_csv(INPUT, index=False, float_format="%.8f")
    monthly = pd.read_csv(INPUT)
    monthly["month"] = pd.PeriodIndex(monthly.month, freq="M")
    if set(monthly.state) != set(states.state):
        raise ValueError("Monthly extract does not match states.csv")
    args.output.mkdir(parents=True, exist_ok=True)
    evaluate(monthly, states, args.output)


if __name__ == "__main__":
    main()
