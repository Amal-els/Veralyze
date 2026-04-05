"""
GCNFN — Graph Convolutional Network for Fake News detection.

A simpler single-direction GCN baseline for comparison with BiGCN.
Uses only the top-down (propagation direction) edges.

Reference:
    Monti et al., "Fake News Detection on Social Media using
    Geometric Deep Learning" (2019)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, global_mean_pool

from .base_gnn import init_weights


class GCNFN(nn.Module):
    """
    Single-direction GCN for graph classification.

    Architecture:
        GCNConv → BN → ReLU → Dropout
        GCNConv → BN → ReLU → Dropout
        Global Mean Pool
        Linear → ReLU → Dropout
        Linear → num_classes
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int = 128,
        num_classes: int = 2,
        dropout: float = 0.5,
    ):
        super().__init__()

        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.bn1 = nn.BatchNorm1d(hidden_channels)

        self.conv2 = GCNConv(hidden_channels, hidden_channels)
        self.bn2 = nn.BatchNorm1d(hidden_channels)

        self.classifier = nn.Sequential(
            nn.Linear(hidden_channels, hidden_channels // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_channels // 2, num_classes),
        )

        self.dropout = dropout
        self.apply(init_weights)

    def forward(self, data):
        """
        Forward pass accepting a PyG Batch object.

        Uses only data.edge_index (top-down / propagation direction).
        """
        x = data.x
        edge_index = data.edge_index
        batch = data.batch

        # Layer 1
        x = self.conv1(x, edge_index)
        x = self.bn1(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        # Layer 2
        x = self.conv2(x, edge_index)
        x = self.bn2(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        # Readout
        graph_emb = global_mean_pool(x, batch)

        # Classify
        logits = self.classifier(graph_emb)
        return logits

    def get_embeddings(self, data):
        """Return graph-level embeddings for visualization."""
        x = data.x
        edge_index = data.edge_index
        batch = data.batch

        x = F.relu(self.bn1(self.conv1(x, edge_index)))
        x = F.relu(self.bn2(self.conv2(x, edge_index)))
        return global_mean_pool(x, batch)
