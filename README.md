# Kanda Code

Kanda Code is our group project for Industry 4.0 (MS4001) at IIT Madras. It answers one question: when should onion farmers sell? Rabi onion, harvested in April when prices are lowest, is the part of India's crop that is stored, and Maharashtra grows about 30% of it. For a farmer group in each of the state's four main onion districts (Nashik, Ahilyanagar, Pune and Solapur), we forecast monthly mandi prices and plan how much to sell each month from April to December after storage loss, quality loss, storage cost, selling costs, interest, cash needs and handling limits.

The analysis tests three hypotheses, one per research question:

1. Winters' seasonal model forecasts with smaller errors than assuming no change.
2. Storing and selling later earns more per tonne than selling at harvest, after all storage and selling costs.
3. A sales plan built on the forecast earns more than one built on past seasons' average prices.

## Requirements

- Python 3.12 or newer (tested on 3.12, 3.14 and 3.15).
- The packages in `requirements.txt`, installed with pip as below.
- No internet connection for the analysis; `fetch_data.py` needs one to download from Agmarknet.
- About seven minutes of run time on a laptop.
- The figure uses Times New Roman if it is installed; otherwise matplotlib uses its default font, and only the figure's look changes.

## Run

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python analysis.py        # about seven minutes; prints each of its seven steps
python -m unittest
```

`analysis.py` writes its outputs to `results/` and gives the same numbers on every run.

`data/mandi_monthly.csv` and `data/nearby_prices.csv` are all the analysis needs. To download them again from Agmarknet, run `python fetch_data.py`; responses are cached in `data/raw/`, so an interrupted download resumes. `python fetch_data.py --select` also re-applies the mandi selection rule and rewrites `markets.csv`, and `python fetch_data.py --share 2024` saves the four districts' share of Maharashtra's reported onion arrivals in 2024 to `data/state_share.csv`.

## Data

- `data/mandi_monthly.csv`: monthly modal price (Rs per quintal) and arrivals (tonnes) from Agmarknet, January 2011 to December 2025, for the four study mandis. In each district we use the mandi with the most arrivals among those that miss at most 5% of months with no gap longer than three months: Pimpalgaon Baswant (Nashik), Newasa-Ghodegaon (Ahilyanagar), Solapur and Pune. 2011 is the earliest start at which all four qualify. Unreported months stay blank (19 of 720, including April-May 2020 when markets closed for the COVID-19 lockdown).
- `data/nearby_prices.csv`: monthly prices at the 33 mandis of the four districts that report at least 80% of months, used to fill the study mandis' gaps.
- `data/state_share.csv`: the four districts' share of Maharashtra's reported onion arrivals in 2024.

`analysis.py` fills a missing month with a lasso regression of the mandi's log price on the other mandis' log prices in that month, fitted only on data up to the forecast date. A gap that no other mandi reported falls back to interpolation of log price. Filled months are never scored as forecast errors; three test market-seasons are valued partly at filled prices, and `filled_months` in `results/storage_results.csv` marks them.

## Method

| Step | Model | Why |
| --- | --- | --- |
| Fill missing months | Lasso regression on nearby mandis' prices | Uses what similar mandis were paid that month and keeps only the ones that help |
| Data description | Least squares: log price on log arrivals, month dummies and a trend | Shows how prices move with arrivals, and that one group's sales cannot move the price |
| Forecasting | No change, past-seasons average, Winters' exponential smoothing on log prices, ARIMA on 12-month log changes | Two simple benchmarks, a model of the yearly cycle and the standard time-series model |
| Sales plan | Dynamic programming solved by backward induction over the tonnes in store | The best monthly plan under storage loss, costs and limits |
| Value of the forecast | The same plan fed past seasons' average prices, and actual prices | Separates the seasonal calendar's value from the forecast's |

Forecasts are made at the end of March and of every later month, using only data up to that month. Seasons 2011-2013 are history, 2014-2019 validate (including the choice of ARIMA order and of the forecast the plans use) and 2020-2025 test. Winters and ARIMA forecast log prices, so their forecasts are medians; the plans need expected prices, so they scale each forecast by exp(s²/2), where s² is the mean squared log error at that horizon in the validation seasons other than the one being planned. The plans are compared for a ventilated chawl, an improved on-farm store and an ICAR-DOGR cold store. Because the four mandis' prices move together, the tests in `results/season_tests.csv` treat seasons as the independent units.

## How to read the results

Start with `results/key_figures.csv`: it lists the headline numbers with plain labels. The other files hold the detail behind them. Two rules apply throughout:

- **Validation vs test.** Choices (the ARIMA order, which forecast the plans use, the forecast correction) are made on the validation seasons 2014-2019. The test seasons 2020-2025 are the fair check, because nothing was tuned on them.
- **p-values.** In `season_tests.csv` each season counts once. A `t_p` below 0.05 means the difference is unlikely to be chance; above it, the data cannot tell the two apart.

**The data.** `market_summary.csv` has one row per mandi: how low April prices are and how high the peak is (`april_index`, `peak_index`), when arrivals peak, how price moves with arrivals (`arrivals_beta`), and whether the series are stable enough to model (`adf_p_...`). `seasonal_pattern.png` draws the price pattern and arrivals by month.

**Missing months.** In `gap_filling_check.csv`, average `abs_pct_error` by `method`: the method with the lowest error fills gaps best.

**Question 1: is Winters a better forecast than no change?** In `forecast_scores.csv`, take the rows for a `split` and `origins` and average `relative_mae` over the four mandis for each `model`; lower is better. `origins = March` is the harvest-time forecast that the March plan uses. Then read the `Winters minus No change relative MAE` rows of `season_tests.csv`: a negative `mean` favours Winters, and `t_p` says whether the gap is real.

**Question 2: does storing pay?** In `storage_results.csv`, `gain_rs_t` is what a plan earned per harvested tonne beyond selling everything in April; positive means storing paid. The main result is the rows with `split = test`, `strategy = March plan` and `selected = True`, averaged by `storage`. The `Improved-store gain of the March plan` rows of `season_tests.csv` test it. `break_even.csv` gives the storage loss at which storing stops paying, `sensitivity.csv` shows the gain under changed assumptions, and `sales_plan.csv` shows how many tonnes each plan sold in each month.

**Question 3: does the forecast beat the past-seasons pattern?** In `storage_results.csv`, compare `gain_rs_t` for the `March plan` (selected model) with the `Past seasons` strategy, store by store. The `March plan minus past-seasons plan` rows of `season_tests.csv` test the difference for the improved store: a positive `mean` favours the forecast.

The results in `results/` show:

- Winters has the lowest error over all forecast dates (34.0% of the price in testing), but its gap to no change is not significant season by season, and at the end-March forecast the two simple benchmarks did better in testing. Hypothesis 1 is not supported.
- Storing pays with a low-loss store: the improved store's March plan gained Rs 4,116 per tonne in testing (48% over an April sale) and was positive in 10 of 12 seasons (p = 0.01). With a chawl, which loses over half its weight in four months, storing loses money. Hypothesis 2 holds for low-loss stores only.
- The forecast plan earned Rs 173 per tonne more than the past-seasons plan in testing, but the difference is not significant (p = 0.40). Hypothesis 3 is not supported: the gain comes from the seasonal calendar.

## Column guide

Money is in rupees: `_rs_q` per quintal (100 kg), `_rs_t` per tonne. Shares are fractions (0.48 = 48%). `market` is the mandi, and `season` is the April-December season of that year.

**Data files**
- `mandi_monthly.csv`: `month` (YYYY-MM), `price_rs_q` modal price (blank if unreported), `arrivals_t` tonnes arriving that month.
- `nearby_prices.csv`: `month`, `price_rs_q` at each nearby mandi.
- `state_share.csv`: `four_district_share` of Maharashtra's reported onion arrivals in `year`.
- `markets.csv`: the chosen mandi per district, its total arrivals 2011-2025 (`arrivals_kt`, thousand tonnes) and `unreported_months`.

**`forecasts.csv`** (one row per forecast)
- `start`: forecast date within the season (0 = end of March, 1 = end of April, ...); `origin`: last month of data used.
- `target`: month forecast; `horizon`: months ahead.
- `model`, `forecast` (Rs/q), `actual` (Rs/q, blank if unreported); `observed`: True if `actual` was reported (only these are scored).

**`forecast_scores.csv`** (one row per split, mandi, model and origin set)
- `split`: `validation` (2014-2019) or `test` (2020-2025); `origins`: `March` (end-March forecasts only) or `All` (every forecast date).
- `mae_rs_q`: mean absolute error; `mean_price_rs_q`: mean actual price; `relative_mae`: the two divided.

**`arima_orders.csv`**: `model` ARIMA(p, d, q), its `validation_relative_mae`, `converged_every_fit` (orders that failed to fit at any date are not eligible) and `selected`.

**`gap_filling_check.csv`**: `method`, `gap_months` (length of the hidden gap) and `abs_pct_error` (mean absolute error as a share of the true price).

**`storage_results.csv`** (one row per mandi, season, store and strategy)
- `storage`: `Chawl`, `Improved` or `Cold`.
- `strategy`: `March plan` (fixed from the end-March forecast), `Monthly re-plan` (re-solved with each new forecast), `Past seasons` (planned on earlier seasons' average prices) or `Perfect foresight` (planned on the actual prices, the best possible).
- `model`: forecast used (blank for `Past seasons` and `Perfect foresight`); `selected`: True for the model chosen on validation.
- `net_rs_t`: present value of sales minus all costs per harvested tonne; `harvest_sale_rs_t`: the same for selling everything in April; `gain_rs_t`: the difference.
- `storage_charge_rs_t`: storage cost included in `net_rs_t`; `filled_months`: months of the season valued at filled prices.

**`sales_plan.csv`**: for each plan in `storage_results.csv`, `sold_t` (tonnes sold in `month`) and `end_stock_t` (tonnes left in store after that month's sales).

**`sensitivity.csv`**: the improved store in the test seasons, with the columns of `storage_results.csv`; `scenario` names the assumption changed (`Base` changes nothing).

**`break_even.csv`**: `value` of each `quantity`; for the loss, `loss_over_four_months` and `loss_over_six_months` give the same monthly loss over a longer period.

**`season_tests.csv`** (one row per comparison and season set)
- `seasons`: `test` (2020-2025) or `all` (2014-2025); `n`: number of seasons; `mean`: average across seasons; `positive`: seasons above zero.
- `t`, `t_p`: one-sample t-test that the mean is zero; `sign_p`: sign test on the count of positive seasons.

**`market_summary.csv`** (one row per mandi)
- `april_index`, `peak_index`: April and peak-month price relative to the year's mean; `peak_month`; `aug_oct_over_april`: August-October price relative to April.
- `peak_arrivals_month`, `lowest_arrivals_month`.
- `arrivals_beta`: % change in price for 1% more arrivals, with month and trend held fixed; `arrivals_se`, `arrivals_t`, `arrivals_p`, `r2`, `adj_r2`, `f_stat`, `f_p`, `n_months`: the regression's statistics.
- `arrivals_vif`: overlap between arrivals and the month effects (below 5 is fine); `residual_lag1_corr`: how much each month's error repeats the last (near 1 means the p-values are optimistic).
- `aug_oct_arrivals_t`: mean monthly arrivals in August-October of the test years; `price_change_300t`: price change if a farmer group sold 300 t more in such a month.
- `adf_p_log_price`, `adf_p_12_month_change`: Augmented Dickey-Fuller p-values (below 0.05 means the series is stable enough to model).
- `price_vs_mandi_mean`: price relative to the four-mandi average; `lowest_price_correlation`: lowest correlation with another study mandi.

**`key_figures.csv`**: `section`, a plain `quantity` label and its `value`.

## Sources

- Directorate of Marketing and Inspection, [Agmarknet 2.0](https://agmarknet.gov.in), monthly market-wise onion prices and arrivals.
- National Horticulture Board (2018). [Onion: monthly report, June 2018](https://www.nhb.gov.in/statistics/Reports/OnionJune2018.pdf). Rabi share of production and Maharashtra's share.
- Khapte, P. S. et al. (2023). [An innovative onion storage structure](https://epubs.icar.org.in/index.php/IndHort/article/view/126543). Indian Horticulture 68(3). Storage rent, improved store cost, loss and holding period.
- ICAR. [Onion cold storage: potential to stabilize price fluctuation](https://icar.org.in/en/node/4701). Loss in a ventilated store and the ICAR-DOGR cold store over 120 days.
- Press Information Bureau (2024, 26 March). [Onion buffer procurement and export measures](https://pib.gov.in/PressReleasePage.aspx?PRID=2016405).
- Tibshirani, R. (1996). Regression shrinkage and selection via the lasso. Journal of the Royal Statistical Society B 58(1).
