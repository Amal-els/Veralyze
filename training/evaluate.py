"""
Model evaluation utilities — metrics, confusion matrix, and visualization.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.loader import DataLoader
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


@torch.no_grad()
def evaluate_model(
    model: nn.Module,
    loader: DataLoader,
    device: str,
) -> Dict:
    """
    Evaluate a model on a dataset and compute comprehensive metrics.

    Returns:
        Dictionary with accuracy, precision, recall, f1, auc, confusion_matrix,
        and per-class classification report.
    """
    model.eval()
    all_preds = []
    all_labels = []
    all_probs = []

    for batch in loader:
        batch = batch.to(device)
        logits = model(batch)
        probs = torch.softmax(logits, dim=1)

        preds = logits.argmax(dim=1).cpu().numpy()
        labels = batch.y.cpu().numpy()

        all_preds.extend(preds)
        all_labels.extend(labels)
        all_probs.extend(probs.cpu().numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    all_probs = np.array(all_probs)

    # Core metrics
    metrics = {
        "accuracy": accuracy_score(all_labels, all_preds),
        "precision_macro": precision_score(all_labels, all_preds, average="macro", zero_division=0),
        "recall_macro": recall_score(all_labels, all_preds, average="macro", zero_division=0),
        "f1_macro": f1_score(all_labels, all_preds, average="macro", zero_division=0),
        "precision_per_class": precision_score(all_labels, all_preds, average=None, zero_division=0).tolist(),
        "recall_per_class": recall_score(all_labels, all_preds, average=None, zero_division=0).tolist(),
        "f1_per_class": f1_score(all_labels, all_preds, average=None, zero_division=0).tolist(),
        "confusion_matrix": confusion_matrix(all_labels, all_preds).tolist(),
        "classification_report": classification_report(
            all_labels, all_preds,
            target_names=["Real/Organic", "Fake/Bot-like"],
            zero_division=0,
        ),
        "predictions": all_preds,
        "labels": all_labels,
        "probabilities": all_probs,
    }

    # AUC (binary only)
    try:
        if all_probs.shape[1] == 2:
            metrics["auc"] = roc_auc_score(all_labels, all_probs[:, 1])
        else:
            metrics["auc"] = roc_auc_score(
                all_labels, all_probs, multi_class="ovr", average="macro"
            )
    except ValueError:
        metrics["auc"] = 0.0

    return metrics


def print_metrics(metrics: Dict):
    """Pretty-print evaluation metrics."""
    print(f"  Accuracy:   {metrics['accuracy']:.4f}")
    print(f"  Precision:  {metrics['precision_macro']:.4f} (macro)")
    print(f"  Recall:     {metrics['recall_macro']:.4f} (macro)")
    print(f"  F1 Score:   {metrics['f1_macro']:.4f} (macro)")
    print(f"  AUC:        {metrics['auc']:.4f}")
    print()
    print("  Classification Report:")
    for line in metrics["classification_report"].split("\n"):
        print(f"    {line}")
    print()
    cm = metrics["confusion_matrix"]
    print("  Confusion Matrix:")
    print(f"                   Pred Real  Pred Fake")
    print(f"    Actual Real:   {cm[0][0]:>8}   {cm[0][1]:>8}")
    print(f"    Actual Fake:   {cm[1][0]:>8}   {cm[1][1]:>8}")


@torch.no_grad()
def get_embeddings(
    model: nn.Module,
    loader: DataLoader,
    device: str,
) -> tuple:
    """
    Extract graph-level embeddings from the model for visualization.

    Returns:
        (embeddings: np.ndarray, labels: np.ndarray)
    """
    model.eval()
    all_embs = []
    all_labels = []

    for batch in loader:
        batch = batch.to(device)
        embs = model.get_embeddings(batch)
        all_embs.append(embs.cpu().numpy())
        all_labels.extend(batch.y.cpu().numpy())

    embeddings = np.vstack(all_embs)
    labels = np.array(all_labels)
    return embeddings, labels


def plot_confusion_matrix(metrics: Dict, save_path: Optional[str] = None):
    """Plot a styled confusion matrix."""
    import matplotlib.pyplot as plt
    import seaborn as sns

    cm = np.array(metrics["confusion_matrix"])
    fig, ax = plt.subplots(figsize=(6, 5))

    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=["Real/Organic", "Fake/Bot-like"],
        yticklabels=["Real/Organic", "Fake/Bot-like"],
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title("Confusion Matrix")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        logger.info(f"Confusion matrix saved → {save_path}")
    plt.show()


def plot_tsne(
    embeddings: np.ndarray,
    labels: np.ndarray,
    save_path: Optional[str] = None,
):
    """t-SNE visualization of graph embeddings."""
    import matplotlib.pyplot as plt
    from sklearn.manifold import TSNE

    logger.info("Computing t-SNE projection…")
    tsne = TSNE(n_components=2, random_state=42, perplexity=30)
    X_2d = tsne.fit_transform(embeddings)

    fig, ax = plt.subplots(figsize=(8, 6))

    colors = ["#2ecc71", "#e74c3c"]
    class_names = ["Real/Organic", "Fake/Bot-like"]

    for cls in range(2):
        mask = labels == cls
        ax.scatter(
            X_2d[mask, 0], X_2d[mask, 1],
            c=colors[cls], label=class_names[cls],
            alpha=0.6, s=15, edgecolors="none",
        )

    ax.legend(fontsize=11)
    ax.set_title("t-SNE of Graph Embeddings", fontsize=14)
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        logger.info(f"t-SNE plot saved → {save_path}")
    plt.show()
