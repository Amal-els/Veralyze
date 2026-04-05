"""
UPFD dataset loader — wraps the built-in PyTorch Geometric UPFD dataset
for quick benchmarking without needing a Twitter API key.

Datasets:
  - 'politifact': 314 real + 314 fake news propagation graphs
  - 'gossipcop': 16,817 real + 5,323 fake news propagation graphs

Feature options:
  - 'bert': 768d BERT embeddings of news content
  - 'spacy': 300d spaCy word vectors
  - 'profile': 10d user profile features
  - 'content': 310d combined (spacy + profile)
"""

import logging
from typing import Tuple

from torch_geometric.data import Dataset
from torch_geometric.loader import DataLoader

logger = logging.getLogger(__name__)


def load_upfd(
    root: str = "./data/upfd",
    name: str = "gossipcop",
    feature: str = "bert",
) -> Tuple[Dataset, Dataset, Dataset]:
    """
    Load UPFD benchmark dataset.

    Args:
        root: Directory to download/cache the dataset
        name: 'politifact' or 'gossipcop'
        feature: Node feature type — 'bert', 'spacy', 'profile', or 'content'

    Returns:
        (train_dataset, val_dataset, test_dataset)
    """
    from torch_geometric.datasets import UPFD

    logger.info(f"Loading UPFD dataset: {name}/{feature}…")

    train = UPFD(root, name, feature, split="train")
    val = UPFD(root, name, feature, split="val")
    test = UPFD(root, name, feature, split="test")

    logger.info(
        f"UPFD {name}/{feature} loaded: "
        f"train={len(train)}, val={len(val)}, test={len(test)}"
    )

    return train, val, test


def get_upfd_loaders(
    root: str = "./data/upfd",
    name: str = "gossipcop",
    feature: str = "bert",
    batch_size: int = 128,
    num_workers: int = 0,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Get DataLoaders for the UPFD dataset, ready for training.

    Returns:
        (train_loader, val_loader, test_loader)
    """
    train, val, test = load_upfd(root, name, feature)

    train_loader = DataLoader(train, batch_size=batch_size, shuffle=True, num_workers=num_workers)
    val_loader = DataLoader(val, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    test_loader = DataLoader(test, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    return train_loader, val_loader, test_loader


def get_upfd_feature_dim(feature: str) -> int:
    """Return the feature dimension for a given UPFD feature type."""
    dims = {"bert": 768, "spacy": 300, "profile": 10, "content": 310}
    return dims.get(feature, 768)
