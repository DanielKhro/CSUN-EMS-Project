"""Replay the weather-aware GRU through the EMS controller.

Example:
    python run_gru_replay.py --start-date 2023-12-15 --max-steps 96
    python run_gru_replay.py --start-date 2023-12-15 --max-steps 96 --live --publish
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt
import torch

from ems_realtime_jetson import EMSController
from gru_model import LoadGRU
from prepare_gru_dataset import (
    CALENDAR_FEATURES,
    DEFAULT_MAX_INTERPOLATE_STEPS,
    WEATHER_FEATURES,
    load_csv_files,
    regularize_and_interpolate,
    validate_cadence,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "energy_weather_102126_3.csv"
DEFAULT_MODEL = SCRIPT_DIR / "trained_models" / "weather_load_gru.pt"
DEFAULT_OUTPUT = SCRIPT_DIR / "trained_models" / "weather_ems_replay.csv"
TEST_START_FRACTION = 0.85


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--start-date",
        help="Start replay at the first available row of this date (YYYY-MM-DD). "
        "Cannot be combined with --today. Defaults to the final 15%% of the CSV "
        "for a held-out replay.",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Start on the most recent CSV date matching the Jetson's current "
        "month and day, regardless of year.",
    )
    parser.add_argument(
        "--match-current-time",
        action="store_true",
        help="With --today, start at the next available 15-minute CSV interval "
        "matching the Jetson's current local time, then replay to that CSV day's end.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Limit replay length for a quick demonstration.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Play historical CSV rows at the configured interval instead of running as fast as possible.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=900.0,
        help="Delay between live-mode predictions. Default: 900 seconds (15 minutes).",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish mode commands to the Raspberry Pi MQTT broker.",
    )
    parser.add_argument(
        "--mqtt-broker",
        default="127.0.0.1",
        help="Raspberry Pi MQTT broker address.",
    )
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument(
        "--mqtt-topic",
        default="prediction/mode_select",
        help="MQTT topic consumed by the Raspberry Pi relay controller.",
    )
    return parser.parse_args()


def load_data(csv_path: Path, feature_columns: list[str], lookback_steps: int) -> pd.DataFrame:
    if "active_power" not in feature_columns:
        raise ValueError("The trained model must use active_power as an input feature.")

    supported_features = set(WEATHER_FEATURES + CALENDAR_FEATURES)
    unsupported = sorted(set(feature_columns).difference(supported_features))
    if unsupported:
        raise ValueError(f"The replay cannot generate model features: {unsupported}")
    measured_columns = [
        column for column in WEATHER_FEATURES if column in feature_columns
    ]
    data = load_csv_files(
        [csv_path], measured_columns, preserve_missing=True
    )
    data, _, interpolated_rows, unfilled_gap_rows = regularize_and_interpolate(
        data, measured_columns, DEFAULT_MAX_INTERPOLATE_STEPS
    )
    validate_cadence(data)
    print(
        f"CSV gap handling: interpolated {interpolated_rows} short-gap rows; "
        f"{unfilled_gap_rows} unfilled gap rows remain unavailable."
    )
    if len(data) < lookback_steps + 1:
        raise ValueError(
            f"CSV must contain at least {lookback_steps + 1} rows for this model."
        )
    return data[["timestamp", *feature_columns]]


def find_latest_month_day(data: pd.DataFrame, current_date: pd.Timestamp) -> tuple[int, pd.Timestamp]:
    timestamps = data["timestamp"]
    matching_rows = timestamps.dt.month.eq(current_date.month) & timestamps.dt.day.eq(
        current_date.day
    )
    if not matching_rows.any():
        raise ValueError(
            f"No CSV rows match today's month/day ({current_date.strftime('%m-%d')})."
        )

    matching_dates = timestamps.loc[matching_rows].dt.normalize()
    selected_date = matching_dates.max()
    selected_rows = np.flatnonzero(
        matching_rows.to_numpy() & timestamps.dt.normalize().eq(selected_date).to_numpy()
    )
    return int(selected_rows[0]), selected_date


def find_current_time_row(
    data: pd.DataFrame,
    current_time: pd.Timestamp,
) -> tuple[int, pd.Timestamp, float]:
    day_start_index, selected_date = find_latest_month_day(data, current_time)
    current_seconds = (
        current_time.hour * 3600
        + current_time.minute * 60
        + current_time.second
        + current_time.microsecond / 1_000_000
    )
    interval_seconds = 15 * 60
    intervals_from_midnight = int(np.ceil(current_seconds / interval_seconds))
    target_timestamp = selected_date + pd.Timedelta(
        seconds=intervals_from_midnight * interval_seconds
    )

    timestamps = data["timestamp"]
    target_index = int(timestamps.searchsorted(target_timestamp, side="left"))
    if target_index >= len(data):
        raise ValueError(
            f"No CSV sample is available at or after {target_timestamp}."
        )
    if target_index < day_start_index:
        raise RuntimeError("Resolved replay time precedes the selected CSV date.")

    next_wall_clock_interval = current_time.normalize() + pd.Timedelta(
        seconds=intervals_from_midnight * interval_seconds
    )
    wait_seconds = max(
        0.0, (next_wall_clock_interval - current_time).total_seconds()
    )
    return target_index, timestamps.iloc[target_index], wait_seconds


def load_model(model_path: Path) -> tuple[LoadGRU, dict]:
    if not model_path.exists():
        raise FileNotFoundError(f"Model file does not exist: {model_path}")

    try:
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    except TypeError:
        # Older Jetson PyTorch releases do not support weights_only.
        checkpoint = torch.load(model_path, map_location="cpu")
    feature_columns = checkpoint.get("feature_columns")
    if not isinstance(feature_columns, list) or not feature_columns:
        raise ValueError("The model checkpoint is missing a valid feature_columns list.")
    if int(checkpoint["input_size"]) != len(feature_columns):
        raise ValueError("Model input_size does not match checkpoint feature_columns.")
    if int(checkpoint["lookback_steps"]) < 1:
        raise ValueError("Model lookback_steps must be positive.")

    model = LoadGRU(
        input_size=int(checkpoint["input_size"]),
        hidden_size=int(checkpoint["hidden_size"]),
        num_layers=int(checkpoint["num_layers"]),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model, checkpoint


def predict_next_watts(
    model: LoadGRU,
    history_features: np.ndarray,
    checkpoint: dict,
) -> float:
    feature_mean = np.asarray(checkpoint["feature_mean"], dtype=np.float32)
    feature_scale = np.asarray(checkpoint["feature_scale"], dtype=np.float32)
    target_mean = float(checkpoint["target_mean"])
    target_scale = float(checkpoint["target_scale"])

    if history_features.shape[1] != len(feature_mean) or len(feature_scale) != len(feature_mean):
        raise ValueError("Input feature shape does not match the model checkpoint.")
    normalized_history = (history_features - feature_mean) / feature_scale
    model_input = torch.from_numpy(normalized_history.astype(np.float32)).unsqueeze(0)
    with torch.no_grad():
        normalized_prediction = float(model(model_input).item())
    return max(0.0, normalized_prediction * target_scale + target_mean)


def mode_to_numeric(mode: str) -> int:
    if mode == "DISCHARGE":
        return 1
    if mode in {"GRID", "CHARGE"}:
        return 2
    return 0


def connect_mqtt(args: argparse.Namespace) -> mqtt.Client | None:
    if not args.publish:
        return None
    if args.mqtt_port < 1 or args.mqtt_port > 65535:
        raise ValueError("--mqtt-port must be between 1 and 65535.")

    client = mqtt.Client(client_id="jetson_weather_gru_ems")
    client.connect(args.mqtt_broker, args.mqtt_port, keepalive=60)
    client.loop_start()
    print(f"MQTT publishing enabled: {args.mqtt_broker}:{args.mqtt_port}")
    print(f"MQTT topic: {args.mqtt_topic}")
    return client


def publish_mode(client: mqtt.Client | None, topic: str, mode: str) -> int:
    mode_numeric = mode_to_numeric(mode)
    if client is None:
        return mode_numeric

    payload = json.dumps({"mode": mode_numeric})
    info = client.publish(topic, payload, qos=1, retain=False)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"MQTT publish failed with return code {info.rc}.")
    try:
        info.wait_for_publish(timeout=5.0)
    except RuntimeError as error:
        if not info.is_published():
            raise RuntimeError(
                "MQTT publish was not acknowledged within 5 seconds."
            ) from error
        raise
    if not info.is_published():
        raise RuntimeError("MQTT publish was not acknowledged within 5 seconds.")
    print(f"Published to Pi: {payload}")
    return mode_numeric


def main() -> None:
    args = parse_args()
    if args.max_steps is not None and args.max_steps < 1:
        raise ValueError("--max-steps must be positive when provided.")
    if args.interval_seconds <= 0:
        raise ValueError("--interval-seconds must be positive.")
    if args.today and args.start_date:
        raise ValueError("--today cannot be combined with --start-date.")
    if args.match_current_time and not args.today:
        raise ValueError("--match-current-time requires --today.")
    if args.publish:
        if not args.live:
            raise ValueError("--publish requires --live to prevent commands being sent as a burst.")
        if not (args.start_date or args.today) or args.max_steps is None:
            raise ValueError(
                "--publish also requires --start-date or --today and --max-steps to "
                "bound commands sent to the Raspberry Pi."
            )

    model, checkpoint = load_model(args.model_path)
    feature_columns = checkpoint["feature_columns"]
    lookback_steps = int(checkpoint["lookback_steps"])
    data = load_data(args.csv, feature_columns, lookback_steps)
    initial_wait_seconds = 0.0
    replay_day_end = len(data)
    if args.today:
        current_date = pd.Timestamp.now().normalize()
        if args.match_current_time:
            current_time = pd.Timestamp.now()
            replay_start, selected_timestamp, initial_wait_seconds = (
                find_current_time_row(data, current_time)
            )
            selected_date = selected_timestamp.normalize()
            replay_day_end = int(
                data["timestamp"].dt.normalize().searchsorted(
                    selected_date, side="right"
                )
            )
            replay_description = (
                f"today's month/day and current time, using CSV timestamp "
                f"{selected_timestamp}"
            )
        else:
            replay_start, selected_date = find_latest_month_day(data, current_date)
            replay_description = (
                f"today's month/day ({current_date.strftime('%m-%d')}), "
                f"using CSV date {selected_date.date()}"
            )
        if replay_start == 0:
            raise ValueError(
                f"The CSV date {selected_date.date()} has no prior observations "
                "to provide model history."
            )
    elif args.start_date:
        try:
            start_date = pd.Timestamp(args.start_date).date()
        except (TypeError, ValueError) as error:
            raise ValueError("--start-date must be a valid YYYY-MM-DD date.") from error
        matching_indexes = np.flatnonzero(data["timestamp"].dt.date.to_numpy() == start_date)
        if matching_indexes.size == 0:
            raise ValueError(f"No valid observations found for {start_date} in {args.csv}.")
        replay_start = int(matching_indexes[0])
        if replay_start == 0:
            raise ValueError(
                f"{start_date} has no prior observations to provide model history."
            )
        replay_description = f"starting {start_date}"
    else:
        replay_start = max(lookback_steps, int(len(data) * TEST_START_FRACTION))
        replay_description = "final 15% held-out period"

    end = len(data)
    if args.match_current_time:
        end = min(end, replay_day_end)
    if args.max_steps is not None:
        end = min(end, replay_start + args.max_steps)
    if end <= replay_start:
        raise ValueError("The selected replay range contains no rows.")

    feature_values = data[feature_columns].to_numpy(dtype=np.float32)
    target_values = data["active_power"].to_numpy(dtype=np.float32)
    for target_index in range(replay_start, end):
        history = feature_values[target_index - lookback_steps : target_index]
        if (
            not np.isfinite(history).all()
            or not np.isfinite(target_values[target_index])
        ):
            raise ValueError(
                "The selected replay range crosses an unfilled data gap near "
                f"{data['timestamp'].iloc[target_index]}. Choose a range with "
                "complete lookback and target data."
            )

    mqtt_client = connect_mqtt(args)
    ems = EMSController(dtHours=0.25)
    results = []
    if args.live:
        print("Live-mode dataset stream.")
        print(f"Prediction interval: {args.interval_seconds:g} seconds")
    else:
        print("Offline GRU/EMS replay.")
    if not args.publish:
        print("MQTT publishing is disabled. Use --publish only after the Pi subscriber is ready.")
    print(f"CSV: {args.csv.resolve()}")
    print(f"Model: {args.model_path.resolve()}")
    print(f"Replay range: {replay_description}")
    print(f"Replay rows: {end - replay_start}")
    print(
        "Replay timestamps: "
        f"{data['timestamp'].iloc[replay_start]} -> {data['timestamp'].iloc[end - 1]}"
    )
    if args.publish:
        print(
            "WARNING: MQTT publishing is enabled; these historical replay decisions "
            "will be sent to the Raspberry Pi."
        )
    print()

    try:
        if args.live and initial_wait_seconds > 0:
            print(
                f"Waiting {initial_wait_seconds:.1f} seconds for the next "
                "15-minute boundary before the first decision...",
                flush=True,
            )
            time.sleep(initial_wait_seconds)
        for target_index in range(replay_start, end):
            history = data.iloc[
                target_index - lookback_steps : target_index
            ][feature_columns].to_numpy(dtype=np.float32)
            actual_watts = float(data["active_power"].iloc[target_index])
            timestamp = data["timestamp"].iloc[target_index].to_pydatetime()
            predicted_watts = predict_next_watts(model, history, checkpoint)
            error_watts = predicted_watts - actual_watts

            decision = ems.step(
                now=timestamp,
                load_kW=predicted_watts / 1000.0,
                grid_ok=1,
            )
            mode_numeric = publish_mode(mqtt_client, args.mqtt_topic, decision["mode"])
            results.append(
                {
                    "timestamp": timestamp,
                    "predicted_watts": predicted_watts,
                    "actual_watts": actual_watts,
                    "error_watts": error_watts,
                    "absolute_error_watts": abs(error_watts),
                    "ems_mode": decision["mode"],
                    "mode_numeric": mode_numeric,
                    "ems_reason": decision["reason"],
                    "tou_period": decision["tou_period"],
                    "price": decision["price"],
                    "battery_power_kW": decision["Pbatt_kW"],
                    "grid_power_kW": decision["Pgrid_kW"],
                    "estimated_soc_kWh": decision["SOC_kWh"],
                }
            )

            print(
                f"{timestamp} | predicted={predicted_watts:7.2f} W | "
                f"actual={actual_watts:7.2f} W | error={error_watts:+7.2f} W | "
                f"mode={decision['mode']}"
            )

            if args.live and target_index < end - 1:
                print("Waiting for the next dataset interval...", flush=True)
                time.sleep(args.interval_seconds)
    finally:
        if mqtt_client is not None:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()

    results_frame = pd.DataFrame(results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results_frame.to_csv(args.output, index=False)

    print()
    print(f"Replay MAE: {results_frame['absolute_error_watts'].mean():.2f} W")
    print(f"Saved replay results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
