"""Download monthly mandi prices and arrivals (Agmarknet) and weather (NASA POWER)."""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

from analysis import BENCHMARK, COMPLETE_FROM, DATA_END, DATA_START, is_complete

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
AGMARKNET = "https://api.agmarknet.gov.in/v1/"
POWER = "https://power.larc.nasa.gov/api/temporal/daily/point"
ONION = 23
STATE_IDS = {"Andhra Pradesh": 2, "Bihar": 5, "Gujarat": 11, "Haryana": 12, "Karnataka": 16,
             "Madhya Pradesh": 19, "Maharashtra": 20, "Rajasthan": 29, "West Bengal": 36}
RETRY_STATUS = {429, 500, 502, 503, 504}
BENCHMARK_ROW = {"state": "Maharashtra", "state_id": 20, "district": "Nashik", "district_id": 361,
                 "market": BENCHMARK, "basis": "National benchmark"}


def request(url, cache, attempts=8, pause=1.0):
    if cache.exists():
        return json.loads(cache.read_text())
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(attempts):
        time.sleep(pause)
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUS or attempt == attempts - 1:
                raise RuntimeError(f"{url} failed with HTTP {error.code}") from error
            time.sleep(min(300, 15 * 2 ** attempt))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return data


def agmarknet(endpoint, cache, **query):
    url = AGMARKNET + endpoint + "?" + urllib.parse.urlencode(query)
    return request(url, RAW / "agmarknet" / cache)


def monthly_report(kind, state_id, district_id, year, month):
    """One district report: market values for this month, last month and a year ago."""
    data = agmarknet(f"price-trend/wholesale-{kind}-monthly",
                     f"{kind}/{state_id}_{district_id}_{year}_{month:02d}.json",
                     report_mode="Marketwise", commodity=ONION, year=year,
                     month=month, state=state_id, district=district_id)
    if "rows" not in data:
        raise RuntimeError(f"Agmarknet {kind} {state_id}/{district_id} {year}-{month}: {data}")
    rows = []
    for row in data["rows"]:
        for key, value in row.items():
            if key.startswith(kind + "_") and value is not None:
                name, period = key[len(kind) + 1:].rsplit("_", 1)
                rows.append({"market": row["market"].strip(), "month": pd.Period(
                    f"{name} {period}", freq="M"), kind: float(value)})
    return rows


def district_series(state_id, district_id, start=DATA_START, kinds=("prices", "arrivals")):
    """Every market in the district, monthly from `start` to DATA_END (each report has two months)."""
    rows = []
    for month in pd.period_range(start, DATA_END, freq="M"):
        if month.month % 2 == 0 or month == DATA_END:
            for kind in kinds:
                rows.extend(monthly_report(kind, state_id, district_id, month.year, month.month))
    data = pd.DataFrame(rows)
    data = data[data.month.between(start, DATA_END)]
    # Overlapping reports repeat the same month; they must agree.
    spread = data.groupby(["market", "month"]).agg(["min", "max"])
    for kind in kinds:
        if kind in spread and not (spread[kind]["max"] - spread[kind]["min"]).fillna(0).le(.01).all():
            raise RuntimeError(f"District {district_id}: inconsistent repeated {kind} values")
    return data.groupby(["market", "month"], as_index=False).first()


def screen_districts(state_id, districts, year):
    """Districts ranked by arrivals in the June and December reports (May-June and Nov-Dec) of `year`."""
    totals = {}
    for name, district_id in districts:
        for month in (6, 12):
            for row in monthly_report("arrivals", state_id, district_id, year, month):
                if row["month"].year == year:
                    key = (name, district_id)
                    totals[key] = totals.get(key, 0) + row["arrivals"]
    return sorted(totals, key=totals.get, reverse=True)


def complete_markets(state_id, district_id):
    """Arrivals since COMPLETE_FROM for the district's markets that report every month."""
    data = district_series(state_id, district_id, COMPLETE_FROM, kinds=("arrivals",))
    months = pd.period_range(COMPLETE_FROM, DATA_END, freq="M")
    totals = {}
    for market, rows in data.groupby("market"):
        arrivals = rows.set_index("month").arrivals.reindex(months)
        if is_complete(arrivals):
            totals[market] = arrivals.sum()
    return totals


