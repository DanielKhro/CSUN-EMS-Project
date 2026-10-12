"""Train the GRU load predictor using a prepared sequence dataset.

Example:
	python train_gru.py
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from gru_model import LoadGRU


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = SCRIPT_DIR / "gru_dataset_weather"
DEFAULT_MODEL_PATH = SCRIPT_DIR / "trained_models" / "weather_load_gru.pt"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
	parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
	parser.add_argument("--epochs", type=int, default=20)
	parser.add_argument("--batch-size", type=int, default=512)
	parser.add_argument("--learning-rate", type=float, default=0.001)
	parser.add_argument("--patience", type=int, default=8)
	parser.add_argument("--seed", type=int, default=42)
	parser.add_argument(
		"--num-threads",
		type=int,
		default=4,
		help="Limit CPU threads used by PyTorch training.",
	)
	return parser.parse_args()


def set_seed(seed: int) -> None:
	random.seed(seed)
	np.random.seed(seed)
	torch.manual_seed(seed)
	if torch.cuda.is_available():
		torch.cuda.manual_seed_all(seed)


def load_dataset(data_dir: Path) -> tuple[dict[str, np.ndarray], dict]:
	sequence_path = data_dir / "gru_sequences.npz"
	metadata_path = data_dir / "metadata.json"

	if not sequence_path.exists():
		raise FileNotFoundError(f"Could not find prepared dataset: {sequence_path}")
	if not metadata_path.exists():
		raise FileNotFoundError(f"Could not find dataset metadata: {metadata_path}")

	with np.load(sequence_path, allow_pickle=False) as archive:
		arrays = {name: archive[name] for name in archive.files}
	with metadata_path.open("r", encoding="utf-8") as file:
		metadata = json.load(file)

	required_arrays = {
		"X_train",
		"y_train",
		"X_validation",
		"y_validation",
		"X_test",
		"y_test",
	}
	missing = required_arrays.difference(arrays)
	if missing:
		raise ValueError(f"Prepared dataset is missing arrays: {sorted(missing)}")

	return arrays, metadata


def make_loader(features: np.ndarray, targets: np.ndarray, batch_size: int, shuffle: bool) -> DataLoader:
	feature_tensor = torch.from_numpy(features).float()
	target_tensor = torch.from_numpy(targets).float()
	dataset = TensorDataset(feature_tensor, target_tensor)
	return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def run_epoch(
	model: LoadGRU,
	loader: DataLoader,
	loss_function: nn.Module,
	device: torch.device,
	optimizer: torch.optim.Optimizer | None = None,
) -> tuple[float, float]:
	is_training = optimizer is not None
	model.train(is_training)
	total_loss = 0.0
	total_absolute_error = 0.0
	total_examples = 0

	for features, targets in loader:
		features = features.to(device)
		targets = targets.to(device)

		if is_training:
			optimizer.zero_grad()

		predictions = model(features)
		loss = loss_function(predictions, targets)

		if is_training:
			loss.backward()
			torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
			optimizer.step()

		example_count = features.size(0)
		total_loss += loss.item() * example_count
		total_absolute_error += torch.abs(predictions - targets).sum().item()
		total_examples += example_count

	return total_loss / total_examples, total_absolute_error / total_examples


def main() -> None:
	args = parse_args()
	if args.epochs < 1 or args.batch_size < 1 or args.patience < 1 or args.num_threads < 1:
		raise ValueError("epochs, batch-size, patience, and num-threads must be positive.")
	if args.learning_rate <= 0:
		raise ValueError("learning-rate must be positive.")

	torch.set_num_threads(args.num_threads)
	set_seed(args.seed)
	arrays, metadata = load_dataset(args.data_dir)
	feature_count = arrays["X_train"].shape[-1]
	hidden_size = 64
	layer_count = 2
	device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

	train_loader = make_loader(
		arrays["X_train"], arrays["y_train"], args.batch_size, shuffle=True
	)
	validation_loader = make_loader(
		arrays["X_validation"], arrays["y_validation"], args.batch_size, shuffle=False
	)
	test_loader = make_loader(
		arrays["X_test"], arrays["y_test"], args.batch_size, shuffle=False
	)

	model = LoadGRU(
		input_size=feature_count,
		hidden_size=hidden_size,
		num_layers=layer_count,
	).to(device)
	loss_function = nn.MSELoss()
	optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)

	target_scale = float(metadata["target_scale"][0])
	target_mean = float(metadata["target_mean"][0])
	best_validation_loss = float("inf")
	best_state = None
	epochs_without_improvement = 0

	print(f"Device: {device}")
	print(f"Training sequences: {len(arrays['X_train'])}")
	print(f"Validation sequences: {len(arrays['X_validation'])}")
	print(f"Test sequences: {len(arrays['X_test'])}")

	for epoch in range(1, args.epochs + 1):
		train_loss, train_scaled_mae = run_epoch(
			model, train_loader, loss_function, device, optimizer
		)
		validation_loss, validation_scaled_mae = run_epoch(
			model, validation_loader, loss_function, device
		)

		validation_mae_watts = validation_scaled_mae * target_scale
		train_mae_watts = train_scaled_mae * target_scale
		print(
			f"Epoch {epoch:03d} | "
			f"train_loss={train_loss:.5f} | "
			f"val_loss={validation_loss:.5f} | "
			f"train_MAE={train_mae_watts:.2f} W | "
			f"val_MAE={validation_mae_watts:.2f} W"
		)

		if validation_loss < best_validation_loss:
			best_validation_loss = validation_loss
			best_state = {
				key: value.detach().cpu().clone()
				for key, value in model.state_dict().items()
			}
			epochs_without_improvement = 0
		else:
			epochs_without_improvement += 1
			if epochs_without_improvement >= args.patience:
				print("Early stopping: validation loss stopped improving.")
				break

	if best_state is None:
		raise RuntimeError("Training did not produce a model checkpoint.")

	model.load_state_dict(best_state)
	test_loss, test_scaled_mae = run_epoch(model, test_loader, loss_function, device)
	test_mae_watts = test_scaled_mae * target_scale
	test_rmse_watts = (test_loss**0.5) * target_scale

	args.model_path.parent.mkdir(parents=True, exist_ok=True)
	checkpoint = {
		"model_state_dict": best_state,
		"input_size": feature_count,
		"hidden_size": hidden_size,
		"num_layers": layer_count,
		"feature_columns": metadata["feature_columns"],
		"target_column": metadata["target_column"],
		"lookback_steps": metadata["lookback_steps"],
		"feature_mean": metadata["feature_mean"],
		"feature_scale": metadata["feature_scale"],
		"target_mean": target_mean,
		"target_scale": target_scale,
	}
	torch.save(checkpoint, args.model_path)

	print(f"Test MAE:  {test_mae_watts:.2f} W")
	print(f"Test RMSE: {test_rmse_watts:.2f} W")
	print(f"Saved model: {args.model_path.resolve()}")


if __name__ == "__main__":
	main()
