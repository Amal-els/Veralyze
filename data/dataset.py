"""
Custom PyTorch Geometric InMemoryDataset for propagation graphs.

Loads pre-crawled JSON tree files from a raw directory, processes them
into PyG Data objects, and caches the processed results.

Expected directory structure:
    data/raw/
        organic/          ← label 0
            tweet_123.json
            tweet_456.json
        bot_like/         ← label 1
            tweet_789.json
            tweet_012.json
"""

import logging
from pathlib import Path
from typing import Optional

import torch
from torch_geometric.data import InMemoryDataset

from .feature_extractor import FeatureExtractor
from .graph_builder import tree_file_to_pyg

logger = logging.getLogger(__name__)


class PropagationDataset(InMemoryDataset):
    """
    Custom dataset of propagation trees for graph classification.

    Labels:
        0 = organic / real
        1 = bot-like / fake
    """

    LABEL_MAP = {"organic": 0, "real": 0, "bot_like": 1, "fake": 1}

    def __init__(
        self,
        root: str = "./dataset",
        use_text_embeddings: bool = True,
        transform=None,
        pre_transform=None,
        pre_filter=None,
    ):
        self.use_text = use_text_embeddings
        super().__init__(root, transform, pre_transform, pre_filter)
        self.load(self.processed_paths[0])

    @property
    def raw_dir(self) -> str:
        return str(Path(self.root) / "raw")

    @property
    def processed_dir(self) -> str:
        return str(Path(self.root) / "processed")

    @property
    def raw_file_names(self):
        """Return list of expected raw subdirectories."""
        raw = Path(self.raw_dir)
        if not raw.exists():
            return []
        return [d.name for d in raw.iterdir() if d.is_dir()]

    @property
    def processed_file_names(self):
        return ["propagation_data.pt"]

    def download(self):
        """No auto-download — user provides raw data."""
        logger.info(
            f"Place your JSON tree files in: {self.raw_dir}/organic/ and "
            f"{self.raw_dir}/bot_like/"
        )

    def process(self):
        """Process all JSON trees into PyG Data objects."""
        extractor = FeatureExtractor(use_text_embeddings=self.use_text)
        data_list = []

        raw_path = Path(self.raw_dir)
        for label_dir in sorted(raw_path.iterdir()):
            if not label_dir.is_dir():
                continue

            label_name = label_dir.name.lower()
            label = self.LABEL_MAP.get(label_name)
            if label is None:
                logger.warning(
                    f"Skipping unknown label directory: {label_dir.name}. "
                    f"Expected one of: {list(self.LABEL_MAP.keys())}"
                )
                continue

            json_files = sorted(label_dir.glob("*.json"))
            logger.info(f"Processing {len(json_files)} trees from '{label_dir.name}' (label={label})")

            for jf in json_files:
                try:
                    data = tree_file_to_pyg(jf, label=label, feature_extractor=extractor)
                    if self.pre_filter is not None and not self.pre_filter(data):
                        continue
                    if self.pre_transform is not None:
                        data = self.pre_transform(data)
                    data_list.append(data)
                except Exception as e:
                    logger.warning(f"Failed to process {jf.name}: {e}")

        if not data_list:
            logger.warning(
                "No data found! Make sure raw JSON files are in the correct directories."
            )
            return

        self.save(data_list, self.processed_paths[0])
        logger.info(f"Processed {len(data_list)} propagation graphs → {self.processed_paths[0]}")
