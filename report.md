# When Should Onion Farmers Sell?
Price Forecasting and Sell-or-Store Planning

Kanda Code | MS4001 Industry 4.0 | IIT Madras BS

## 1. Problem statement

An onion growers' cooperative can sell at harvest or hold some stock for later months. A higher price later in the year does not automatically make storage worthwhile: onions are lost and lose quality in store, storage costs money, every sale pays transport and market fees, the cooperative needs cash at harvest, and only a limited quantity can be moved each month. We forecast monthly prices at the largest onion mandi in each state with complete records, then plan monthly sales for a cooperative with 1,000 tonnes harvested in mid-April.

## 2. Motivation for problem selection

The harvest price is often low, but a decision to wait has to be made before the later prices are known. A useful plan has to answer both questions: what are prices likely to do, and will the increase cover the loss, discount and cost of holding stock? The Mendeley extract we started with gives state averages for 2014-2024 only, with no mandi-level arrivals, so we rebuilt the data from the official market records.

## 3. Research questions

1. Are higher mandi arrivals associated with lower monthly prices?
2. Do seasonal, arrivals and weather signals forecast April to December prices better than the last price or the same month last year?
3. Do forecast-based sales plans beat selling the full harvest in April after storage loss, quality loss, storage cost, selling costs and cash needs?

## 4. Hypotheses, objectives and constraints

We expect higher arrivals to lower prices, and low-loss cold storage to make waiting worthwhile. The objective is sales revenue after market fees, transport and quality discount, minus storage cost. The decision variables are tonnes sold and tonnes held each month. The cooperative must sell at least 250 tonnes at harvest for cash, can store up to 700 tonnes, cannot sell from store until curing ends 15 days after harvest, and can move at most 300 tonnes a month. Stock must be cleared by December and within the store's maximum duration.

## 5. Exploratory data analysis

Agmarknet 2.0 publishes monthly modal prices (Rs per quintal) and arrivals (tonnes) for every mandi. NASA POWER gives daily rainfall and temperature at each mandi, which we total or average by month. Every market uses one timeline: January 2008 to December 2025. To be scored on the same seasons, a mandi must report every month from January 2013. Gaps of one or two months are interpolated in logs and never scored; longer gaps stop the run. For each state we screened the three districts with the most 2024 arrivals and chose the mandi with the most arrivals in 2013-2025 among those meeting this rule.

Four states have a qualifying mandi: Solapur (Maharashtra), Bara Bazar Kolkata (West Bengal), Hubballi (Karnataka) and Gurgaon (Haryana). We add Lasalgaon as the national benchmark. Gujarat, Madhya Pradesh, Rajasthan, Andhra Pradesh and Bihar had no mandi meeting the rule; the closest, Gondal, missed three months in 2022. Only 12 of 780 market-months since 2013 are interpolated. Lasalgaon matches the independent NHRDF archive closely: over 138 shared months the correlation is 0.987 and the median gap 2.3%.

April prices average 0.54-0.70 times the year's mean, and prices peak in October to December at 1.32-1.45 times the mean. March to May brings 19-25% of the year's arrivals.

<!-- pagebreak -->

## 6. Methodology

**Arrivals regression.** For each market we regress log monthly price on log arrivals with calendar-month and year effects over 2013-2025. Newey-West standard errors allow for short-run serial correlation. The coefficient measures association only.

**Forecasting.** Forecasts are made at the end of March for April to December, and again at the end of each later month for the rest of the season. The last price and the same month last year are the baselines. The seasonal profile multiplies the last price by the median ratio between the target and origin months in earlier seasons. Two pooled ridge regressions adjust that profile using price, arrivals and five-market arrivals relative to the same months of the previous three years; the second also adds rainfall and maximum temperature. Each regression is refitted every season on earlier seasons only. Models are compared on 2014-2019 and tested on 2020-2025. Because the cooperative needs a sell-or-store decision, we choose the model whose sales plans earned most in the validation seasons, not the one with the lowest error.

**Sales plan.** A linear programme chooses monthly sales and closing stocks. April sales plus April stock equal the harvest. In each later month, sales plus stock equal the previous stock after spoilage. The net price deducts 1% market fees, Rs 500 per tonne for transport and handling, and a 1% discount for each month in store. Cold storage loses 1.83% a month, costs Rs 700 per tonne-month and holds stock up to eight months. Ventilated storage loses 18.05% a month, costs Rs 250 and holds up to six months; both losses come from ICAR 120-day trials. The March plan fixes all sales from the March forecast. The monthly re-plan reruns the programme each month with the latest forecast and carries out only the next month's sales. Each plan is valued at the prices that actually occurred, against selling everything at harvest. Perfect foresight shows the most storage could have earned.

