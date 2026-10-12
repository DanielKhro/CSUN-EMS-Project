# Weather-Aware GRU Jetson Deployment

This folder contains the weather-aware GRU, its EMS replay controller, trained
checkpoint, source CSV, and prepared sequences for evaluation or retraining.
Copy the entire `jetson_gru_deployment` folder to the Jetson Nano.

## Runtime requirements

- Python 3
- NumPy, pandas, and paho-mqtt (`python3 -m pip install -r requirements.txt`)
- PyTorch installed using the NVIDIA-compatible instructions for the Jetson's
  JetPack release. Install the Jetson-compatible PyTorch build separately;
  a generic desktop PyTorch wheel may not work on the Nano.

## Run a local simulation for today's month/day

From this folder:

```bash
python3 run_gru_replay.py --today --max-steps 96
```

This runs the selected historical CSV day through the EMS as fast as possible
without publishing MQTT commands. `--today` matches the Jetson's current
month/day to the most recent matching date in the CSV, even if the year differs.
The source CSV covers 2022-11-05 through 2024-01-06; it cannot provide data for
a month/day that is absent from that range. Replay results are written under
`trained_models/`.

## Pace the historical replay at 15-minute intervals

```bash
python3 run_gru_replay.py --today --max-steps 96 --live
```

This is paced historical playback, not a live sensor feed. The GRU uses active
power and dew point from the selected CSV date, while the EMS simulates its
battery state and assumes the grid is available.

## Optional MQTT publishing

Only use this when the Jetson can reach the broker and the Raspberry Pi
subscriber is ready for historical replay decisions:

```bash
python3 run_gru_replay.py --today --max-steps 96 --live --publish --mqtt-broker BROKER_IP
```

The default MQTT topic is `relay___mode/mode_select`. Use `--mqtt-topic` if the
subscriber uses another topic. Publishing requires `--live`, either `--today`
or `--start-date`, and a finite `--max-steps` to prevent an unpaced or
unbounded command replay.

## Included files

- `run_gru_replay.py`: GRU-to-EMS replay and optional MQTT publishing
- `ems_realtime_jetson.py`: EMS decision logic
- `gru_model.py`: GRU architecture
- `prepare_gru_dataset.py`, `train_gru.py`, `evaluate_gru.py`: data preparation,
  training, and evaluation tools
- `energy_weather_101026.csv`: weather and active-power history used by replay
- `trained_models/weather_load_gru.pt`: trained weather-aware GRU checkpoint
- `gru_dataset_weather/`: prepared sequences and metadata for evaluation or
  retraining
