# Kanda Code

Kanda Code is our group project for Industry 4.0 (MS4001) at IIT Madras. It answers one question: when should onion farmers sell? Rabi onion, harvested in April when prices are lowest, is the part of India's crop that is stored, and Maharashtra grows about 30% of it. For a farmer group in each of the state's four main onion districts (Nashik, Ahilyanagar, Pune and Solapur), we forecast monthly mandi prices and plan how much to sell each month from April to December after storage loss, quality loss, storage cost, selling costs, interest, cash needs and handling limits.

The report tests four hypotheses, one per research question:

1. When arrivals rise, prices fall, even after allowing for the seasonal pattern.
2. Winters' seasonal model forecasts with smaller errors than assuming no change.
3. Storing and selling later earns more per tonne than selling at harvest, after all storage and selling costs.
4. A sales plan built on the forecast earns more than one built on past seasons' average prices.

## Run

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python analysis.py
python -m unittest
```

The two files in `data/` are enough to run the analysis, which takes about five minutes. To download them again from Agmarknet, run `python fetch_data.py`; responses are cached in `data/raw/`, so an interrupted download resumes. `python fetch_data.py --select` also re-applies the mandi selection rule and rewrites `markets.csv`.

## Data

- `data/mandi_monthly.csv`: monthly modal price (Rs per quintal) and arrivals (tonnes) from Agmarknet, January 2011 to December 2025, for the four study mandis. In each district we use the mandi with the most arrivals among those that miss at most 5% of months with no gap longer than three months: Pimpalgaon Baswant (Nashik), Newasa-Ghodegaon (Ahilyanagar), Solapur and Pune. 2011 is the earliest start at which all four qualify. Unreported months stay blank (19 of 720, including April-May 2020 when markets closed for the COVID-19 lockdown).
- `data/nearby_prices.csv`: monthly prices at the 33 mandis of the four districts that report at least 80% of months, used to fill the study mandis' gaps.

`analysis.py` fills a missing month with a lasso regression of the mandi's log price on the other mandis' log prices in that month, fitted only on data up to the forecast date. A gap that no other mandi reported falls back to interpolation of log price. Filled months are never scored as forecast errors, and the arrivals regression uses reported months only. `results/gap_filling_check.csv` compares the lasso with ordinary regression, interpolation and forecasting the gap, on reported months hidden at random.

## Method

| Step | Model | Why |
| --- | --- | --- |
| Fill missing months | Lasso regression on nearby mandis' prices | Uses what similar mandis were paid that month and keeps only the ones that help |
| Arrivals and price | Least squares: log price on log arrivals, month dummies and a trend | Separates the supply effect from the seasonal cycle |
| Forecasting | No change, Winters' exponential smoothing on log prices, ARIMA on 12-month log changes | A benchmark, a model of the yearly cycle and the standard time-series model |
| Sales plan | Dynamic programming solved by backward induction over the tonnes in store | The exact best monthly plan under storage loss, costs and limits |
| Value of the forecast | The same plan fed past seasons' average prices, and actual prices | Separates the seasonal calendar's value from the forecast's |

Forecasts are made at the end of March and of every later month, using only data up to that month. Seasons 2011-2013 are history, 2014-2019 validate (including the choice of ARIMA order) and 2020-2025 test. The sales plans use the forecast with the lowest validation error, for a traditional store, an improved on-farm store and a cold store.

## Results

- `results/market_summary.csv`: seasonal price and arrivals pattern, the arrivals regression, stationarity tests, and how the four mandis' prices compare.
- `results/forecasts.csv` and `results/forecast_scores.csv`: every forecast and its error on reported months. `relative_mae` is the mean absolute error divided by the mean price. `origins` is `March` for the harvest-time forecast and `All` for every forecast date.
- `results/arima_orders.csv`: validation error for each ARIMA order, and whether it converged at every forecast date.
- `results/gap_filling_check.csv`: error of each gap-filling method on hidden months.
- `results/storage_results.csv` and `results/sales_plan.csv`: gain per tonne harvested against selling everything at harvest, and the tonnes sold and held each month, for every strategy, forecast model, store and season. `filled_months` counts the season's months valued at filled prices; `selected` marks the forecast model used in the report.
- `results/sensitivity.csv`: the improved-store test result under changed costs, losses and limits.
- `results/seasonal_pattern.png`: Figure 1 of the report.

## Sources

- Directorate of Marketing and Inspection, [Agmarknet 2.0](https://agmarknet.gov.in), monthly market-wise onion prices and arrivals.
- National Horticulture Board (2018). Onion: monthly report, June 2018. Rabi share of production, harvest months and stored stock.
- Khapte, P. S. et al. (2023). An innovative onion storage structure. Indian Horticulture, May-June 2023. Onion districts, storage rent, improved store cost and loss.
- ICAR. [Onion cold storage: potential to stabilize price fluctuation](https://icar.org.in/en/node/4701). Storage loss over 120 days.
- Tibshirani, R. (1996). Regression shrinkage and selection via the lasso. Journal of the Royal Statistical Society B 58(1).
