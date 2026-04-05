"""
BiGCN — Bi-Directional Graph Convolutional Network for rumor/fake news detection.

Reference:
    Bian et al., "Rumor Detection on Social Media with Bi-Directional
    Graph Convolutional Networks" (AAAI 2020)

Architecture:
    Two parallel GCN branches process the propagation graph in
    opposite directions:
      - Top-Down (TD): follows information flow (root → leaves)
      - Bottom-Up (BU): captures aggregated responses (leaves → root)

    Graph-level embeddings from both branches are concatenated and
    fed into a classifier head.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import global_mean_pool, global_max_pool

from .base_gnn import GNNBranch, init_weights


class TDRumorGCN(nn.Module):
    """Top-Down branch: processes edges in propagation direction."""

    def __init__(self, in_channels: int, hidden: int, num_layers: int = 2, dropout: float = 0.5):
        super().__init__()
        self.branch = GNNBranch(
            in_channels, hidden, num_layers, conv_type="gcn", dropout=dropout
        )

    def forward(self, x, edge_index, batch):
        h = self.branch(x, edge_index)
        # Root-enhanced pooling: concat mean-pool with root embedding
        pool = global_mean_pool(h, batch)
        return pool


class BURumorGCN(nn.Module):
    """Bottom-Up branch: processes reversed edges (responses aggregated to root)."""

    def __init__(self, in_channels: int, hidden: int, num_layers: int = 2, dropout: float = 0.5):
        super().__init__()
        self.branch = GNNBranch(
            in_channels, hidden, num_layers, conv_type="gcn", dropout=dropout
        )

    def forward(self, x, edge_index_bu, batch):
        h = self.branch(x, edge_index_bu)
        pool = global_mean_pool(h, batch)
        return pool


class BiGCN(nn.Module):
    """
    Bi-Directional GCN for propagation-based graph classification.

    Input:
        - x:              Node features [num_nodes, in_channels]
        - edge_index:     Top-down edges [2, num_edges]
        - BU_edge_index:  Bottom-up edges [2, num_edges]
        - batch:          Batch assignment vector

    Output:
        - logits:         [batch_size, num_classes]
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int = 128,
        num_classes: int = 2,
        num_layers: int = 2,
        dropout: float = 0.5,
    ):
        super().__init__()

        self.td_gcn = TDRumorGCN(in_channels, hidden_channels, num_layers, dropout)
        self.bu_gcn = BURumorGCN(in_channels, hidden_channels, num_layers, dropout)

        # Classifier: takes concatenated TD + BU embeddings
        self.classifier = nn.Sequential(
            nn.Linear(hidden_channels * 2, hidden_channels),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_channels, num_classes),
        )

        self.apply(init_weights)

    def forward(self, data):
        """
        Forward pass accepting a PyG Batch object.

        The Batch object should have:
          - data.x
          - data.edge_index (top-down)
          - data.BU_edge_index (bottom-up)
          - data.batch
        """
        x = data.x
        edge_index_td = data.edge_index
        batch = data.batch

        # Bottom-up edges: use BU_edge_index if available,
        # otherwise flip the top-down edges
        if hasattr(data, "BU_edge_index") and data.BU_edge_index is not None:
            edge_index_bu = data.BU_edge_index
        else:
            edge_index_bu = edge_index_td.flip(0)

        # Run both branches
        td_emb = self.td_gcn(x, edge_index_td, batch)   # [B, hidden]
        bu_emb = self.bu_gcn(x, edge_index_bu, batch)    # [B, hidden]

        # Fuse and classify
        combined = torch.cat([td_emb, bu_emb], dim=1)    # [B, hidden*2]
        logits = self.classifier(combined)                 # [B, num_classes]

        return logits

    def get_embeddings(self, data):
        """Return graph-level embeddings (before classifier) for visualization."""
        x = data.x
        edge_index_td = data.edge_index
        batch = data.batch

        if hasattr(data, "BU_edge_index") and data.BU_edge_index is not None:
            edge_index_bu = data.BU_edge_index
        else:
            edge_index_bu = edge_index_td.flip(0)

        td_emb = self.td_gcn(x, edge_index_td, batch)
        bu_emb = self.bu_gcn(x, edge_index_bu, batch)

        return torch.cat([td_emb, bu_emb], dim=1)
