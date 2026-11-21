# When Should Onion Farmers Sell?
Price Forecasting and Sell-or-Store Planning

Kanda Code | MS4001 Industry 4.0 | IIT Madras BS

## 1. Problem statement

An onion growers' cooperative can sell at harvest or hold some stock for later months. A higher price later in the year does not automatically make storage worthwhile: some onions are lost, storage costs money, and only a limited quantity can be moved each month. We compare monthly sales plans for a cooperative with 1,000 tonnes available in April. We use Maharashtra as the starting market and test the same decision on Gujarat prices.

## 2. Motivation for problem selection

The harvest price is often low, but a decision to wait has to be made before the later prices are known. A useful plan has to answer both questions: what are prices likely to do, and will the increase cover the loss and cost of holding stock?

## 3. Research questions

1. Are higher onion arrivals associated with lower monthly prices in both states?
2. Does a seasonal model forecast April to December prices better than the last available price or the same month last year?
3. Do forecast-based sales plans beat selling the full harvest in April after storage costs and losses?

## 4. Hypotheses, objectives and constraints

We expect higher arrivals to be associated with lower prices and low-loss storage to make waiting more attractive. The objective is to maximise sales revenue minus storage operating costs. The decision variables are tonnes sold and tonnes left in storage each month. The cooperative can hold up to 700 tonnes, must sell at least 250 tonnes in April, and can move at most 300 tonnes per month from May onward. No stock remains at the end of December.

## 5. Exploratory data analysis

The Agmarknet compilation has daily modal prices and arrivals by market. We drop nonpositive arrivals, prices outside Rs 50–20,000 per quintal, and prices outside 0.2–5 times the state-day median. When the same arrival total repeats across varieties on a market day, we count it once and use the mean of the reported prices. We then weight each market-day price by arrivals to obtain a monthly state benchmark.

Both states have 132 months (January 2014 to December 2024). April averages 0.55 times the year's mean in Maharashtra and 0.58 in Gujarat. November averages 1.55 and 1.45 times the mean, respectively. These are historical patterns, not guarantees about next season. We also use monthly NHRDF prices for Lasalgaon from January 1996 to June 2019.

<!-- pagebreak -->

## 6. Methodology

**Arrivals regression.** We regress log monthly price on log arrivals per reporting market-day, with month and year effects. Newey–West standard errors allow for short-run serial correlation. This is an association test; it does not show what would happen if an individual farmer increased supply.

**Forecasting.** At each March cutoff we predict the following nine months. We compare the last observed price, the price for the same month last year, and a log-price regression with a time trend and calendar-month effects. The last model allows prices to change with time while keeping the explanation for seasonal movements simple. For each state we choose the model on the 2019–2022 validation seasons, then score it on 2023–2024. For the older Lasalgaon archive we use 2013–2016 for validation and 2017–2018 for testing. Forecasts use no prices after the March cutoff.

**Sales plan.** We multiply the forecast price per quintal by ten to get rupees per tonne. The linear programme chooses monthly sales and closing stocks. April sales plus April closing stock equal the harvest. In each later month, sales and closing stock sum to the previous month's stock after spoilage. The model maximises forecast revenue minus the cost of holding closing stock.

The ventilated scenario uses 18.05% monthly loss and Rs 250 per tonne-month. The cold scenario uses 1.83% and Rs 700 per tonne-month. We apply the same cost assumptions across markets; they are not local quotes. We judge each plan at the prices that actually occurred and compare it with selling all 1,000 tonnes at the observed April price.

## 7. Results

| Market | Selected forecast | Validation MAPE | Test MAPE | Cold gain vs April |
| --- | --- | ---: | ---: | ---: |
| Gujarat | Trend + month effects | 37.1% | 24.8% | Rs 10,034/t |
| Maharashtra | Trend + month effects | 36.9% | 29.5% | Rs 9,980/t |
| Lasalgaon archive | Last observed price | 34.9% | 34.7% | Rs 0/t |

Gain is per tonne harvested, averaged over the two test seasons in each market; it excludes capital costs. The seasonal-naive test error was 31.0% in Gujarat and 34.8% in Maharashtra, compared with 24.8% and 29.5% for the selected model.

Higher arrivals were associated with lower prices in Maharashtra (coefficient -0.442, p = 0.013), but we did not see the same relationship in Gujarat (-0.015, p = 0.874). The absolute price errors still matter: the selected model missed by an average of Rs 636 per quintal in Gujarat and Rs 660 in Maharashtra.

<!-- pagebreak -->

## 7. Results (continued)

The ventilated-storage plan sold everything in April in both states' test years. In Gujarat, the cold-storage plan gained Rs 9,853 per tonne in 2023 and Rs 10,216 in 2024, after storage operating costs. For the 2024 Gujarat season, the March forecast leads to sales of 300 tonnes in April, about 22 in August, and 300 each in October and November. About 78 tonnes are lost in storage. The same April harvest date is assumed for both states to compare the plans.

| Gujarat cold scenario | Mean gain above April sale |
| --- | ---: |
| Base: 1.83% monthly loss, Rs 700/t-month | Rs 10,034/t harvested |
| Monthly loss increased to 5% | Rs 5,587/t harvested |
| Storage operating cost doubled | Rs 5,023/t harvested |

For Lasalgaon, the last observed price performed best in validation. Because that forecast stays flat and storage costs money, the programme sold at harvest in both test years. Lasalgaon is a single market tested over a different period, so we do not compare its performance directly with the state results.

## 8. Managerial implications

Use the plan as a starting point for the cooperative, not a promise of the best sale date. Sell enough at harvest to meet cash needs and stay within capacity. Before holding stock, check the actual local purchase offer, handling charges and storage loss. Monitor temperature, humidity and stock weight, then use the measured loss and updated prices to decide whether to release the next batch early.

The operating gains are based on two recent test seasons and state-average prices. They do not include equipment investment, interest, grade differences or the effect of large sales on prices. Do not infer a cold-store payback period from this comparison. Test the plan on more seasons and replace the assumed loss and storage cost with measured values before investing.

## 9. References

1. Shelar, R., Hajare, A., and Mangarule, S. (2025). A Comprehensive Spatio-Temporal Dataset for Agricultural Price Forecasting: Integrated Market, Weather, and Event Features (2014–2024). Mendeley Data, version 1. doi:10.17632/ds9jmxp9zy.1.
2. Singla, S. (2020). Lasalgaon Onion Data, compiled from NHRDF. Mendeley Data, version 1. doi:10.17632/9dn4g8m97m.1.
3. ICAR. Onion cold storage: potential to stabilize price fluctuation. icar.org.in/en/node/4701.
