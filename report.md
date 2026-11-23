# When Should Onion Farmers Sell?
Price Forecasting and Sell-or-Store Planning

Kanda Code | MS4001 Industry 4.0 | IIT Madras BS

## 1. Problem statement

Rabi (winter-sown) onion is about 65% of India's crop and the part that is stored: it is harvested from late March to May, when prices are lowest, and held for the lean months after (NHB, 2018; Khapte et al., 2023). Maharashtra grows about 30% of India's onions (NHB, 2018), mainly in Nashik, Ahilyanagar (formerly Ahmednagar), Pune and Solapur. We ask how much a farmer group with 1,000 tonnes harvested in mid-April should sell at the mandi (regulated wholesale market) in each month from April to December, and what it takes for waiting to pay.

## 2. Motivation for problem selection

Farmers at Lasalgaon, India's largest onion market, sell about 40% of their produce at a loss (Vivek and Mohammed, 2023), and in March 2026 Maharashtra mandi prices fell to Rs 300-800 per quintal (100 kg) against a production cost of about Rs 1,800 (Shagun, 2026). Lack of storage forces sales at harvest, when prices are lowest (Khapte et al., 2023). In our data the April price averaged Rs 745 per quintal over 2011-2025 and November Rs 2,138, but the November-to-April ratio ranged from 5.7 (2023) to 1.1 (2025). The four districts carried 84% of Maharashtra's reported onion arrivals in 2024 (DMI, 2026).

## 3. Research questions

- **RQ1.** Can a seasonal model forecast April-December prices better than assuming the price stays where it is?
- **RQ2.** Does storing part of the harvest and selling it later earn more than selling everything in April?
- **RQ3.** Does a price forecast lead to better selling decisions than the pattern of past seasons?

## 4. Hypotheses, objectives and constraints

- **H1.** Winters' seasonal model makes smaller forecast errors than the no-change forecast.
- **H2.** Storing and selling later earns more per tonne than selling at harvest, after all storage and selling costs.
- **H3.** A sales plan built on the forecast earns more than one built on past seasons' average prices.

The objective is the present value at harvest (10% a year) of sales net of 1% market charges, Rs 500 per tonne for transport, loading and weighing, and a 1% price discount per month in store, minus storage cost; the decisions are tonnes sold and held each month. The store holds 700 t, so at least 300 t is sold at harvest (more than the 250 t needed for cash); nothing leaves it until curing ends 15 days after harvest; at most 300 t is sold a month after April; and the store must be empty at its holding limit: six months for a chawl or the improved store (end of October), eight for the cold store.

## 5. Exploratory data analysis

**Data.** Agmarknet monthly modal (most common) price in Rs per quintal and arrivals in tonnes, January 2011 to December 2025 (DMI, 2026). In each district we use the mandi with the most arrivals among those that miss at most 5% of months with no gap over three months: Pimpalgaon Baswant (Nashik), Newasa-Ghodegaon (Ahilyanagar), Solapur and Pune. 2011 is the earliest start at which all four qualify. Only 19 of 720 mandi-months are unreported, including the April-May 2020 COVID-19 lockdown.

![](results/seasonal_pattern.png)

*Figure 1. Mean monthly price relative to the year's mean (left) and share of the year's arrivals (right), 2011-2025; April shaded.*

The price cycle is shared (Figure 1): April prices are 0.53-0.58 times the annual mean and November is the peak at all four mandis (1.35-1.51), while arrivals peak in May at Pimpalgaon, February at Pune, July at Newasa and December at Solapur, so the districts differ in crop calendar, not price pattern. Regressing log price on log arrivals, month dummies and a trend gives -0.23 at Pimpalgaon, -0.18 at Pune, -0.15 at Newasa and +0.06 at Solapur: months with 10% more arrivals had 1.5-2.3% lower prices at three mandis. With autocorrelated residuals (lag-1 about 0.8) this is an association, not a causal price effect. We assume the group is a price taker, given its small share of arrivals: 300 t is about 1% of a month's August-October arrivals. Augmented Dickey-Fuller tests reject a unit root (random walk) in the 12-month change in log price at all four mandis (p ≤ 0.007) but not always in log price (Solapur p = 0.08), so ARIMA models the year-on-year change.

## 6. Methodology

*Table 1. Where each model is used and why.*

| Step: model or algorithm | Why this choice |
| --- | --- |
| Fill missing months: lasso on nearby mandis | Uses what similar mandis were paid; keeps the useful ones |
| RQ1: no change, past seasons, Winters, ARIMA | Two benchmarks, the yearly cycle, the standard model |
| RQ2: dynamic programming (Bellman equation) | The best monthly plan under storage loss, costs and limits |
| RQ3: same plan fed forecast or past prices | Isolates what the forecast adds to the seasonal calendar |

