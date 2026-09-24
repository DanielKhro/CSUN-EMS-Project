"""Replay the load-only GRU through the EMS controller without hardware or MQTT.

Example:
    python run_gru_replay.py --csv ../energy_weather_090826.csv
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


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR.parent / "energy_weather_090826.csv"
DEFAULT_MODEL = SCRIPT_DIR / "trained_models" / "load_only_gru.pt"
DEFAULT_OUTPUT = SCRIPT_DIR / "trained_models" / "load_only_ems_replay.csv"
LOOKBACK_STEPS = 96
TEST_START_FRACTION = 0.85


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Limit replay length for a quick demonstration.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Process one dataset row per interval instead of running as fast as possible.",
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
        default="192.168.8.236",
        help="Raspberry Pi MQTT broker address.",
    )
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument(
        "--mqtt-topic",
        default="relay___mode/mode_select",
        help="MQTT topic consumed by the Raspberry Pi relay controller.",
    )
    return parser.parse_args()


def load_data(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")

    data = pd.read_csv(csv_path)
    required_columns = {"date", "active_power"}
    missing = required_columns.difference(data.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")

    data["timestamp"] = pd.to_datetime(data["date"], errors="coerce")
    data["active_power"] = pd.to_numeric(data["active_power"], errors="coerce")
    data = data.dropna(subset=["timestamp", "active_power"])
    data = data.sort_values("timestamp").drop_duplicates("timestamp")
    data = data.reset_index(drop=True)

    if len(data) < LOOKBACK_STEPS + 1:
        raise ValueError("CSV does not contain enough rows for a 96-step replay.")

    differences = data["timestamp"].diff().dropna().dt.total_seconds() / 60.0
    if not differences.eq(15.0).all():
        raise ValueError("CSV must contain continuous 15-minute timestamps.")

    return data[["timestamp", "active_power"]]


def load_model(model_path: Path) -> tuple[LoadGRU, dict]:
    if not model_path.exists():
        raise FileNotFoundError(f"Model file does not exist: {model_path}")

    try:
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    except TypeError:
        # Older Jetson PyTorch releases do not support weights_only.
        checkpoint = torch.load(model_path, map_location="cpu")
    feature_columns = checkpoint.get("feature_columns")
    if feature_columns != ["active_power"]:
        raise ValueError(
            "The replay expects the load-only model with feature_columns=['active_power']."
        )

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
    history_watts: np.ndarray,
    checkpoint: dict,
) -> float:
    feature_mean = float(checkpoint["feature_mean"][0])
    feature_scale = float(checkpoint["feature_scale"][0])
    target_mean = float(checkpoint["target_mean"])
    target_scale = float(checkpoint["target_scale"])

    normalized_history = (history_watts - feature_mean) / feature_scale
    model_input = torch.from_numpy(normalized_history.astype(np.float32)).reshape(
        1, LOOKBACK_STEPS, 1
    )
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

    client = mqtt.Client(client_id="jetson_gru_load_only")
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
    if not info.wait_for_publish(timeout=5.0):
        raise RuntimeError("MQTT publish was not acknowledged within 5 seconds.")
    print(f"Published to Pi: {payload}")
    return mode_numeric


def main() -> None:
    args = parse_args()
    if args.max_steps is not None and args.max_steps < 1:
        raise ValueError("--max-steps must be positive when provided.")
    if args.interval_seconds <= 0:
        raise ValueError("--interval-seconds must be positive.")

    data = load_data(args.csv)
    model, checkpoint = load_model(args.model_path)
    mqtt_client = connect_mqtt(args)

    test_start = max(LOOKBACK_STEPS, int(len(data) * TEST_START_FRACTION))
    end = len(data)
    if args.max_steps is not None:
        end = min(end, test_start + args.max_steps)

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
    print(f"Replay rows: {end - test_start}")
    print()

    for target_index in range(test_start, end):
        history = data["active_power"].iloc[target_index - LOOKBACK_STEPS : target_index]
        history_watts = history.to_numpy(dtype=np.float32)
        actual_watts = float(data["active_power"].iloc[target_index])
        timestamp = data["timestamp"].iloc[target_index].to_pydatetime()
        predicted_watts = predict_next_watts(model, history_watts, checkpoint)
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

    results_frame = pd.DataFrame(results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results_frame.to_csv(args.output, index=False)
    if mqtt_client is not None:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

    print()
    print(f"Replay MAE: {results_frame['absolute_error_watts'].mean():.2f} W")
    print(f"Saved replay results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
