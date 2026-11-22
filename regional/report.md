# When Should Onion Farmers Sell?
An Eight-State Comparison of Onion Forecasts and Storage Decisions

Kanda Code | MS4001 Industry 4.0 | IIT Madras BS

## 1. Problem statement

An onion growers' cooperative can sell in April or hold part of its harvest for later months. Waiting can bring a better price, but it also costs money and leaves less saleable stock. We forecast prices in eight states and use the forecasts to plan sales from April to December.

## 2. Motivation for problem selection

A sales plan based on western markets may not behave the same way elsewhere. Comparing two states in each of four regions shows whether the gains from waiting hold across the selected markets and whether a more complex forecast helps.

## 3. Research questions

Which forecast gives the lowest validation error? Do March arrivals and weather improve on price and calendar patterns? After costs and spoilage, does storing onions beat an April sale in the selected states?

## 4. Hypotheses, objectives and constraints

We expect seasonal forecasts to improve on holding the March price fixed and cold storage to make waiting more attractive. We maximise revenue after operating costs for a 1,000-tonne harvest. Closing stock is capped at 700 tonnes, at least 250 tonnes must be sold in April, monthly sales after April cannot exceed 300 tonnes, and December closing stock must be zero.

## 5. Exploratory data analysis

We select the two largest reported 2023-24 onion producers by tonnage within each of four Ministry of Home Affairs zones. Central and Northeast are outside scope. Daily Agmarknet modal prices become arrival-weighted monthly state prices. Repeated arrival totals across varieties are counted once per market-day. March weather is averaged over reporting market-days from the IMD fields in the dataset.

| Zone | Rank 1 (thousand tonnes) | Rank 2 (thousand tonnes) |
| --- | --- | --- |
| North | Rajasthan: 1,630.50 | Haryana: 541.00 |
| South | Karnataka: 1,637.89 | Andhra Pradesh: 512.79 |
| East | Bihar: 1,387.76 | West Bengal: 857.00 |
| West | Maharashtra: 8,602.00 | Gujarat: 2,057.00 |

In complete calendar years, average April prices range from 0.55 to 0.73 times the state's annual mean. November is the highest-index month in seven states; Andhra Pradesh peaks in August. April is the common comparison date in every state, although harvest timing varies.

<!-- pagebreak -->

## 6. Methodology

**Forecasting.** Each forecast uses observations dated no later than March. We compare March-price persistence, pooled historical monthly price ratios, and a recency-weighted version. We also fit three pooled ridge regressions on log prices relative to March: a calendar and March-price model, one adding March arrivals per market-day, and one adding March rainfall and temperature. The regressions use the same training rows. Pooling gives Bihar a usable starting point when it has no eligible pre-2022 training rows. The dataset has no onion-specific fertilizer or soil measurements.

**Evaluation.** We select one common model using the equally weighted state mean absolute percentage error (MAPE) in 2022. Earlier seasons train each forecast; 2023-24 scores do not change the choice. Bihar and Andhra Pradesh lack July 2023 prices. Forecasts are scored on the 17 months observed in every state across the two test years, without filling the missing prices.

**Sales plan.** A linear programme sets monthly sales and stocks using each forecast. Each month, sales plus closing stock equal the available stock after loss. The ventilated scenario uses 18.05% monthly loss and Rs 250 per tonne-month; cold storage uses 1.83% and Rs 700. We value each fixed plan using observed prices and compare it with selling all stock in April. For like-for-like regional gains we use 2024, the only complete test season across all eight states.

## 7. Results

| Forecast | 2022 validation MAPE | 2023-24 test MAPE |
| --- | ---: | ---: |
| March price | 25.2% | 41.8% |
| Pooled seasonality | 53.4% | 28.6% |
| Recent seasonality | 77.1% | 25.3% |
| Calendar ridge | 29.0% | 34.4% |
| Calendar + arrivals | 29.0% | 34.4% |
| Calendar + arrivals + weather | 15.6% | 33.9% |

The weather model won in validation; recent seasonality was more accurate in the held-out years. Adding arrivals alone made little difference. Weather improved validation substantially but cut test MAPE by less than half a percentage point relative to the arrivals model. The added inputs did not consistently beat a simple seasonal rule.

<!-- pagebreak -->

## 7. Results (continued)

| Zone | State | Test MAPE | 2024 cold gain (Rs/t) |
| --- | --- | ---: | ---: |
| North | Haryana | 25.4% | 7,397 |
| North | Rajasthan | 31.2% | 9,248 |
| South | Andhra Pradesh | 49.1% | 14,602 |
| South | Karnataka | 32.5% | 5,979 |
| East | Bihar | 38.2% | 9,927 |
| East | West Bengal | 28.2% | 15,161 |
| West | Gujarat | 30.1% | 10,216 |
| West | Maharashtra | 36.6% | 9,091 |

In 2024 the selected forecast's cold-storage plan beat an April sale in all eight states. Mean gains per tonne harvested were Rs 12,544 in East, Rs 10,291 in South, Rs 9,653 in West and Rs 8,322 in North, giving equal weight to each state. The ventilated plan sold everything in April. Doubling cold storage cost reduced North's average gain to Rs 1,392 per tonne. The pooled seasonal plan, used as a decision benchmark, earned Rs 11,521 per tonne across the eight states versus Rs 10,203 for the weather model in 2024.

## 8. Managerial implications

Look at the forecast and the cost of waiting together. Where costs and losses are low, a cooperative can hold part of the crop and release it in batches; verify local offers, harvest timing and carrying costs before using the plan. Use stock weight, temperature and humidity readings to check whether loss assumptions are realistic. If forecasts disagree, compare the sales plans rather than assuming a more complex price model produces a better decision.

The gains exclude capital and financing costs. One season is too short to estimate payback. The two-state averages describe these markets only, and Bihar's early price history is sparse.

## 9. References

1. Shelar, Hajare and Mangarule (2025). Agricultural price forecasting dataset, 2014-2024. Mendeley Data V1. doi:10.17632/ds9jmxp9zy.1.
2. ICAR-IASRI. Agricultural Research Data Book 2025, table 4.12: state-wise onion area, production and productivity.
3. Ministry of Home Affairs. Zonal Councils. mha.gov.in/zonal-council.
4. ICAR. Onion cold storage: potential to stabilize price fluctuation. icar.org.in/en/node/4701.