def select_markets(states, screen_year=2024, shortlist=3):
    """Within each state's `shortlist` largest districts, the complete mandi with the most arrivals."""
    chosen = []
    for state in states:
        state_id = STATE_IDS[state]
        districts = agmarknet("price-trend/district-filter", f"districts/{state_id}.json",
                              commodity=ONION, state=state_id)["data"]
        ranked = screen_districts(state_id, [(d["district_name"], d["district_id"]) for d in districts],
                                  screen_year)
        totals = {(name, district_id, market): total
                  for name, district_id in ranked[:shortlist]
                  for market, total in complete_markets(state_id, district_id).items()}
        if not totals:
            print(f"{state}: no market in the {shortlist} largest districts reports every month "
                  f"from {COMPLETE_FROM}; excluded")
            continue
        best = max(totals, key=totals.get)
        chosen.append({"state": state, "state_id": state_id, "district": best[0],
                       "district_id": best[1], "market": best[2],
                       "basis": f"Most arrivals {COMPLETE_FROM.year}-{DATA_END.year}, reporting every month"})
    if BENCHMARK not in {c["market"] for c in chosen}:
        chosen.append(BENCHMARK_ROW)
    return pd.DataFrame(chosen)


def weather(market, lat, lon):
    query = {"parameters": "PRECTOTCORR,T2M_MAX,T2M_MIN", "community": "AG",
             "latitude": lat, "longitude": lon, "format": "JSON",
             "start": DATA_START.start_time.strftime("%Y%m%d"),
             "end": DATA_END.end_time.strftime("%Y%m%d")}
    data = request(POWER + "?" + urllib.parse.urlencode(query),
                   RAW / "power" / f"{lat}_{lon}_{query['start']}_{query['end']}.json")
    values = pd.DataFrame(data["properties"]["parameter"])
    values = values.replace(data["header"]["fill_value"], float("nan"))
    if values.isna().any().any():
        raise RuntimeError(f"{market}: NASA POWER returned missing days")
    values.index = pd.to_datetime(values.index, format="%Y%m%d").to_period("M")
    monthly = values.groupby(level=0).agg({"PRECTOTCORR": "sum", "T2M_MAX": "mean", "T2M_MIN": "mean"})
    monthly.columns = ["rain_mm", "tmax_c", "tmin_c"]
    return monthly.rename_axis("month").reset_index().assign(market=market)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--select", action="store_true",
                        help="Rescan every district and rewrite markets.csv.")
    args = parser.parse_args()
    markets_file = ROOT / "markets.csv"
    if args.select:
        markets = select_markets(STATE_IDS)
        if markets_file.exists():
            located = pd.read_csv(markets_file)[["market", "lat", "lon"]]
            markets = markets.merge(located, on="market", how="left")
        markets.to_csv(markets_file, index=False)
        print(markets.to_string(index=False))
        return
    markets = pd.read_csv(markets_file)
    if markets[["lat", "lon"]].isna().any().any():
        raise ValueError("markets.csv needs coordinates for every market")
    series, climate = [], []
    for m in markets.itertuples():
        district = district_series(m.state_id, m.district_id)
        found = district[district.market.eq(m.market)]
        if found.empty:
            raise RuntimeError(f"{m.market} is missing from district {m.district_id}")
        series.append(found)
        climate.append(weather(m.market, m.lat, m.lon))
    # Weather covers every month; months without mandi reports keep blank prices.
    prices = pd.concat(climate).merge(pd.concat(series), on=["market", "month"],
                                      how="left", validate="one_to_one")
    prices = prices.merge(markets[["market", "state"]], on="market", validate="many_to_one")
    prices = prices.rename(columns={"prices": "price_rs_q", "arrivals": "arrivals_t"})
    columns = ["state", "market", "month", "price_rs_q", "arrivals_t", "rain_mm", "tmax_c", "tmin_c"]
    prices[columns].sort_values(["state", "market", "month"]).to_csv(
        ROOT / "data" / "mandi_monthly.csv", index=False, float_format="%.2f")


if __name__ == "__main__":
    main()
