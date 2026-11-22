# Kanda Code: eight-state comparison

We compare how the same March forecast and storage rules perform across eight onion-producing states. The alternatives use the March price alone, pooled historical seasonality, recency-weighted seasonality, and three pooled regressions. The regressions add March arrivals and then March rainfall and temperature. This dataset has no onion-specific fertilizer or soil measurements.

Run from the repository root (Python 3.12):

```sh
python -m pip install -r requirements.txt
python -m regional.run
python -m unittest -v test_analysis regional.test_regional
```

The packaged monthly extract is sufficient. To rebuild it, download the version 1 Parquet from [Mendeley Data](https://doi.org/10.17632/ds9jmxp9zy.1), verify SHA-256 `392da11330e7d3166df07e7b4e154c64934bfd450221afa8b4024e2cf1124006`, and run:

```sh
python -m regional.run --parquet /path/to/onion.parquet
```

## Reading the outputs

- `coverage.csv`, `training_rows.csv`, and `seasonality.csv`: observed months, training samples by state and origin, and price indices from complete calendar years.
- `forecasts.csv` and `model_scores.csv`: forecasts for each March origin and scores on matching observed months. The 2022 validation error determines the common model; the 2023-24 test does not select it.
- `state_scores.csv` and `regional_scores.csv`: state and equal-state regional forecast errors.
- `sales_plans.csv`, `storage_results.csv`, and `regional_storage.csv`: plans, actual gains versus selling in April, and comparable regional averages. Blank gains mean at least one actual monthly price was unavailable. The common regional storage table uses 2024.

## Data

- State selection: 2023-24 production in thousand tonnes, [ICAR-IASRI Data Book 2025, table 4.12](https://www.iasri.res.in/uploads/IASRI%20Data%20Book%20-2025%20_low.pdf). We take the two highest reported state producers in each of the four [Ministry of Home Affairs zones](https://mha.gov.in/zonal-council). Central and Northeast zones are excluded.
- Price, arrivals and gridded weather: Shelar, Hajare and Mangarule (2025), [Agmarknet and IMD compilation, version 1](https://doi.org/10.17632/ds9jmxp9zy.1), CC BY 4.0. The included CSV is a filtered and aggregated derivative. Weather is the mean across trading-market days with weather observations, not a land-area-weighted state mean.
- Storage loss assumptions: [ICAR onion cold-storage trials](https://icar.org.in/en/node/4701). Storage cost, harvest date and handling limits are the same assumptions in every state.