**Filling missing months.** The 33 mandis of the four districts that report at least 80% of months move together, so a missing month is predicted from the others' log prices that month by a lasso regression (Tibshirani, 1996), whose cross-validated penalty drops unhelpful mandis. It uses only data up to the forecast date, and filled months are never scored as forecast errors. On 240 runs of one to three known months hidden at random it missed by 8.7%, against 10.6% for ordinary regression on the other three study mandis and 18.6% for log interpolation.

**RQ1.** At the end of March and of each later month, each model forecasts every month to December from prices up to that date, refitted each time. *No change* carries the last price forward; the *past-seasons average* is the mean price of that month in earlier years; *Winters' exponential smoothing* (Winters, 1960) updates a level, a trend and 12 monthly factors on log prices; *ARIMA* (Box and Jenkins, 1976) models the 12-month change in log price, and the best order that converged at every date, (0,1,0), is a seasonal random walk: last year's price for the month times the latest 12-month change. Seasons 2011-2013 are history, 2014-2019 validate and 2020-2025 test; the plans use the model with the lowest validation error. Relative MAE is the mean absolute error on reported months divided by the mean price. As the mandis' prices move together (correlation ≥ 0.90), t-tests treat seasons as the independent units.

**RQ2 and RQ3.** A finite-horizon dynamic programme (Bellman, 1957): month *t* runs from April (0) to December (8), the state *s* is the stock in store and the action *x* is tonnes sold. With net price *p*, monthly loss *l*, storage cost *c* and monthly discount factor λ, the value of holding *s* tonnes at the start of month *t* is

$$ V_{t}(s) = max_{x} { λ^{t} [ p_{t} x − c (s − x) ] + V_{t+1}( (1 − l)(s − x) ) }

with no stock after the holding limit; backward induction over every whole-tonne stock level gives the best plan (a linear programme would give the same). Winters and ARIMA forecast log prices, so their forecasts are medians; as the plan needs expected prices, each is multiplied by exp(σ^{2}_{h}/2), σ^{2}_{h} being the mean squared *h*-month log error in the other validation seasons (for Winters 1.04 at one month, 1.29 at six). The stores: a *ventilated chawl* rented at Rs 140 per quintal a season, which lost 54.9% in 120 days in an ICAR-DOGR trial, a worst case beside the usual 30-40% (ICAR, n.d.); an *improved on-farm store* costing Rs 167 per quintal to build, charged over a season, whose developers report 8-10% loss (we use 10% over six months; Khapte et al., 2023); and ICAR-DOGR's *cold store*, held at 27 °C, which lost 7.1% in 120 days (ICAR, n.d.), at an assumed Rs 700 per tonne-month. Plans are valued at actual prices against an April sale. A *March plan* is fixed from the March forecast, a *monthly re-plan* re-solves with each new forecast, a *past-seasons plan* uses the past-seasons average and *perfect foresight* the actual prices.

## 7. Results

*Table 2. Relative MAE of each forecast, averaged over the four mandis: all forecast dates, and the end-March forecast alone.*

| Forecast model | Validation, all | Test, all | Validation, March | Test, March |
| --- | ---: | ---: | ---: | ---: |
| No change | 48.2% | 40.6% | 54.2% | 43.6% |
| Past-seasons average | 50.7% | 35.7% | 47.2% | 35.1% |
| Winters | 44.1% | 34.0% | 45.8% | 47.2% |
| ARIMA (0,1,0) | 66.6% | 55.9% | 68.0% | 83.5% |

**RQ1: H1 not supported.** Winters had the lowest validation error, so it drives the plans, and the lowest test error over all dates (34.0%, a typical miss of Rs 658 per quintal), but season by season its gap to no change is not significant (p = 0.93 in testing, 0.77 over twelve seasons), and from March both simple benchmarks did better in testing. ARIMA, which carries last year's movement into this year, was worst.

