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
DEFAULT_INPUT = SCRIPT_DIR / "energy_weather_102126_3.csv"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "gru_dataset_weather_102126_3"
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
DEFAULT_MAX_INTERPOLATE_STEPS = 4


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
		"--max-interpolate-steps",
		type=int,
		default=DEFAULT_MAX_INTERPOLATE_STEPS,
		help="Interpolate only missing runs up to this many 15-minute rows.",
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


def load_csv_files(
	paths: Sequence[Path],
	feature_columns: Sequence[str],
	preserve_missing: bool = False,
) -> pd.DataFrame:
	frames = []
	for path in paths:
		if not path.exists():
			raise FileNotFoundError(f"Input file does not exist: {path}")
		frame = pd.read_csv(path)
		if "imputed" in frame.columns:
			frame["imputed"] = (
				frame["imputed"].astype(str).str.strip().str.lower().isin(
					{"true", "1", "yes"}
				)
			)
		else:
			frame["imputed"] = False
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

	if not preserve_missing:
		data = data.dropna(subset=feature_columns).reset_index(drop=True)
	if data.empty:
		raise ValueError("No valid numeric rows remain after cleaning.")

	data = data[["timestamp", *feature_columns, "imputed"]]
	return add_calendar_features(data)


def regularize_and_interpolate(
	data: pd.DataFrame,
	measured_features: Sequence[str],
	max_interpolate_steps: int,
) -> tuple[pd.DataFrame, np.ndarray, int, int]:
	if len(data) < 2:
		raise ValueError("At least two timestamped rows are required.")
	if max_interpolate_steps < 0:
		raise ValueError("--max-interpolate-steps cannot be negative.")

	data = data.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
	start = data["timestamp"].iloc[0]
	offset_seconds = (
		(data["timestamp"] - start).dt.total_seconds().to_numpy()
	)
	if np.any(np.mod(offset_seconds, 900.0) != 0):
		raise ValueError("All timestamps must align to 15-minute intervals.")

	full_index = pd.date_range(
		start=start,
		end=data["timestamp"].iloc[-1],
		freq="15min",
	)
	data = data.set_index("timestamp").reindex(full_index)
	data.index.name = "timestamp"
	data = data.reset_index()
	source_imputed = data["imputed"].fillna(True).to_numpy(dtype=bool)

	target_observed = data[TARGET_COLUMN].notna().to_numpy() & ~source_imputed
	missing_rows = data[list(measured_features)].isna().any(axis=1).to_numpy()
	missing_positions = np.flatnonzero(missing_rows)
	interpolated_rows = 0
	unfilled_gap_rows = 0

	if missing_positions.size:
		run_starts = missing_positions[
			np.r_[True, np.diff(missing_positions) > 1]
		]
		run_ends = missing_positions[
			np.r_[np.diff(missing_positions) > 1, True]
		]
		for run_start, run_end in zip(run_starts, run_ends):
			run_length = int(run_end - run_start + 1)
			has_neighbors = run_start > 0 and run_end < len(data) - 1
			if run_length > max_interpolate_steps or not has_neighbors:
				unfilled_gap_rows += run_length
				continue

			for column in measured_features:
				values = data[column].to_numpy(dtype=np.float64, copy=True)
				missing_in_run = np.isnan(values[run_start : run_end + 1])
				if not missing_in_run.any():
					continue
				left = run_start - 1
				right = run_end + 1
				if not np.isfinite(values[left]) or not np.isfinite(values[right]):
					continue
				interpolated = np.linspace(
					values[left], values[right], run_length + 2, dtype=np.float64
				)[1:-1]
				run_values = values[run_start : run_end + 1]
				run_values[missing_in_run] = interpolated[missing_in_run]
				values[run_start : run_end + 1] = run_values
				data[column] = values
			source_imputed[run_start : run_end + 1] = True
			interpolated_rows += run_length

	data["imputed"] = source_imputed
	data = add_calendar_features(data)
	return data, target_observed, interpolated_rows, unfilled_gap_rows


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
	target_observed: np.ndarray,
	interpolated_rows: int,
	unfilled_gap_rows: int,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
	values = data[list(feature_columns)].to_numpy(dtype=np.float32)
	timestamps = data["timestamp"].astype(str).to_numpy()
	target_column_index = feature_columns.index(TARGET_COLUMN)

	split_row = int(len(data) * train_fraction)
	validation_end_row = int(len(data) * (train_fraction + validation_fraction))
	if split_row <= lookback or validation_end_row <= split_row:
		raise ValueError("The dataset is too small for the requested lookback and splits.")

	valid_training_rows = (
		target_observed[:split_row]
		& np.isfinite(values[:split_row]).all(axis=1)
	)
	training_values = values[:split_row][valid_training_rows]
	if len(training_values) <= lookback:
		raise ValueError("Too few complete training rows remain after gap handling.")
	feature_mean = training_values.mean(axis=0)
	feature_scale = training_values.std(axis=0)
	feature_scale[feature_scale < 1e-8] = 1.0

	target_mean = np.array([feature_mean[target_column_index]], dtype=np.float32)
	target_scale = np.array([feature_scale[target_column_index]], dtype=np.float32)
	normalized = standardize(values, feature_mean, feature_scale)

	sequences = []
	targets = []
	target_timestamps = []
	split_names = []

	for target_index in range(lookback, len(values)):
		if not target_observed[target_index]:
			continue
		if not target_observed[target_index - lookback : target_index].all():
			continue
		window = normalized[target_index - lookback : target_index]
		if not np.isfinite(window).all():
			continue

		target_row = target_index
		if target_row < split_row:
			split_name = "train"
		elif target_row < validation_end_row:
			split_name = "validation"
		else:
			split_name = "test"

		sequences.append(window)
		targets.append(normalized[target_index, target_column_index])
		target_timestamps.append(timestamps[target_index])
		split_names.append(split_name)

	if not sequences:
		raise ValueError("No valid training sequences remain after gap handling.")
	sequence_array = np.asarray(sequences, dtype=np.float32)
	target_array = np.asarray(targets, dtype=np.float32).reshape(-1, 1)
	timestamp_array = np.asarray(target_timestamps)
	split_array = np.asarray(split_names)

	output = {}
	for split_name in ("train", "validation", "test"):
		mask = split_array == split_name
		if not np.any(mask):
			raise ValueError(
				f"No {split_name} sequences remain after gap handling."
			)
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
		"interpolated_rows": interpolated_rows,
		"unfilled_gap_rows": unfilled_gap_rows,
		"observed_target_rows": int(target_observed.sum()),
		"synthetic_rows_excluded": int((~target_observed).sum()),
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

	data = load_csv_files(args.input, args.features, preserve_missing=True)
	data, target_observed, interpolated_rows, unfilled_gap_rows = (
		regularize_and_interpolate(data, args.features, args.max_interpolate_steps)
	)
	validate_cadence(data)
	feature_columns = list(args.features) + CALENDAR_FEATURES
	arrays, metadata = build_sequences(
		data,
		feature_columns,
		args.lookback,
		args.train_fraction,
		args.validation_fraction,
		target_observed,
		interpolated_rows,
		unfilled_gap_rows,
	)

	args.output_dir.mkdir(parents=True, exist_ok=True)
	np.savez_compressed(args.output_dir / "gru_sequences.npz", **arrays)
	with (args.output_dir / "metadata.json").open("w", encoding="utf-8") as file:
		json.dump(metadata, file, indent=2)

	print(f"Rows loaded: {metadata['row_count']}")
	print(f"Short-gap rows interpolated: {metadata['interpolated_rows']}")
	print(f"Unfilled gap rows left missing: {metadata['unfilled_gap_rows']}")
	print(f"Observed target rows: {metadata['observed_target_rows']}")
	print(f"Synthetic rows excluded from targets/history: {metadata['synthetic_rows_excluded']}")
	print(f"Time range: {metadata['source_start']} -> {metadata['source_end']}")
	print(f"Features: {', '.join(feature_columns)}")
	print(f"Lookback: {args.lookback} steps ({args.lookback * 15 / 60:.1f} hours)")
	for split_name in ("train", "validation", "test"):
		print(f"{split_name.title()} sequences: {len(arrays[f'X_{split_name}'])}")
	print(f"Saved dataset to: {args.output_dir.resolve()}")


if __name__ == "__main__":
	main()
