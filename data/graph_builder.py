"""
Graph builder: converts PropagationTree objects into PyTorch Geometric
Data objects suitable for GNN training.

Each propagation tree becomes one graph with:
  - x: node feature matrix [num_nodes, feature_dim]
  - edge_index: top-down edges [2, num_edges]
  - edge_index_bu: bottom-up edges [2, num_edges]
  - y: label (0=real/organic, 1=fake/bot-like)
  - root_index: index of the root node
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import torch
from torch_geometric.data import Data

from .feature_extractor import FeatureExtractor

logger = logging.getLogger(__name__)


def tree_dict_to_pyg(
    tree_dict: dict,
    label: int,
    feature_extractor: Optional[FeatureExtractor] = None,
) -> Data:
    """
    Convert a serialized PropagationTree dict to a PyG Data object.

    Args:
        tree_dict: Dict with 'root_id', 'nodes', 'edges' keys
                   (as produced by PropagationTree.to_dict())
        label: Graph-level label (0 or 1)
        feature_extractor: FeatureExtractor instance (created if None)

    Returns:
        torch_geometric.data.Data object
    """
    if feature_extractor is None:
        feature_extractor = FeatureExtractor(use_text_embeddings=True)

    nodes_dict = tree_dict["nodes"]
    edges_list = tree_dict["edges"]
    root_id = tree_dict["root_id"]

    # Create stable node ordering (root first)
    node_ids = list(nodes_dict.keys())
    # Ensure root is at index 0
    root_key = None
    for nid in node_ids:
        if nodes_dict[nid].get("node_id") == f"tweet_{root_id}" or nid == root_id:
            root_key = nid
            break
    if root_key and root_key in node_ids:
        node_ids.remove(root_key)
        node_ids.insert(0, root_key)

    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    # Extract node data for feature extraction
    node_list = [nodes_dict[nid] for nid in node_ids]
    root_created_at = node_list[0].get("created_at") if node_list else None

    # Extract features
    x = feature_extractor.extract_batch(node_list, root_created_at=root_created_at)

    # Build edge indices
    edge_src_td, edge_dst_td = [], []  # top-down
    edge_src_bu, edge_dst_bu = [], []  # bottom-up

    for edge in edges_list:
        parent_key = edge["parent"]
        child_key = edge["child"]

        if parent_key in id_to_idx and child_key in id_to_idx:
            p_idx = id_to_idx[parent_key]
            c_idx = id_to_idx[child_key]

            # Top-down: parent → child
            edge_src_td.append(p_idx)
            edge_dst_td.append(c_idx)

            # Bottom-up: child → parent
            edge_src_bu.append(c_idx)
            edge_dst_bu.append(p_idx)

    # Handle empty graphs (single node, no edges)
    if not edge_src_td:
        # Self-loop on root
        edge_src_td = [0]
        edge_dst_td = [0]
        edge_src_bu = [0]
        edge_dst_bu = [0]

    data = Data(
        x=torch.tensor(x, dtype=torch.float),
        edge_index=torch.tensor([edge_src_td, edge_dst_td], dtype=torch.long),
        BU_edge_index=torch.tensor([edge_src_bu, edge_dst_bu], dtype=torch.long),
        y=torch.tensor([label], dtype=torch.long),
        root_index=torch.tensor([0], dtype=torch.long),
        num_nodes=len(node_ids),
    )

    return data


def tree_file_to_pyg(
    json_path: Union[str, Path],
    label: int,
    feature_extractor: Optional[FeatureExtractor] = None,
) -> Data:
    """Load a JSON tree file and convert to PyG Data."""
    with open(json_path, "r", encoding="utf-8") as f:
        tree_dict = json.load(f)
    return tree_dict_to_pyg(tree_dict, label, feature_extractor)


def propagation_tree_to_pyg(
    tree,  # PropagationTree object
    label: int,
    feature_extractor: Optional[FeatureExtractor] = None,
) -> Data:
    """Convert a live PropagationTree object to PyG Data."""
    return tree_dict_to_pyg(tree.to_dict(), label, feature_extractor)


def add_self_loops_if_needed(data: Data) -> Data:
    """Add self-loops to isolated nodes to avoid GNN issues."""
    from torch_geometric.utils import add_self_loops as _add_self_loops

    data.edge_index, _ = _add_self_loops(data.edge_index, num_nodes=data.num_nodes)
    data.BU_edge_index, _ = _add_self_loops(data.BU_edge_index, num_nodes=data.num_nodes)
    return data
