# Kanda Code

Kanda Code is our group project for Industry 4.0 (MS4001) at IIT Madras. It asks when an onion growers' cooperative should sell its rabi harvest: at harvest in April, or from storage later in the year. We forecast monthly prices at the largest onion mandi in each state with complete records, plus Lasalgaon as the national benchmark, then plan sales after storage loss, quality loss, storage cost, selling costs, cash needs and handling limits.

## Run

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python analysis.py
python -m unittest
```

`data/mandi_monthly.csv` is enough to run the analysis. To download it again, run `python fetch_data.py`. Responses are cached in `data/raw/`, so an interrupted download resumes. `python fetch_data.py --select` rescans every district and rewrites `markets.csv`; add coordinates for any new market before downloading.

`markets.csv` lists Solapur (Maharashtra), Bara Bazar Kolkata (West Bengal), Hubballi (Karnataka), Gurgaon (Haryana) and Lasalgaon. For each state, the selection screens the three districts with the most 2024 arrivals and keeps the mandi with the most 2013-2025 arrivals among those that report every month. Andhra Pradesh, Bihar, Gujarat, Madhya Pradesh and Rajasthan have no mandi that meets this rule.

## Timeline

Every market uses the same dates. Data run from January 2008 to December 2025. A season starts with the April harvest and ends in December. Forecasts are made at the end of March and again at the end of each later month. Seasons 2011-2013 only train the models, 2014-2019 choose one and 2020-2025 test it. Training always uses only data dated before the forecast.

Every market must report every month from January 2013. Gaps of one or two months are interpolated in logs and never scored; a longer gap stops the run. Gaps before 2013 only remove those months from training.

The forecast model is the one whose sales plans earned most at the four state mandis in the validation seasons, averaged over both storage types and both plans. Lasalgaon is forecast and planned like the others but kept out of model selection and averages; every results file has a `benchmark` column to filter it.

## Read the results

- `results/market_summary.csv`: price and arrivals calendars, the arrivals regression, and the check against the NHRDF Lasalgaon archive.
- `results/forecasts.csv` and `results/forecast_scores.csv`: forecasts from every origin and their errors. `origins` is `March` for the harvest-time forecast and `All` for the monthly updates.
- `results/sales_plan.csv`: tonnes sold and held each month for the selected model, by market, season, storage type and strategy.
- `results/storage_results.csv`: realised proceeds per tonne harvested against selling everything at harvest, for every forecast model in validation and test seasons. Capital costs are excluded.
- `results/sensitivity.csv`: the cold-storage test result under changed loss, cost, quality, selling-cost, cash and curing assumptions.

## Earlier eight-state comparison

The [regional module](regional/README.md) is the earlier comparison built on the Mendeley state extract. The main analysis now covers the same question with one data source and one timeline.

## Sources

- Directorate of Marketing and Inspection, [Agmarknet 2.0](https://agmarknet.gov.in), monthly market-wise onion prices and arrivals.
- NASA Langley Research Center, [POWER daily API](https://power.larc.nasa.gov), rainfall and temperature at each mandi.
- Singla, S. (2020). [Lasalgaon Onion Data, version 1](https://doi.org/10.17632/9dn4g8m97m.1), CC BY 4.0. Monthly NHRDF prices, used to check the Agmarknet series.
- ICAR. [Onion cold storage: potential to stabilize price fluctuation](https://icar.org.in/en/node/4701). Storage loss over 120 days.
- Ministry of Finance, [Economic Survey 2021-22](https://www.indiabudget.gov.in/economicsurvey/ebook_es2022/files/basic-html/page197.html). Onion seasons and harvest months.
