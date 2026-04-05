# Propagation Graph GNN — Misinformation Detection

Detects **bot-like vs. organic** news spreading patterns using Graph Neural Networks on tweet propagation trees.

## Architecture

```
Root Tweet → Retweet → Comment → Reply → …
     ↓
  Propagation Tree (JSON)
     ↓
  PyG Data (node features + bidirectional edges)
     ↓
  BiGCN (top-down + bottom-up graph convolutions)
     ↓
  Classification: Organic 🟢  or  Bot-like 🔴
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** PyTorch and PyG installation depends on your CUDA version. See:
> - [PyTorch](https://pytorch.org/get-started/locally/)
> - [PyG](https://pytorch-geometric.readthedocs.io/en/latest/install/installation.html)

### 2. Train on UPFD benchmark (no API key needed)

```bash
# BiGCN on GossipCop with BERT features
python main.py train --model bigcn --dataset upfd --upfd-name gossipcop --feature bert --epochs 60

# GCNFN baseline on PolitiFact
python main.py train --model gcnfn --dataset upfd --upfd-name politifact --feature spacy
```

### 3. Crawl a tweet propagation tree (requires API key)

```bash
# Set your Twitter API bearer token
export TWITTER_BEARER_TOKEN=your_token

# Crawl
python main.py crawl --tweet-id 1234567890123456789 --output data/raw/crawled/
```

### 4. Predict on a crawled tree

```bash
python main.py predict --checkpoint checkpoints/best_bigcn_upfd.pt --tree-json data/raw/crawled/tree_1234567890123456789.json
```

### 5. Visualize a propagation tree

```bash
python main.py viz --tree-json data/raw/crawled/tree_1234567890123456789.json --show-text
```

## Project Structure

```
propagation/
├── crawler/                   # Twitter API crawler
│   ├── twitter_client.py      # API wrapper with rate limiting
│   ├── propagation_crawler.py # Tree builder (replies + RTs + quotes)
│   └── bot_features.py        # Bot-likelihood heuristic scorer
│
├── data/                      # Data pipeline
│   ├── feature_extractor.py   # Text + profile + temporal + bot features
│   ├── graph_builder.py       # Tree → PyG Data conversion
│   ├── dataset.py             # Custom PyG InMemoryDataset
│   └── upfd_loader.py         # UPFD benchmark loader
│
├── models/                    # GNN models
│   ├── base_gnn.py            # Shared convolution/pooling utilities
│   ├── bigcn.py               # BiGCN (bidirectional, SOTA)
│   └── gcnfn.py               # Single-direction GCN baseline
│
├── training/                  # Training & evaluation
│   ├── config.py              # Hyperparameter config
│   ├── train.py               # Training loop + early stopping
│   └── evaluate.py            # Metrics + visualization
│
├── utils/
│   └── visualization.py       # Propagation tree plotting
│
├── main.py                    # CLI entry point
├── requirements.txt
└── README.md
```

## Node Features (406 dimensions)

| Feature Group   | Dims | Description                                    |
|----------------|------|------------------------------------------------|
| Text embedding | 384  | MiniLM-L6-v2 sentence embedding                |
| User profile   | 10   | Followers, following, tweet count, verified, …  |
| Temporal        | 4    | Time delta, hour, day of week, reply speed      |
| Bot score       | 5    | Age, ratio, default profile, activity, entropy  |
| Edge type       | 3    | One-hot: reply / retweet / quote                |

## Models

### BiGCN (Recommended)
Bi-directional GCN that processes the propagation graph in two directions:
- **Top-down**: How information spreads from source
- **Bottom-up**: How users react back toward source

### GCNFN (Baseline)
Single-direction GCN using only propagation flow edges.

## References

- Bian et al., *"Rumor Detection on Social Media with Bi-Directional Graph Convolutional Networks"* (AAAI 2020)
- Dou et al., *"User Preference-aware Fake News Detection"* (SIGIR 2021) — UPFD dataset
- [GNN-FakeNews](https://github.com/safe-graph/GNN-FakeNews) repository