## 7. Results

| Forecast model | Validation MAPE | Test MAPE | March test MAPE | Validation plan gain |
| --- | ---: | ---: | ---: | ---: |
| Last price | 35.0% | 33.5% | 38.6% | Rs 0/t |
| Same month last year | 89.4% | 52.6% | 47.9% | Rs -93/t |
| Seasonal profile | 44.3% | 37.1% | 52.8% | Rs 835/t |
| + market signals | 51.6% | 36.3% | 44.4% | Rs 821/t |
| + market signals + weather | 55.2% | 38.5% | 46.5% | Rs 676/t |

MAPE covers forecasts from every origin, averaged over markets; plan gain averages both storage types and both plans. The last price has the lowest percentage error, but it never predicts a rise, so its plans always sell at harvest. The seasonal profile was selected. Weather raised errors and lowered plan gains.

Higher arrivals were associated with lower prices in Kolkata (coefficient -0.341, p = 0.006) and Lasalgaon (-0.168, p = 0.002), weakly in Hubballi (-0.148, p = 0.066), and not clearly in Solapur (-0.098, p = 0.120) or Gurgaon (-0.021, p = 0.755).

<!-- pagebreak -->

## 7. Results (continued)

| Cold storage, 2020-2025 | March plan | Monthly re-plan | Perfect foresight |
| --- | ---: | ---: | ---: |
| Lasalgaon (benchmark) | Rs 3,787/t | Rs 4,533/t | Rs 7,251/t |
| Kolkata | Rs 4,696/t | Rs 4,147/t | Rs 7,652/t |
| Solapur | Rs 1,057/t | Rs 1,545/t | Rs 4,634/t |
| Gurgaon | Rs -165/t | Rs 154/t | Rs 2,848/t |
| Hubballi | Rs -833/t | Rs -1,554/t | Rs 1,969/t |
| All five markets | Rs 1,708/t | Rs 1,765/t | Rs 4,871/t |

Gains are per tonne harvested above selling everything at harvest, which nets Rs 10,410/t on average, and exclude capital costs. The monthly re-plan gained in 19 of 30 market-seasons. It earned Rs 5,647/t in 2023 and Rs 6,643/t in 2024, but lost Rs 3,277/t in 2025, when November prices fell below April's. Ventilated storage lost money with forecast plans (Rs -246/t re-planned) because a fifth of the stock is lost each month.

| Monthly re-plan, cold storage | Mean gain above harvest sale |
| --- | ---: |
| Base assumptions | Rs 1,765/t harvested |
| Storage loss 5% a month | Rs -49/t harvested |
| Storage cost doubled | Rs -1,078/t harvested |
| Quality discount 2% a month | Rs 716/t harvested |
| Selling costs doubled | Rs 1,622/t harvested |
| Half the harvest sold for cash | Rs 1,164/t harvested |
| Curing takes 45 days | Rs 1,765/t harvested |

## 8. Managerial implications

Sell enough at harvest to meet cash needs, store the rest only in low-loss cold storage, and expect to release it mainly from August to November; the re-planned sales put 37% of the harvest on the market in April and 53% in those four months. Storage pays only while loss stays near 2% a month and the storage charge near Rs 700 per tonne-month, so measure both before committing. The result depends on the market: Lasalgaon and Kolkata gained most, while Hubballi, a kharif market with peak arrivals in October, lost money.

The plans use monthly modal prices for all varieties and grades together; grade-level Agmarknet data begin only in November 2025, so quality is a fixed discount. Fees, transport, storage cost and duration are assumptions, five states lacked complete records, and large sales could move the price.

## 9. References

1. Directorate of Marketing and Inspection. Agmarknet 2.0, monthly onion prices and arrivals by market. agmarknet.gov.in.
2. NASA Langley Research Center. POWER daily API, rainfall and temperature, 2008-2025. power.larc.nasa.gov.
3. Singla, S. (2020). Lasalgaon Onion Data, compiled from NHRDF. Mendeley Data, version 1. doi:10.17632/9dn4g8m97m.1.
4. ICAR. Onion cold storage: potential to stabilize price fluctuation. icar.org.in/en/node/4701.
5. Shelar, R., Hajare, A., and Mangarule, S. (2025). A Comprehensive Spatio-Temporal Dataset for Agricultural Price Forecasting: Integrated Market, Weather, and Event Features (2014–2024). Mendeley Data, version 1. doi:10.17632/ds9jmxp9zy.1.
