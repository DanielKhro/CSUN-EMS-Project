"""GRU model for one-step-ahead electrical load prediction."""

from __future__ import annotations

import torch
from torch import nn


class LoadGRU(nn.Module):
	"""Predict the next normalized load value from a feature sequence."""

	def __init__(
		self,
		input_size: int,
		hidden_size: int = 64,
		num_layers: int = 2,
		dropout: float = 0.1,
	) -> None:
		super().__init__()

		if input_size < 1:
			raise ValueError("input_size must be positive.")
		if hidden_size < 1:
			raise ValueError("hidden_size must be positive.")
		if num_layers < 1:
			raise ValueError("num_layers must be positive.")

		self.gru = nn.GRU(
			input_size=input_size,
			hidden_size=hidden_size,
			num_layers=num_layers,
			batch_first=True,
			dropout=dropout if num_layers > 1 else 0.0,
		)

		self.regressor = nn.Sequential(
			nn.Linear(hidden_size, 32),
			nn.ReLU(),
			nn.Linear(32, 1),
		)

	def forward(self, inputs: torch.Tensor) -> torch.Tensor:
		"""Return one prediction for each sequence in ``inputs``.

		Expected input shape: ``(batch_size, sequence_length, input_size)``.
		Returned shape: ``(batch_size, 1)``.
		"""
		if inputs.ndim != 3:
			raise ValueError(
				"inputs must have shape (batch_size, sequence_length, input_size)."
			)

		sequence_output, _ = self.gru(inputs)
		final_step = sequence_output[:, -1, :]
		return self.regressor(final_step)


MODEL_INPUT_SIZE = 6
MODEL_HIDDEN_SIZE = 64
MODEL_NUM_LAYERS = 2


if __name__ == "__main__":
	model = LoadGRU(
		input_size=MODEL_INPUT_SIZE,
		hidden_size=MODEL_HIDDEN_SIZE,
		num_layers=MODEL_NUM_LAYERS,
	)
	sample_input = torch.zeros(4, 96, MODEL_INPUT_SIZE)
	sample_output = model(sample_input)
	print(f"Input shape:  {tuple(sample_input.shape)}")
	print(f"Output shape: {tuple(sample_output.shape)}")
