"""
Base GNN utilities shared across model implementations.

Provides:
  - Configurable message-passing layer selection (GCN, GAT, GraphSAGE)
  - Graph-level readout (pooling) functions
  - Weight initialization helpers
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import (
    GCNConv,
    GATConv,
    SAGEConv,
    global_mean_pool,
    global_max_pool,
    global_add_pool,
)


def get_conv_layer(conv_type: str, in_channels: int, out_channels: int, **kwargs):
    """
    Factory for PyG convolution layers.

    Args:
        conv_type: 'gcn', 'gat', or 'sage'
        in_channels: Input feature dimension
        out_channels: Output feature dimension
    """
    conv_type = conv_type.lower()
    if conv_type == "gcn":
        return GCNConv(in_channels, out_channels)
    elif conv_type == "gat":
        heads = kwargs.get("heads", 4)
        return GATConv(in_channels, out_channels // heads, heads=heads, concat=True)
    elif conv_type == "sage":
        return SAGEConv(in_channels, out_channels)
    else:
        raise ValueError(f"Unknown conv type: {conv_type}. Use 'gcn', 'gat', or 'sage'.")


def get_pool_fn(pool_type: str = "mean"):
    """Get a graph-level pooling function."""
    fns = {
        "mean": global_mean_pool,
        "max": global_max_pool,
        "add": global_add_pool,
        "sum": global_add_pool,
    }
    if pool_type not in fns:
        raise ValueError(f"Unknown pool type: {pool_type}. Use {list(fns.keys())}.")
    return fns[pool_type]


class GNNBranch(nn.Module):
    """
    A multi-layer GNN branch with batch norm and dropout.

    Used as a building block in BiGCN (one branch per direction) and
    as the full model in single-direction baselines.
    """

    def __init__(
        self,
        in_channels: int,
        hidden_channels: int,
        num_layers: int = 2,
        conv_type: str = "gcn",
        dropout: float = 0.5,
        use_bn: bool = True,
    ):
        super().__init__()
        self.convs = nn.ModuleList()
        self.bns = nn.ModuleList() if use_bn else None
        self.dropout = dropout
        self.num_layers = num_layers

        # First layer
        self.convs.append(get_conv_layer(conv_type, in_channels, hidden_channels))
        if use_bn:
            self.bns.append(nn.BatchNorm1d(hidden_channels))

        # Remaining layers
        for _ in range(num_layers - 1):
            self.convs.append(get_conv_layer(conv_type, hidden_channels, hidden_channels))
            if use_bn:
                self.bns.append(nn.BatchNorm1d(hidden_channels))

    def forward(self, x, edge_index):
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            if self.bns is not None:
                x = self.bns[i](x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
        return x


def init_weights(module):
    """Xavier uniform initialization for Linear and Conv layers."""
    if isinstance(module, nn.Linear):
        nn.init.xavier_uniform_(module.weight)
        if module.bias is not None:
            nn.init.zeros_(module.bias)
