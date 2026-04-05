"""
Visualization utilities for propagation graphs.

Provides functions to:
  - Plot propagation trees with networkx + matplotlib
  - Color nodes by edge type and size by bot-score
  - Visualize graph statistics
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Union

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)

# Color scheme for edge types
EDGE_TYPE_COLORS = {
    "root": "#f39c12",     # amber
    "reply": "#3498db",    # blue
    "retweet": "#2ecc71",  # green
    "quote": "#e67e22",    # orange
}

EDGE_TYPE_EDGE_COLORS = {
    "reply": "#85c1e9",
    "retweet": "#82e0aa",
    "quote": "#f0b27a",
}


def plot_propagation_tree(
    tree_dict: dict,
    title: str = "Propagation Tree",
    save_path: Optional[str] = None,
    figsize: tuple = (14, 10),
    show_text: bool = False,
):
    """
    Visualize a propagation tree as a network graph.

    Args:
        tree_dict: Serialized PropagationTree dict (from .to_dict())
        title: Plot title
        save_path: Optional path to save the figure
        figsize: Figure size
        show_text: Whether to annotate nodes with truncated tweet text
    """
    G = nx.DiGraph()

    nodes = tree_dict.get("nodes", {})
    edges = tree_dict.get("edges", [])

    # Add nodes
    for node_id, node_data in nodes.items():
        G.add_node(
            node_id,
            edge_type=node_data.get("edge_type", "root"),
            depth=node_data.get("depth", 0),
            text=node_data.get("text", "")[:40],
            bot_score=_get_bot_aggregate(node_data),
        )

    # Add edges
    for edge in edges:
        G.add_edge(
            edge["parent"], edge["child"],
            edge_type=edge.get("type", "reply"),
        )

    if len(G.nodes) == 0:
        logger.warning("Empty graph — nothing to plot.")
        return

    # Layout: hierarchical tree layout
    try:
        pos = _hierarchical_layout(G, tree_dict.get("root_id", list(nodes.keys())[0]))
    except Exception:
        pos = nx.spring_layout(G, k=2.0, iterations=50, seed=42)

    fig, ax = plt.subplots(figsize=figsize)

    # Draw edges colored by type
    for u, v, data in G.edges(data=True):
        etype = data.get("edge_type", "reply")
        color = EDGE_TYPE_EDGE_COLORS.get(etype, "#cccccc")
        nx.draw_networkx_edges(
            G, pos, edgelist=[(u, v)],
            edge_color=color, arrows=True,
            arrowsize=12, width=1.5, alpha=0.7,
            ax=ax,
        )

    # Draw nodes colored by edge type, sized by bot-score
    for node_id in G.nodes:
        node_data = G.nodes[node_id]
        etype = node_data.get("edge_type", "root")
        color = EDGE_TYPE_COLORS.get(etype, "#95a5a6")
        bot_score = node_data.get("bot_score", 0.3)
        size = 200 + bot_score * 600  # 200..800

        nx.draw_networkx_nodes(
            G, pos, nodelist=[node_id],
            node_color=color, node_size=size,
            edgecolors="#2c3e50", linewidths=1.0,
            alpha=0.85, ax=ax,
        )

    # Labels
    if show_text:
        labels = {nid: G.nodes[nid].get("text", "")[:20] for nid in G.nodes}
        nx.draw_networkx_labels(
            G, pos, labels, font_size=7, font_color="#2c3e50", ax=ax
        )

    # Legend
    legend_patches = [
        mpatches.Patch(color=EDGE_TYPE_COLORS["root"], label="Root tweet"),
        mpatches.Patch(color=EDGE_TYPE_COLORS["reply"], label="Reply"),
        mpatches.Patch(color=EDGE_TYPE_COLORS["retweet"], label="Retweet"),
        mpatches.Patch(color=EDGE_TYPE_COLORS["quote"], label="Quote"),
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=10)

    # Metadata
    n_nodes = len(G.nodes)
    n_edges = len(G.edges)
    max_depth = max((G.nodes[n].get("depth", 0) for n in G.nodes), default=0)
    ax.set_title(f"{title}\n{n_nodes} nodes · {n_edges} edges · depth {max_depth}", fontsize=13)
    ax.axis("off")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info(f"Propagation tree plot saved → {save_path}")
    plt.show()


def plot_graph_stats(tree_dicts: list, save_path: Optional[str] = None):
    """
    Plot statistics across multiple propagation trees:
    - Node count distribution
    - Depth distribution
    - Edge type distribution
    - Bot score distribution
    """
    node_counts = []
    depths = []
    edge_types = {"reply": 0, "retweet": 0, "quote": 0}
    bot_scores = []

    for tree in tree_dicts:
        nodes = tree.get("nodes", {})
        edges = tree.get("edges", [])
        node_counts.append(len(nodes))

        for node_data in nodes.values():
            depths.append(node_data.get("depth", 0))
            bs = _get_bot_aggregate(node_data)
            bot_scores.append(bs)

        for edge in edges:
            etype = edge.get("type", "reply")
            if etype in edge_types:
                edge_types[etype] += 1

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Node count distribution
    axes[0, 0].hist(node_counts, bins=30, color="#3498db", edgecolor="white", alpha=0.8)
    axes[0, 0].set_title("Nodes per Graph")
    axes[0, 0].set_xlabel("Node count")
    axes[0, 0].set_ylabel("Frequency")

    # Depth distribution
    axes[0, 1].hist(depths, bins=max(depths) + 1 if depths else 10,
                     color="#2ecc71", edgecolor="white", alpha=0.8)
    axes[0, 1].set_title("Node Depth Distribution")
    axes[0, 1].set_xlabel("Depth")

    # Edge type breakdown
    types = list(edge_types.keys())
    counts = list(edge_types.values())
    colors = [EDGE_TYPE_COLORS.get(t, "#95a5a6") for t in types]
    axes[1, 0].bar(types, counts, color=colors, edgecolor="white")
    axes[1, 0].set_title("Edge Type Distribution")

    # Bot score distribution
    axes[1, 1].hist(bot_scores, bins=30, color="#e74c3c", edgecolor="white", alpha=0.8)
    axes[1, 1].set_title("Bot Score Distribution")
    axes[1, 1].set_xlabel("Aggregate bot score")

    plt.suptitle(f"Dataset Statistics ({len(tree_dicts)} graphs)", fontsize=14)
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info(f"Graph stats plot saved → {save_path}")
    plt.show()


def _get_bot_aggregate(node_data: dict) -> float:
    """Extract aggregate bot score from a node data dict."""
    bot = node_data.get("bot_score")
    if bot and isinstance(bot, dict):
        return bot.get("aggregate", 0.3)
    return 0.3


def _hierarchical_layout(G: nx.DiGraph, root_id: str) -> dict:
    """
    Compute a top-down hierarchical layout for a tree graph.
    Falls back to spring layout if the graph is not a tree.
    """
    # Find root node key
    root_key = None
    for n in G.nodes:
        if root_id in str(n):
            root_key = n
            break
    if root_key is None:
        root_key = list(G.nodes)[0]

    # BFS to assign layers
    pos = {}
    visited = set()
    queue = [(root_key, 0)]
    layers = {}

    while queue:
        node, depth = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)

        if depth not in layers:
            layers[depth] = []
        layers[depth].append(node)

        for child in G.successors(node):
            if child not in visited:
                queue.append((child, depth + 1))

    # Also handle disconnected nodes
    for node in G.nodes:
        if node not in visited:
            depth = max(layers.keys(), default=0) + 1
            if depth not in layers:
                layers[depth] = []
            layers[depth].append(node)

    # Position: spread horizontally within each layer
    max_width = max(len(v) for v in layers.values()) if layers else 1
    for depth, layer_nodes in layers.items():
        n = len(layer_nodes)
        for i, node in enumerate(layer_nodes):
            x = (i - (n - 1) / 2) * (max_width / max(n, 1))
            y = -depth * 2  # top-to-bottom
            pos[node] = (x, y)

    return pos
