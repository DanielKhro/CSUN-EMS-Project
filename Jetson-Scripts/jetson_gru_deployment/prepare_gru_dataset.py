"""Prepare year-round weather/load data for GRU training.

Example:
	python prepare_gru_dataset.py

The output file contains normalized sequence arrays and metadata for the
training script. Scaling parameters are learned from the training period only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "energy_weather_101026.csv"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "gru_dataset_weather"
WEATHER_FEATURES = [
	"active_power",
	"dew_point",
]
CALENDAR_FEATURES = [
	"annual_sin",
	"annual_cos",
	"daily_sin",
	"daily_cos",
	"weekly_sin",
	"weekly_cos",
]
TARGET_COLUMN = "active_power"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--input",
		nargs="+",
		default=[DEFAULT_INPUT],
		type=Path,
		help="One or more CSV files containing date, active_power, and dew_point.",
	)
	parser.add_argument(
		"--output-dir",
		type=Path,
		default=DEFAULT_OUTPUT_DIR,
		help="Directory for the prepared dataset.",
	)
	parser.add_argument(
		"--lookback",
		type=int,
		default=96,
		help="Number of 15-minute steps used to predict the next step.",
	)
	parser.add_argument(
		"--train-fraction",
		type=float,
		default=0.70,
		help="Fraction of chronological samples used for training.",
	)
	parser.add_argument(
		"--validation-fraction",
		type=float,
		default=0.15,
		help="Fraction of chronological samples used for validation.",
	)
	parser.add_argument(
		"--features",
		nargs="+",
		default=WEATHER_FEATURES,
		choices=WEATHER_FEATURES,
		help="Measured input columns. Calendar features are always added.",
	)
	return parser.parse_args()


def add_calendar_features(data: pd.DataFrame) -> pd.DataFrame:
	timestamp = data["timestamp"]
	minute_of_day = timestamp.dt.hour * 60 + timestamp.dt.minute
	day_fraction = minute_of_day / 1440.0
	days_in_year = np.where(timestamp.dt.is_leap_year, 366.0, 365.0)
	annual_fraction = (timestamp.dt.dayofyear - 1 + day_fraction) / days_in_year
	weekly_fraction = (timestamp.dt.dayofweek + day_fraction) / 7.0

	data = data.copy()
	data["annual_sin"] = np.sin(2.0 * np.pi * annual_fraction)
	data["annual_cos"] = np.cos(2.0 * np.pi * annual_fraction)
	data["daily_sin"] = np.sin(2.0 * np.pi * day_fraction)
	data["daily_cos"] = np.cos(2.0 * np.pi * day_fraction)
	data["weekly_sin"] = np.sin(2.0 * np.pi * weekly_fraction)
	data["weekly_cos"] = np.cos(2.0 * np.pi * weekly_fraction)
	return data


def load_csv_files(paths: Sequence[Path], feature_columns: Sequence[str]) -> pd.DataFrame:
	frames = []
	for path in paths:
		if not path.exists():
			raise FileNotFoundError(f"Input file does not exist: {path}")
		frame = pd.read_csv(path)
		frame["source_file"] = path.name
		frames.append(frame)

	if not frames:
		raise ValueError("No input CSV files were supplied.")

	data = pd.concat(frames, ignore_index=True)
	required = {"date", *feature_columns}
	missing = sorted(required.difference(data.columns))
	if missing:
		raise ValueError(f"Missing required columns: {missing}")

	data["timestamp"] = pd.to_datetime(data["date"], errors="coerce")
	data = data.dropna(subset=["timestamp"]).copy()
	data = data.sort_values("timestamp").drop_duplicates("timestamp", keep="last")

	for column in feature_columns:
		data[column] = pd.to_numeric(data[column], errors="coerce")

	data = data.dropna(subset=feature_columns).reset_index(drop=True)
	if data.empty:
		raise ValueError("No valid numeric rows remain after cleaning.")

	data = data[["timestamp", *feature_columns]]
	return add_calendar_features(data)


def validate_cadence(data: pd.DataFrame) -> None:
	if len(data) < 2:
		raise ValueError("At least two rows are required to validate cadence.")

	differences = data["timestamp"].diff().dropna().dt.total_seconds() / 60.0
	invalid = differences[differences != 15.0]
	if not invalid.empty:
		first_gap = data.loc[invalid.index[0] - 1 : invalid.index[0], "timestamp"]
		raise ValueError(
			f"Found {len(invalid)} timestamp gaps or irregular intervals. "
			f"First problem:\n{first_gap.to_string(index=False)}\n"
			"Prepare a continuous 15-minute file before training."
		)


def standardize(values: np.ndarray, mean: np.ndarray, scale: np.ndarray) -> np.ndarray:
	return (values - mean) / scale


def build_sequences(
	data: pd.DataFrame,
	feature_columns: Sequence[str],
	lookback: int,
	train_fraction: float,
	validation_fraction: float,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
	values = data[list(feature_columns)].to_numpy(dtype=np.float32)
	timestamps = data["timestamp"].astype(str).to_numpy()
	target_column_index = feature_columns.index(TARGET_COLUMN)

	split_row = int(len(data) * train_fraction)
	validation_end_row = int(len(data) * (train_fraction + validation_fraction))
	if split_row <= lookback or validation_end_row <= split_row:
		raise ValueError("The dataset is too small for the requested lookback and splits.")

	feature_mean = values[:split_row].mean(axis=0)
	feature_scale = values[:split_row].std(axis=0)
	feature_scale[feature_scale < 1e-8] = 1.0

	target_mean = np.array([feature_mean[target_column_index]], dtype=np.float32)
	target_scale = np.array([feature_scale[target_column_index]], dtype=np.float32)
	normalized = standardize(values, feature_mean, feature_scale)

	sequences = []
	targets = []
	target_timestamps = []
	split_names = []

	for target_index in range(lookback, len(values)):
		target_row = target_index
		if target_row < split_row:
			split_name = "train"
		elif target_row < validation_end_row:
			split_name = "validation"
		else:
			split_name = "test"

		sequences.append(normalized[target_index - lookback : target_index])
		targets.append(normalized[target_index, target_column_index])
		target_timestamps.append(timestamps[target_index])
		split_names.append(split_name)

	sequence_array = np.asarray(sequences, dtype=np.float32)
	target_array = np.asarray(targets, dtype=np.float32).reshape(-1, 1)
	timestamp_array = np.asarray(target_timestamps)
	split_array = np.asarray(split_names)

	output = {}
	for split_name in ("train", "validation", "test"):
		mask = split_array == split_name
		output[f"X_{split_name}"] = sequence_array[mask]
		output[f"y_{split_name}"] = target_array[mask]
		output[f"timestamps_{split_name}"] = timestamp_array[mask]

	metadata = {
		"feature_columns": list(feature_columns),
		"target_column": TARGET_COLUMN,
		"lookback_steps": lookback,
		"interval_minutes": 15,
		"feature_mean": feature_mean.tolist(),
		"feature_scale": feature_scale.tolist(),
		"target_mean": target_mean.tolist(),
		"target_scale": target_scale.tolist(),
		"source_start": str(data["timestamp"].iloc[0]),
		"source_end": str(data["timestamp"].iloc[-1]),
		"row_count": len(data),
		"train_end_exclusive": str(data["timestamp"].iloc[split_row]),
		"validation_end_exclusive": str(data["timestamp"].iloc[validation_end_row]),
	}
	return output, metadata


def main() -> None:
	args = parse_args()
	if args.lookback < 1:
		raise ValueError("--lookback must be at least 1.")
	if not 0.0 < args.train_fraction < 1.0:
		raise ValueError("--train-fraction must be between 0 and 1.")
	if not 0.0 < args.validation_fraction < 1.0:
		raise ValueError("--validation-fraction must be between 0 and 1.")
	if args.train_fraction + args.validation_fraction >= 1.0:
		raise ValueError("Training and validation fractions must leave test data.")

	if TARGET_COLUMN not in args.features:
		raise ValueError("--features must include active_power because it is the target.")

	data = load_csv_files(args.input, args.features)
	validate_cadence(data)
	feature_columns = list(args.features) + CALENDAR_FEATURES
	arrays, metadata = build_sequences(
		data,
		feature_columns,
		args.lookback,
		args.train_fraction,
		args.validation_fraction,
	)

	args.output_dir.mkdir(parents=True, exist_ok=True)
	np.savez_compressed(args.output_dir / "gru_sequences.npz", **arrays)
	with (args.output_dir / "metadata.json").open("w", encoding="utf-8") as file:
		json.dump(metadata, file, indent=2)

	print(f"Rows loaded: {metadata['row_count']}")
	print(f"Time range: {metadata['source_start']} -> {metadata['source_end']}")
	print(f"Features: {', '.join(feature_columns)}")
	print(f"Lookback: {args.lookback} steps ({args.lookback * 15 / 60:.1f} hours)")
	for split_name in ("train", "validation", "test"):
		print(f"{split_name.title()} sequences: {len(arrays[f'X_{split_name}'])}")
	print(f"Saved dataset to: {args.output_dir.resolve()}")


if __name__ == "__main__":
	main()
