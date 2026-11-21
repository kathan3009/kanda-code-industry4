# Kanda Code

Kanda Code is our group project for Industry 4.0 (MS4001) at IIT Madras. We compare onion-price forecasts and sell-or-store plans in Maharashtra and Gujarat, and test the approach separately on historical Lasalgaon data. Using prices available through March, we plan sales from April to December. The plan accounts for storage costs, spoilage, capacity and the minimum sale at harvest.

## Run

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python analysis.py
python -m unittest
```

The two CSVs in `data/` are enough to run the analysis. To rebuild the Maharashtra and Gujarat extract, download the version 1 Parquet from the Agmarknet source below and run `python analysis.py --parquet /path/to/file.parquet`.

In the full repository, edit `report.md` and run `python make_pdf.py` to rebuild the PDF. The script requires `reportlab`, `pypdf`, and Times New Roman. On non-Mac systems, set `TNR_FONT_DIR` to the folder containing the regular and bold font files.

## Read the results

- `results/market_summary.csv`: seasonal price patterns and arrivals regressions.
- `results/forecast_scores.csv`: validation and test errors. The method is chosen on validation MAPE only.
- `results/sales_plan.csv`: monthly tonnes sold and held, by storage scenario.
- `results/storage_results.csv`: realised operating proceeds versus selling everything in April. This excludes capital costs.

We test the Maharashtra and Gujarat plans on 2023 and 2024 prices, and the Lasalgaon plan on 2017 and 2018 prices. We use the same storage and sales constraints to compare the plans. The project report explains the assumptions and results.

## Sources

- Shelar, R., Hajare, A., and Mangarule, S. (2025). [Agmarknet-based agricultural price forecasting dataset, version 1](https://doi.org/10.17632/ds9jmxp9zy.1), CC BY 4.0. The state CSV is a modified extract: filtered, deduplicated and aggregated by month.
- Singla, S. (2020). [Lasalgaon Onion Data, version 1](https://doi.org/10.17632/9dn4g8m97m.1), CC BY 4.0. Monthly prices and arrivals compiled from NHRDF.
