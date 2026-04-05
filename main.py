"""
Propagation Graph GNN — CLI entry point.

Commands:
    crawl   — Crawl a tweet's propagation tree via Twitter API
    train   — Train a GNN model (UPFD benchmark or custom data)
    predict — Classify a crawled propagation tree
    viz     — Visualize a saved propagation tree
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s │ %(name)-20s │ %(levelname)-7s │ %(message)s",
        datefmt="%H:%M:%S",
    )


# ================================================================== #
#  CRAWL command                                                       #
# ================================================================== #

def cmd_listen(args):
    """Start local HTTP server to receive extension payloads."""
    from crawler.extension_bridge import run_bridge_server

    run_bridge_server(
        port=args.port,
        checkpoint_path=args.checkpoint,
        enrich_osint=args.enrich_osint
    )


# ================================================================== #
#  TRAIN command                                                       #
# ================================================================== #

def cmd_train(args):
    """Train a GNN model."""
    from training.config import TrainConfig
    from training.train import train

    config = TrainConfig(
        model=args.model,
        dataset=args.dataset,
        upfd_name=args.upfd_name,
        upfd_feature=args.feature,
        custom_data_dir=args.data_dir,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        dropout=args.dropout,
        lr=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.epochs,
        batch_size=args.batch_size,
        patience=args.patience,
        device=args.device,
        seed=args.seed,
        checkpoint_dir=args.checkpoint_dir,
    )

    model = train(config)
    print("\n  ✓ Training complete.")


# ================================================================== #
#  PREDICT command                                                     #
# ================================================================== #

def cmd_predict(args):
    """Predict whether a propagation tree is bot-like or organic."""
    import torch
    from data.graph_builder import tree_file_to_pyg
    from data.feature_extractor import FeatureExtractor
    from data.upfd_loader import get_upfd_feature_dim
    from training.config import TrainConfig

    # Load checkpoint
    checkpoint_path = Path(args.checkpoint)
    if not checkpoint_path.exists():
        print(f"  ✗ Checkpoint not found: {checkpoint_path}")
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=True)
    saved_config = checkpoint.get("config", {})

    # Rebuild model
    from training.train import build_model
    config = TrainConfig(**{k: v for k, v in saved_config.items() if k in TrainConfig.__dataclass_fields__})

    if config.dataset == "upfd":
        in_channels = get_upfd_feature_dim(config.upfd_feature)
    else:
        in_channels = 407  # custom feature dim

    model = build_model(config, in_channels).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    # Load and process the tree
    if args.tree_json:
        tree_path = Path(args.tree_json)
    elif args.tweet_id:
        # Crawl first
        from crawler.twitter_client import TwitterClient
        from crawler.propagation_crawler import PropagationCrawler

        client = TwitterClient()
        crawler = PropagationCrawler(client)
        tree = crawler.crawl(args.tweet_id)
        tree_path = Path(f"./tmp_tree_{args.tweet_id}.json")
        tree.save(str(tree_path))
    else:
        print("  ✗ Provide either --tree-json or --tweet-id")
        sys.exit(1)

    extractor = FeatureExtractor(use_text_embeddings=(config.dataset != "upfd"))
    data = tree_file_to_pyg(tree_path, label=0, feature_extractor=extractor)
    data = data.to(device)

    # Add batch dimension
    data.batch = torch.zeros(data.num_nodes, dtype=torch.long, device=device)

    with torch.no_grad():
        logits = model(data)
        probs = torch.softmax(logits, dim=1)
        pred = logits.argmax(dim=1).item()

    labels = ["Real / Organic 🟢", "Fake / Bot-like 🔴"]
    print(f"\n  Prediction: {labels[pred]}")
    print(f"  Confidence: {probs[0][pred]:.2%}")
    print(f"  Probabilities: Real={probs[0][0]:.4f}  Fake={probs[0][1]:.4f}")


# ================================================================== #
#  VIZ command                                                         #
# ================================================================== #

def cmd_viz(args):
    """Visualize a saved propagation tree using the interactive 3D explorer."""
    from utils.viz_server import launch_interactive_viz

    tree_path = Path(args.tree_json)
    if not tree_path.exists():
        print(f"  ✗ Tree file not found: {tree_path}")
        sys.exit(1)

    with open(tree_path, "r") as f:
        tree_dict = json.load(f)

    # Launch the interactive 3D web-based explorer
    launch_interactive_viz(tree_dict)


# ================================================================== #
#  Argument parser                                                     #
# ================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description="Propagation Graph GNN — Misinformation Detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── listen ──
    p_listen = subparsers.add_parser("listen", help="Start extension bridge to receive DOM-scraped trees")
    p_listen.add_argument("--port", type=int, default=8000)
    p_listen.add_argument("--checkpoint", type=str, help="Path to best_model.pt for live inference")
    p_listen.add_argument("--enrich-osint", action="store_true", help="Launch SpiderFoot for OSINT enrichment")
    p_listen.set_defaults(func=cmd_listen)

    # ── train ──
    p_train = subparsers.add_parser("train", help="Train GNN model")
    p_train.add_argument("--model", default="bigcn", choices=["bigcn", "gcnfn"])
    p_train.add_argument("--dataset", default="upfd", choices=["upfd", "custom"])
    p_train.add_argument("--upfd-name", default="gossipcop", choices=["politifact", "gossipcop"])
    p_train.add_argument("--feature", default="bert", choices=["bert", "spacy", "profile", "content"])
    p_train.add_argument("--data-dir", default="./dataset", help="Custom data directory")
    p_train.add_argument("--hidden-dim", type=int, default=128)
    p_train.add_argument("--num-layers", type=int, default=2)
    p_train.add_argument("--dropout", type=float, default=0.5)
    p_train.add_argument("--lr", type=float, default=0.01)
    p_train.add_argument("--weight-decay", type=float, default=0.001)
    p_train.add_argument("--epochs", type=int, default=60)
    p_train.add_argument("--batch-size", type=int, default=128)
    p_train.add_argument("--patience", type=int, default=10)
    p_train.add_argument("--device", default="auto")
    p_train.add_argument("--seed", type=int, default=42)
    p_train.add_argument("--checkpoint-dir", default="./checkpoints")
    p_train.set_defaults(func=cmd_train)

    # ── predict ──
    p_pred = subparsers.add_parser("predict", help="Classify a propagation tree")
    p_pred.add_argument("--checkpoint", required=True, help="Model checkpoint path")
    p_pred.add_argument("--tree-json", help="Path to saved tree JSON")
    p_pred.add_argument("--tweet-id", help="Tweet ID (will crawl first)")
    p_pred.set_defaults(func=cmd_predict)

    # ── viz ──
    p_viz = subparsers.add_parser("viz", help="Visualize a propagation tree")
    p_viz.add_argument("--tree-json", required=True, help="Path to saved tree JSON")
    p_viz.add_argument("--save", help="Save plot to file")
    p_viz.add_argument("--show-text", action="store_true", help="Show tweet text on nodes")
    p_viz.set_defaults(func=cmd_viz)

    # Parse and dispatch
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
