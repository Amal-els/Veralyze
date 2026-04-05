"""
Training loop for propagation graph GNN models.

Supports:
  - UPFD benchmark dataset (built-in PyG)
  - Custom crawled propagation dataset
  - Early stopping with patience
  - Model checkpointing (best validation accuracy)
  - Per-epoch logging
"""

import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.loader import DataLoader

from .config import TrainConfig
from .evaluate import evaluate_model, print_metrics
from data.upfd_loader import load_upfd, get_upfd_feature_dim
from models.bigcn import BiGCN
from models.gcnfn import GCNFN

logger = logging.getLogger(__name__)


def build_model(config: TrainConfig, in_channels: int) -> nn.Module:
    """Instantiate the GNN model based on config."""
    if config.model == "bigcn":
        return BiGCN(
            in_channels=in_channels,
            hidden_channels=config.hidden_dim,
            num_classes=config.num_classes,
            num_layers=config.num_layers,
            dropout=config.dropout,
        )
    elif config.model == "gcnfn":
        return GCNFN(
            in_channels=in_channels,
            hidden_channels=config.hidden_dim,
            num_classes=config.num_classes,
            dropout=config.dropout,
        )
    else:
        raise ValueError(f"Unknown model: {config.model}. Use 'bigcn' or 'gcnfn'.")


def load_data(config: TrainConfig) -> Tuple[DataLoader, DataLoader, DataLoader, int]:
    """
    Load dataset and create DataLoaders.

    Returns:
        (train_loader, val_loader, test_loader, in_channels)
    """
    if config.dataset == "upfd":
        train_ds, val_ds, test_ds = load_upfd(
            root="./data/upfd",
            name=config.upfd_name,
            feature=config.upfd_feature,
        )
        in_channels = get_upfd_feature_dim(config.upfd_feature)
    elif config.dataset == "custom":
        from data.dataset import PropagationDataset

        full_ds = PropagationDataset(
            root=config.custom_data_dir,
            use_text_embeddings=config.use_text_embeddings,
        )
        # Split 70/15/15
        n = len(full_ds)
        n_train = int(0.7 * n)
        n_val = int(0.15 * n)
        n_test = n - n_train - n_val

        torch.manual_seed(config.seed)
        train_ds, val_ds, test_ds = torch.utils.data.random_split(
            full_ds, [n_train, n_val, n_test]
        )
        in_channels = full_ds[0].x.shape[1]
    else:
        raise ValueError(f"Unknown dataset: {config.dataset}. Use 'upfd' or 'custom'.")

    train_loader = DataLoader(
        train_ds, batch_size=config.batch_size, shuffle=True,
        num_workers=config.num_workers,
    )
    val_loader = DataLoader(
        val_ds, batch_size=config.batch_size, shuffle=False,
        num_workers=config.num_workers,
    )
    test_loader = DataLoader(
        test_ds, batch_size=config.batch_size, shuffle=False,
        num_workers=config.num_workers,
    )

    return train_loader, val_loader, test_loader, in_channels


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: str,
) -> Tuple[float, float]:
    """
    Train for one epoch.

    Returns:
        (average_loss, accuracy)
    """
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch in loader:
        batch = batch.to(device)
        optimizer.zero_grad()

        logits = model(batch)
        loss = F.cross_entropy(logits, batch.y)

        loss.backward()
        optimizer.step()

        total_loss += loss.item() * batch.y.size(0)
        pred = logits.argmax(dim=1)
        correct += (pred == batch.y).sum().item()
        total += batch.y.size(0)

    avg_loss = total_loss / max(total, 1)
    accuracy = correct / max(total, 1)
    return avg_loss, accuracy


@torch.no_grad()
def validate(model: nn.Module, loader: DataLoader, device: str) -> Tuple[float, float]:
    """
    Validate the model.

    Returns:
        (average_loss, accuracy)
    """
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch in loader:
        batch = batch.to(device)
        logits = model(batch)
        loss = F.cross_entropy(logits, batch.y)

        total_loss += loss.item() * batch.y.size(0)
        pred = logits.argmax(dim=1)
        correct += (pred == batch.y).sum().item()
        total += batch.y.size(0)

    avg_loss = total_loss / max(total, 1)
    accuracy = correct / max(total, 1)
    return avg_loss, accuracy


def train(config: Optional[TrainConfig] = None) -> nn.Module:
    """
    Full training pipeline.

    Steps:
      1. Load data
      2. Build model
      3. Train with early stopping
      4. Evaluate on test set
      5. Save best checkpoint

    Returns:
        The trained model
    """
    if config is None:
        config = TrainConfig()

    # Setup
    device = config.resolve_device()
    torch.manual_seed(config.seed)
    logger.info(f"Training config: {config.to_dict()}")
    logger.info(f"Device: {device}")

    # Load data
    train_loader, val_loader, test_loader, in_channels = load_data(config)
    logger.info(f"Input feature dimension: {in_channels}")

    # Build model
    model = build_model(config, in_channels).to(device)
    param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info(f"Model: {config.model} ({param_count:,} trainable parameters)")

    # Optimizer
    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.lr, weight_decay=config.weight_decay
    )

    # Early stopping state
    best_val_acc = 0.0
    best_epoch = 0
    patience_counter = 0
    checkpoint_dir = Path(config.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    best_path = checkpoint_dir / f"best_{config.model}_{config.dataset}.pt"

    # ── Training loop ──
    print(f"\n{'='*60}")
    print(f"  Training {config.model.upper()} on {config.dataset}")
    print(f"  {param_count:,} parameters | device={device}")
    print(f"{'='*60}\n")

    start_time = time.time()

    for epoch in range(1, config.epochs + 1):
        # Train
        train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, device)

        # Validate
        val_loss, val_acc = validate(model, val_loader, device)

        # Logging
        if epoch % config.log_interval == 0 or epoch == 1:
            print(
                f"  Epoch {epoch:3d}/{config.epochs} │ "
                f"Train Loss: {train_loss:.4f}  Acc: {train_acc:.4f} │ "
                f"Val Loss: {val_loss:.4f}  Acc: {val_acc:.4f}"
            )

        # Early stopping check
        if val_acc > best_val_acc + config.min_delta:
            best_val_acc = val_acc
            best_epoch = epoch
            patience_counter = 0
            # Save checkpoint
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_acc": val_acc,
                    "config": config.to_dict(),
                },
                best_path,
            )
        else:
            patience_counter += 1
            if patience_counter >= config.patience:
                print(f"\n  ⏹ Early stopping at epoch {epoch} (patience={config.patience})")
                break

    elapsed = time.time() - start_time
    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Best validation accuracy: {best_val_acc:.4f} (epoch {best_epoch})")

    # ── Load best model and evaluate on test set ──
    if best_path.exists():
        checkpoint = torch.load(best_path, map_location=device, weights_only=True)
        model.load_state_dict(checkpoint["model_state_dict"])
        logger.info(f"Loaded best checkpoint from epoch {checkpoint['epoch']}")

    print(f"\n{'='*60}")
    print(f"  Test Set Evaluation")
    print(f"{'='*60}\n")

    metrics = evaluate_model(model, test_loader, device)
    print_metrics(metrics)

    print(f"\n  Checkpoint saved: {best_path}")

    return model
