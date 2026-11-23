"""Download Agmarknet onion prices and arrivals for the four districts."""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from analysis import DATA_END, DATA_START, MARKETS, NEARBY_MIN_REPORTED, ROOT, usable

RAW = ROOT / "data" / "raw"
AGMARKNET = "https://api.agmarknet.gov.in/v1/"
ONION = 23
STATE, STATE_ID = "Maharashtra", 20
DISTRICTS = {"Nashik": 361, "Ahilyanagar": 338, "Solapur": 369, "Pune": 364}
RETRY_STATUS = {429, 500, 502, 503, 504}


def request(url, cache, required, attempts=8, pause=1.0):
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
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            if attempt == attempts - 1:
                raise RuntimeError(f"{url} failed: {error}") from error
        time.sleep(min(300, 15 * 2 ** attempt))
    if required not in data:
        raise RuntimeError(f"{url} returned no {required!r}: {data}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data))
    return data


def monthly_report(kind, district_id, year, month):
    query = {"report_mode": "Marketwise", "commodity": ONION, "year": year, "month": month,
             "state": STATE_ID, "district": district_id}
    url = AGMARKNET + f"price-trend/wholesale-{kind}-monthly?" + urllib.parse.urlencode(query)
    return request(url, RAW / "agmarknet" / kind / f"{STATE_ID}_{district_id}_{year}_{month:02d}.json",
                   "rows")


def monthly_rows(kind, district_id, year, month):
    data = monthly_report(kind, district_id, year, month)
    rows = []
    for row in data["rows"]:
        for key, value in row.items():
            if key.startswith(kind + "_") and value is not None:
                name, period = key[len(kind) + 1:].rsplit("_", 1)
                rows.append({"market": row["market"].strip(), "month": pd.Period(
                    f"{name} {period}", freq="M"), kind: float(value)})
    return rows


def district_series(district_id):
    # each report covers two months
    rows = []
    for month in pd.period_range(DATA_START, DATA_END, freq="M"):
        if month.month % 2 == 0 or month == DATA_END:
            for kind in ("prices", "arrivals"):
                rows.extend(monthly_rows(kind, district_id, month.year, month.month))
    data = pd.DataFrame(rows)
    data = data[data.month.between(DATA_START, DATA_END)]
    # overlapping reports must agree
    spread = data.groupby(["market", "month"]).agg(["min", "max"])
    for kind in ("prices", "arrivals"):
        if not (spread[kind]["max"] - spread[kind]["min"]).fillna(0).le(.01).all():
            raise RuntimeError(f"District {district_id}: inconsistent repeated {kind} values")
    data = data.groupby(["market", "month"], as_index=False).first()
    return data.rename(columns={"prices": "price_rs_q", "arrivals": "arrivals_t"})


def state_share(year):
    query = urllib.parse.urlencode({"commodity": ONION, "state": STATE_ID})
    districts = request(AGMARKNET + "price-trend/district-filter?" + query,
                        RAW / "agmarknet" / "districts" / f"{STATE_ID}.json", "data")["data"]
    totals = {}
    for district in districts:
        # the year suffix drops the year-ago column
        reports = [monthly_report("arrivals", district["district_id"], year, month).get("total") or {}
                   for month in range(2, 13, 2)]
        totals[district["district_id"]] = sum(value for total in reports for key, value in total.items()
                                              if key.startswith("arrivals_") and key.endswith(f"_{year}")
                                              and value is not None)
    return sum(totals[i] for i in DISTRICTS.values()) / sum(totals.values())


def select_market(data):
    months = pd.period_range(DATA_START, DATA_END, freq="M")
    totals = {}
    for market, rows in data.groupby("market"):
        rows = rows.set_index("month").reindex(months)
        if usable(rows.price_rs_q) and usable(rows.arrivals_t):
            totals[market] = (rows.arrivals_t.sum(), int(rows[["price_rs_q", "arrivals_t"]].isna().any(axis=1).sum()))
    if not totals:
        raise RuntimeError("No mandi in the district has a usable record")
    market = max(totals, key=lambda m: totals[m][0])
    return market, round(totals[market][0] / 1000), totals[market][1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--select", action="store_true", help="Rewrite markets.csv from the arrivals ranking.")
    parser.add_argument("--share", type=int, metavar="YEAR",
                        help="Save the four districts' share of Maharashtra's onion arrivals and stop.")
    args = parser.parse_args()
    if args.share:
        share = state_share(args.share)
        pd.DataFrame([{"year": args.share, "four_district_share": share}]).to_csv(
            ROOT / "data" / "state_share.csv", index=False, float_format="%.4f")
        print(f"{args.share}: {share:.1%} of Maharashtra's reported onion arrivals")
        return
    series = {district: district_series(district_id) for district, district_id in DISTRICTS.items()}
    if args.select:
        chosen = [(district, *select_market(data)) for district, data in series.items()]
        markets = pd.DataFrame(chosen, columns=["district", "market", "arrivals_kt", "unreported_months"])
        markets.insert(0, "state", STATE)
        markets.to_csv(MARKETS, index=False)
        print(markets.to_string(index=False))
    markets = pd.read_csv(MARKETS)
    months = pd.period_range(DATA_START, DATA_END, freq="M")
    frames = []
    for m in markets.itertuples():
        rows = series[m.district].query("market == @m.market").set_index("month").reindex(months)
        if rows.price_rs_q.notna().sum() == 0:
            raise RuntimeError(f"{m.market} is missing from {m.district}")
        frames.append(rows[["price_rs_q", "arrivals_t"]].rename_axis("month").reset_index().assign(
            state=m.state, district=m.district, market=m.market))
    columns = ["state", "district", "market", "month", "price_rs_q", "arrivals_t"]
    # unreported months stay blank
    pd.concat(frames)[columns].to_csv(ROOT / "data" / "mandi_monthly.csv", index=False, float_format="%.2f")

    # nearby mandis, for gap filling
    nearby = []
    for district, data in series.items():
        for market, rows in data.groupby("market"):
            rows = rows.set_index("month").reindex(months)
            if rows.price_rs_q.notna().mean() >= NEARBY_MIN_REPORTED:
                nearby.append(rows[["price_rs_q"]].rename_axis("month").reset_index().assign(
                    district=district, market=market))
    pd.concat(nearby)[["district", "market", "month", "price_rs_q"]].to_csv(
        ROOT / "data" / "nearby_prices.csv", index=False, float_format="%.2f")


if __name__ == "__main__":
    main()
