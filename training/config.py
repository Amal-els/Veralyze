"""
Training configuration — centralized hyperparameters and experiment settings.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrainConfig:
    """All hyperparameters for a training run."""

    # ── Model ──
    model: str = "bigcn"                # bigcn | gcnfn
    hidden_dim: int = 128
    num_layers: int = 2
    dropout: float = 0.5
    num_classes: int = 2

    # ── Dataset ──
    dataset: str = "upfd"               # upfd | custom
    upfd_name: str = "gossipcop"        # politifact | gossipcop
    upfd_feature: str = "bert"          # bert | spacy | profile | content
    custom_data_dir: str = "./dataset"  # for custom dataset
    use_text_embeddings: bool = True    # for custom dataset feature extraction

    # ── Training ──
    lr: float = 0.01
    weight_decay: float = 0.001
    epochs: int = 60
    batch_size: int = 128
    patience: int = 10                  # early stopping patience
    min_delta: float = 0.001            # min improvement for early stopping

    # ── System ──
    device: str = "auto"                # auto | cpu | cuda | cuda:0
    num_workers: int = 0
    seed: int = 42
    checkpoint_dir: str = "./checkpoints"
    log_interval: int = 5               # print every N epochs

    def resolve_device(self) -> str:
        """Resolve 'auto' to the best available device."""
        if self.device != "auto":
            return self.device
        import torch
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def to_dict(self) -> dict:
        """Serialize config for logging."""
        return {k: v for k, v in self.__dict__.items()}
