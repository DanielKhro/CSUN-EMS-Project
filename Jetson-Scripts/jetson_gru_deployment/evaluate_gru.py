"""Evaluate the weather/calendar GRU against simple load-forecast baselines.

Examples:
	python evaluate_gru.py
	python evaluate_gru.py --date 2023-07-15
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, TensorDataset

from gru_model import LoadGRU
from prepare_gru_dataset import (
	CALENDAR_FEATURES,
	WEATHER_FEATURES,
	load_csv_files,
	validate_cadence,
)


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = SCRIPT_DIR / "gru_dataset_weather"
DEFAULT_MODEL_PATH = SCRIPT_DIR / "trained_models" / "weather_load_gru.pt"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "trained_models" / "weather_gru_test_predictions.csv"
DEFAULT_CSV = SCRIPT_DIR / "energy_weather_101026.csv"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
	parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
	parser.add_argument("--output", type=Path)
	parser.add_argument("--batch-size", type=int, default=256)
	parser.add_argument(
		"--date",
		help="Evaluate every available 15-minute sample on this YYYY-MM-DD date.",
	)
	parser.add_argument(
		"--csv",
		type=Path,
		default=DEFAULT_CSV,
		help="Source CSV used with --date.",
	)
	return parser.parse_args()


def load_inputs(data_dir: Path, model_path: Path) -> tuple[dict, dict, dict]:
	sequence_path = data_dir / "gru_sequences.npz"
	metadata_path = data_dir / "metadata.json"
	if not sequence_path.exists():
		raise FileNotFoundError(f"Could not find dataset: {sequence_path}")
	if not metadata_path.exists():
		raise FileNotFoundError(f"Could not find metadata: {metadata_path}")
	if not model_path.exists():
		raise FileNotFoundError(f"Could not find trained model: {model_path}")

	with np.load(sequence_path, allow_pickle=False) as archive:
		arrays = {name: archive[name] for name in archive.files}
	with metadata_path.open("r", encoding="utf-8") as file:
		metadata = json.load(file)
	checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
	if checkpoint.get("feature_columns") != metadata.get("feature_columns"):
		raise ValueError(
			"The model and prepared dataset use different feature columns. "
			"Prepare the dataset and retrain the model."
		)
	return arrays, metadata, checkpoint


def inverse_target(values: np.ndarray, metadata: dict) -> np.ndarray:
	target_mean = float(metadata["target_mean"][0])
	target_scale = float(metadata["target_scale"][0])
	return values * target_scale + target_mean


def gru_predictions(
	features: np.ndarray,
	checkpoint: dict,
	batch_size: int,
) -> np.ndarray:
	tensor_features = torch.from_numpy(features).float()
	loader = DataLoader(TensorDataset(tensor_features), batch_size=batch_size)
	model = LoadGRU(
		input_size=int(checkpoint["input_size"]),
		hidden_size=int(checkpoint["hidden_size"]),
		num_layers=int(checkpoint["num_layers"]),
	)
	model.load_state_dict(checkpoint["model_state_dict"])
	model.eval()

	predictions = []
	with torch.no_grad():
		for (batch_features,) in loader:
			predictions.append(model(batch_features).squeeze(1).numpy())
	return np.concatenate(predictions)


def calculate_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
	valid = np.isfinite(actual) & np.isfinite(predicted)
	if not np.any(valid):
		raise ValueError("No valid samples are available to calculate metrics.")
	actual = actual[valid]
	predicted = predicted[valid]
	error = predicted - actual
	nonzero_actual = np.abs(actual) > 1e-6
	mape = np.mean(
		np.abs(error[nonzero_actual] / actual[nonzero_actual])
	) * 100.0
	return {
		"MAE_W": float(np.mean(np.abs(error))),
		"RMSE_W": float(np.sqrt(np.mean(error**2))),
		"MAPE_percent": float(mape),
		"Bias_W": float(np.mean(error)),
	}


def date_examples(
	csv_path: Path,
	date_text: str,
	metadata: dict,
	checkpoint: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, str]:
	try:
		selected_date = pd.Timestamp(date_text).date()
	except (TypeError, ValueError) as error:
		raise ValueError("--date must be a valid date in YYYY-MM-DD format.") from error

	feature_columns = metadata["feature_columns"]
	weather_columns = [column for column in feature_columns if column in WEATHER_FEATURES]
	expected_columns = weather_columns + CALENDAR_FEATURES
	if feature_columns != expected_columns:
		raise ValueError(
			"Date-based evaluation requires a dataset prepared with the current "
			"weather and calendar features."
		)
	data = load_csv_files([csv_path], weather_columns)
	validate_cadence(data)
	if len(data) < int(metadata["lookback_steps"]) + 1:
		raise ValueError("CSV does not contain enough rows for the configured lookback.")

	target_indexes = np.flatnonzero(data["timestamp"].dt.date.to_numpy() == selected_date)
	if target_indexes.size == 0:
		raise ValueError(f"No valid observations found for {selected_date} in {csv_path}.")

	lookback = int(metadata["lookback_steps"])
	target_indexes = target_indexes[target_indexes > 0]
	if target_indexes.size == 0:
		raise ValueError(
			f"{selected_date} has no observations with any prior load measurement."
		)

	values = data[feature_columns].to_numpy(dtype=np.float32)
	feature_mean = np.asarray(checkpoint["feature_mean"], dtype=np.float32)
	feature_scale = np.asarray(checkpoint["feature_scale"], dtype=np.float32)
	if values.shape[1] != int(checkpoint["input_size"]):
		raise ValueError("CSV feature count does not match the trained model.")
	normalized = (values - feature_mean) / feature_scale
	sequence_windows = []
	for index in target_indexes:
		history = normalized[max(0, index - lookback) : index]
		if len(history) < lookback:
			padding = np.repeat(history[:1], lookback - len(history), axis=0)
			history = np.concatenate((padding, history), axis=0)
		sequence_windows.append(history)
	features = np.asarray(sequence_windows, dtype=np.float32)
	target_index = feature_columns.index(metadata["target_column"])
	actual = data["active_power"].to_numpy(dtype=np.float32)[target_indexes]
	previous = values[target_indexes - 1, target_index]
	yesterday = np.full(len(target_indexes), np.nan, dtype=np.float32)
	has_yesterday = target_indexes >= lookback
	yesterday[has_yesterday] = values[
		target_indexes[has_yesterday] - lookback, target_index
	]

	train_end = pd.Timestamp(metadata["train_end_exclusive"])
	validation_end = pd.Timestamp(metadata["validation_end_exclusive"])
	target_timestamps = data["timestamp"].iloc[target_indexes]
	split_names = np.where(
		target_timestamps < train_end,
		"training",
		np.where(target_timestamps < validation_end, "validation", "test"),
	)
	split_name = "/".join(sorted(set(split_names)))
	timestamps = data["timestamp"].iloc[target_indexes].astype(str).to_numpy()
	return features, actual, previous, yesterday, timestamps, split_name


def main() -> None:
	args = parse_args()
	if args.batch_size < 1:
		raise ValueError("batch-size must be positive.")

	arrays, metadata, checkpoint = load_inputs(args.data_dir, args.model_path)
	if args.date:
		(
			test_features,
			actual,
			previous_watts,
			yesterday_watts,
			timestamps,
			split_name,
		) = date_examples(args.csv, args.date, metadata, checkpoint)
	else:
		test_features = arrays["X_test"]
		actual = inverse_target(arrays["y_test"].reshape(-1), metadata)
		target_index = metadata["feature_columns"].index(metadata["target_column"])
		previous_watts = inverse_target(
			test_features[:, -1, target_index], metadata
		)
		yesterday_watts = inverse_target(
			test_features[:, 0, target_index], metadata
		)
		timestamps = arrays.get("timestamps_test")
		split_name = "test"
	gru_scaled = gru_predictions(test_features, checkpoint, args.batch_size)
	gru_prediction = inverse_target(gru_scaled, metadata)

	predictions = {
		"GRU": gru_prediction,
		"Persistence": previous_watts,
		"SameTimeYesterday": yesterday_watts,
	}

	print(f"Evaluated samples: {len(actual)}")
	if args.date:
		print(f"Selected date: {args.date} ({split_name} period in this dataset)")
		if split_name != "test":
			print("Note: this date was used during training or model selection; metrics are not held-out.")
	print(f"Model: {args.model_path.resolve()}")
	print()
	print(f"{'Method':<20} {'MAE (W)':>12} {'RMSE (W)':>12} {'MAPE':>12} {'Bias (W)':>12}")
	print("-" * 72)
	for method_name, prediction in predictions.items():
		if not np.isfinite(prediction).any():
			print(f"{method_name:<20} {'N/A':>12} {'N/A':>12} {'N/A':>12} {'N/A':>12}")
			continue
		metrics = calculate_metrics(actual, prediction)
		print(
			f"{method_name:<20} "
			f"{metrics['MAE_W']:>12.2f} "
			f"{metrics['RMSE_W']:>12.2f} "
			f"{metrics['MAPE_percent']:>11.2f}% "
			f"{metrics['Bias_W']:>12.2f}"
		)

	results = pd.DataFrame(
		{
			"timestamp": timestamps if timestamps is not None else np.arange(len(actual)),
			"actual_watts": actual,
			"gru_watts": gru_prediction,
			"persistence_watts": previous_watts,
			"same_time_yesterday_watts": yesterday_watts,
		}
	)
	output_path = args.output or (
		SCRIPT_DIR / "trained_models" / f"weather_gru_{pd.Timestamp(args.date).date().isoformat()}_predictions.csv"
		if args.date
		else DEFAULT_OUTPUT_PATH
	)
	output_path.parent.mkdir(parents=True, exist_ok=True)
	results.to_csv(output_path, index=False)
	print(f"Saved detailed predictions: {output_path.resolve()}")


if __name__ == "__main__":
	main()