**RQ2: H2 supported on average for low-loss stores; the test seasons alone are inconclusive.** An April sale netted Rs 8,497 per tonne in the test seasons 2020-2025. The improved store's March plan gained Rs 4,116 per tonne (48%) and the cold store Rs 3,236. The improved-store gain was positive in 5 of 6 test seasons and 19 of 24 test market-seasons, but six seasons do not establish it at 5% (p = 0.08); counting the validation seasons, it was positive in 10 of 12 (p = 0.01). In 2025 all four districts lost (Rs 1,790 per tonne on average), as prices rose only 4-18% from April to August-October. The plans sold 300 t at harvest, then about 125 t in August, 235 t in September and 280 t in October, as the six-month limit empties the store before the November peak. With a chawl even perfect foresight gains only Rs 465 per tonne, and the forecast plan, storing in 16 of 24 market-seasons on expected prices that allow for a spike, lost Rs 1,702. Storing stops paying once a store loses about a third of its weight in four months (9.3% a month), the loss ICAR calls usual.

*Table 3. Gain over selling everything in April (Rs per tonne harvested), improved store unless noted, test seasons.*

| Mandi | March plan | Monthly re-plan | Past seasons | Perfect foresight | Cold store, March plan |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pimpalgaon Baswant (Nashik) | 5,422 | 5,422 | 5,959 | 6,799 | 4,920 |
| Newasa (Ahilyanagar) | 4,586 | 5,567 | 4,586 | 6,418 | 4,819 |
| Solapur | 3,241 | 3,241 | 2,692 | 4,494 | 871 |
| Pune | 3,215 | 3,212 | 2,535 | 4,482 | 2,333 |
| Four districts | 4,116 | 4,360 | 3,943 | 5,548 | 3,236 |

The improved-store gain falls to Rs 2,954 if storage cost doubles, 2,815 if loss doubles, 3,233 with a 2% monthly quality discount, 3,066 if half the harvest is sold for cash and 3,477 at 20% interest, and rises to 5,521 if the store holds a seventh month. Without the three market-seasons valued at filled prices it is Rs 4,237.

**RQ3: H3 not supported.** The forecast plan beat the past-seasons plan by Rs 173 per tonne in testing, but in only 4 of 6 seasons (p = 0.40). Monthly re-planning changed little, and ARIMA's plan, best in testing (Rs 4,503), trailed in validation (Rs 3,005 vs 4,552): the value is in seasonal timing, which past seasons reveal.

## 8. Managerial implications

**When to sell.** With an improved on-farm store, sell 300 t at harvest and the rest from August to October by the past-seasons calendar. With a chawl losing a third of its weight in four months, sell at harvest whatever the forecast says.

**What to invest in.** The improved store beat the cold store by Rs 500-2,400 per tonne in three districts but not at Newasa; the cold store would match it at a rent below Rs 555 per tonne-month. Even with its whole Rs 11.7 lakh (1 lakh = 100,000) build cost for 700 t charged to one season, the improved store would have gained about Rs 39 lakh on 1,000 t in an average test season; this is a modelled average, and in a year like 2025 storing lost money. Weighing stock or temperature and humidity sensors would track actual loss, which decides whether storing pays.

**Risk and limits.** Storing lost money in 2025, so the harvest sale should leave cash to carry such a year. Policy acts in the selling window: in 2023-24 a 40% export duty, an export ban from December and a 5 lakh t buffer stock bought by NAFED and NCCF (PIB, 2024). One group is a small share of arrivals, but many groups selling on one calendar could move prices. Modal prices mix grades and, from October, fresh kharif onion; costs and the cold-store rent are assumptions.

## 9. References

- Bellman, R. (1957). Dynamic Programming. Princeton University Press.
- Box, G. E. P., Jenkins, G. M. (1976). Time Series Analysis: Forecasting and Control. Holden-Day.
- DMI, Directorate of Marketing and Inspection (2026). Agmarknet 2.0, monthly onion prices and arrivals. agmarknet.gov.in.
- ICAR (n.d.). Onion cold storage: potential to stabilize price fluctuation. icar.org.in/en/node/4701.
- Khapte, P. S. et al. (2023). An innovative onion storage structure. Indian Horticulture 68(3), 39-41.
- NHB, National Horticulture Board (2018). Onion: monthly report, June 2018. nhb.gov.in.
- PIB (2024, 26 March). Government has directed NCCF and NAFED to initiate procurement of 5 lakh tonnes of onion for the buffer requirement. Press Information Bureau.
- Shagun (2026, 31 March). War in West Asia and protectionist steps by Bangladesh disrupt onion exports, lead to price crash. Down To Earth.
- Tibshirani, R. (1996). Regression shrinkage and selection via the lasso. J. R. Stat. Soc. B 58(1), 267-288.
- Vivek, T. R., Mohammed, F. (2023, 8 April). Onions in India a political nightmare. Govt only has band-aid solutions for policy failures. ThePrint.
- Winters, P. R. (1960). Forecasting sales by exponentially weighted moving averages. Manage. Sci. 6(3), 324-342.
