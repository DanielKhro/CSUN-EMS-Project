# Weather-Aware GRU Deployment 2

This is a compact, separate candidate runtime built from
`energy_weather_102126_3.csv`. The original `jetson_gru_deployment` folder is
unchanged.

## Validation summary

- The source CSV has 40,935 rows at a continuous 15-minute cadence, no blank
  values, and the required `active_power` and `dew_point` inputs.
- The replay and preparation scripts derive annual, daily, and weekly calendar
  features from each timestamp, matching the model's eight input features.
- The new CSV's power series is smoother than the previous CSV, but it has no
  `imputed` or `source_samples` provenance columns. This package therefore
  cannot distinguish measured readings from any values filled or smoothed by
  the CSV author.
- Dew-point values match the previous source CSV exactly and range down to
  approximately -44 C. Confirm the weather source and units before relying on
  the weather input operationally.
- The held-out split contains 6,141 samples from 2023-11-03 through 2024-01-06.
  This is not a summer holdout, so it does not establish hot-season
  generalization.
- Candidate held-out metrics: GRU MAE 37.98 W, RMSE 56.74 W, MAPE 29.01%;
  persistence MAE 34.83 W, RMSE 60.02 W, MAPE 22.58%. The candidate improves
  on RMSE but not MAE or MAPE versus persistence. It improves on the previous
  GRU checkpoint on this same CSV/test split, but is not a clear replacement
  for the persistence baseline.
- A full offline EMS replay completed for all 6,141 held-out rows. It produced
  no missing result values and no MQTT publishes. Offline replay does not
  verify the Raspberry Pi's relay behavior.

## Raspberry Pi runtime

Install the packages in `requirements.txt` and a PyTorch build compatible with
the Pi's OS, Python, architecture, and hardware. Copy this folder to the Pi;
there is no workstation virtual environment in this package. From this folder,
run an offline replay:

```bash
python3 run_gru_replay.py --start-date 2023-12-15 --max-steps 96
```

MQTT publishing is disabled unless `--publish` is supplied. This replay uses
historical CSV data and is not a live sensor-based forecast.

## Runtime files

- `run_gru_replay.py`: replay entry point
- `ems_realtime_jetson.py`: EMS decision logic
- `gru_model.py`: GRU architecture
- `prepare_gru_dataset.py`: shared CSV and feature preprocessing used by replay
- `energy_weather_102126_3.csv`: historical input data
- `trained_models/weather_load_gru.pt`: candidate checkpoint
- `requirements.txt`: non-PyTorch Python dependencies
