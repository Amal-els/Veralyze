"""
Extension Bridge API

Provides a local HTTP webhook (`/analyze`) designed to catch pushed graphs
from the browser extension. Translates the shallow Document Object Model
payload into a PyG propagation tree, dynamically scores it via BiGCN,
and replies with the classification for the UI.
"""

import json
import logging
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from typing import Optional
from pathlib import Path

import torch
from torch_geometric.data import Data

from .bot_features import UserProfile, compute_bot_score, BotScore
from .spiderfoot_client import SpiderfootClient
from crawler.propagation_crawler import PropagationTree, PropagationNode
from data.feature_extractor import FeatureExtractor
from data.graph_builder import tree_dict_to_pyg

logger = logging.getLogger(__name__)

# Global state to hold inference dependencies
_GLOBAL_MODEL: Optional[torch.nn.Module] = None
_GLOBAL_EXTRACTOR: Optional[FeatureExtractor] = None
_GLOBAL_SPIDERFOOT: Optional[SpiderfootClient] = None
_GLOBAL_DEVICE: str = "cpu"
_GLOBAL_CHECKPOINT_PATH: Optional[str] = None


def _make_user_profile(author_dict: dict) -> UserProfile:
    """Mock a UserProfile out of limited extension data"""
    handle = author_dict.get("handle") or ""
    if handle.startswith("@"):
        handle = handle[1:]

    return UserProfile(
        user_id=handle or "unknown",
        username=handle,
        name=author_dict.get("name") or "",
        # Since we don't have these metrics deeply scraped, we leave them default (0)
        # However, bot_features heuristics will still evaluate entropy, etc.
    )


def payload_to_tree(payload: dict, enrich_osint: bool) -> PropagationTree:
    """Restructure the raw Extension payload into a PyG-ready PropagationTree"""
    # 1. Root Extraction
    post_block = payload.get("post") or {}
    author_block = payload.get("author") or {}
    eng_block = payload.get("engagement") or {}
    comments = payload.get("comments") or []
    
    root_handle = author_block.get("handle") or "root_unknown"
    root_id = f"tweet_{root_handle}_{int(time.time())}"
    
    tree = PropagationTree(root_id=root_id)
    
    # 2. Build Root Node
    root_profile = _make_user_profile(author_block)
    root_bot_score = compute_bot_score(root_profile)
    
    if enrich_osint and _GLOBAL_SPIDERFOOT and root_profile.username:
        root_bot_score.osint_score = _GLOBAL_SPIDERFOOT.scan_target(root_profile.username)
        
    root_node = PropagationNode(
        node_id=root_id,
        author_id=root_profile.username,
        text=post_block.get("text") or payload.get("text") or "",
        created_at=post_block.get("created_at") or datetime.now(timezone.utc).isoformat(),
        edge_type="root",
        depth=0,
        parent_id=None,
        user_profile={"username": root_profile.username},
        bot_score={"vector": root_bot_score.to_vector(), "aggregate": root_bot_score.aggregate},
        public_metrics=eng_block
    )
    tree.add_node(root_node)
    
    # 3. Build Comment Nodes
    for i, c in enumerate(comments):
        c_author = c.get("author") or {}
        c_profile = _make_user_profile(c_author)
        c_bot_score = compute_bot_score(c_profile)
        
        reply_id = f"reply_{i}_{c_profile.username}"
        
        node = PropagationNode(
            node_id=reply_id,
            author_id=c_profile.username,
            text=c.get("text") or "",
            created_at=datetime.now(timezone.utc).isoformat(),  # Time delta heuristic approx
            edge_type="reply",
            depth=1,
            parent_id=root_id,
            user_profile={"username": c_profile.username},
            bot_score={"vector": c_bot_score.to_vector(), "aggregate": c_bot_score.aggregate},
            public_metrics={"likes": c.get("reaction_count", 0)}
        )
        tree.add_node(node)
        tree.add_edge(root_id, reply_id, "reply")
        
    return tree


def evaluate_payload(payload: dict) -> dict:
    global _GLOBAL_MODEL, _GLOBAL_EXTRACTOR, _GLOBAL_DEVICE
    
    start_time = time.time()
    logger.info("Received new DOM payload from extension...")

    try:
        # Build logical Tree
        tree = payload_to_tree(payload, enrich_osint=(_GLOBAL_SPIDERFOOT is not None))
        
        # Save tree to disk automatically for visualization / training
        out_dir = Path("data/raw/crawled")
        out_dir.mkdir(parents=True, exist_ok=True)
        tree_path = out_dir / f"{tree.root_id}.json"
        tree.save(str(tree_path))
        logger.info(f"Saved tree to {tree_path}")
        
        # Lazy load extractor if missing
        if _GLOBAL_EXTRACTOR is None:
            logger.info("Lazy loading FeatureExtractor (includes heavy text model)...")
            _GLOBAL_EXTRACTOR = FeatureExtractor(use_text_embeddings=True)
            
        # Build raw Graph Data Object
        data = tree_dict_to_pyg(tree.to_dict(), label=0, feature_extractor=_GLOBAL_EXTRACTOR)
        data = data.to(_GLOBAL_DEVICE)
        data.batch = torch.zeros(data.num_nodes, dtype=torch.long, device=_GLOBAL_DEVICE)
        
        # BiGCN Inference (if model loaded or needs loading)
        prob_organic, prob_bot = 0.5, 0.5
        trustScore = 50.0  # By default fallback to 50 if model errors
        
        if _GLOBAL_MODEL is None and _GLOBAL_CHECKPOINT_PATH:
             _load_model_lazy()

        if _GLOBAL_MODEL is not None:
            with torch.no_grad():
                logits = _GLOBAL_MODEL(data)
                probs = torch.softmax(logits, dim=1)
                prob_organic = probs[0][0].item()
                prob_bot = probs[0][1].item()
                
            # Maps 0.0 -> 100.0 directly linking prob_organic to trust score.
            trustScore = prob_organic * 100.0

        elapsed = time.time() - start_time
        logger.info(f"Analyzed {tree.num_nodes} nodes in {elapsed:.2f}s | trust_score={trustScore:.1f}")

        # Map predictions to strict extension visualization schema
        if trustScore >= 70:
            verdict = "trusted"
            summary = "GNN Propagation structure resembles Organic sharing."
        elif trustScore >= 40:
            verdict = "uncertain"
            summary = "GNN Propagation structure shows mixed signals."
        else:
            verdict = "suspicious"
            summary = "GNN Propagation structure resembles Bot-like / Fake spreading patterns."

        nodes_data = []
        valid_node_ids = set()
        for n in tree.nodes.values():
            # Force ID to string and skip if empty
            if not n.node_id: continue
            node_id = str(n.node_id)
            
            nodes_data.append({
                "id": node_id,
                "label": str(n.author_id or "unknown"),
                "type": str(n.edge_type or "reply"),
                "score": float(n.bot_score.get("aggregate", 0.0)) if isinstance(n.bot_score, dict) else 0.0
            })
            valid_node_ids.add(node_id)
            
        edges_data = []
        for s, t, _ in tree.edges:
            # Force both to string
            s_id, t_id = str(s), str(t)
            if s_id in valid_node_ids and t_id in valid_node_ids:
                edges_data.append({
                    "source": s_id, 
                    "target": t_id
                })
            else:
                logger.warning(f"Dropping dangling edge: {s_id} -> {t_id}")
            else:
                logger.warning(f"Dropping dangling edge: {s_id} -> {t_id}")

        return {
            "trust_score": int(trustScore),
            "verdict": verdict,
            "summary_title": f"BiGCN: {verdict.title()} ({prob_organic:.1%} organic)",
            "explanation": f"{summary} Analyzed {tree.num_nodes} depth-1 propagation nodes.",
            "subscores": {
                "authenticity": int(prob_organic * 100),
                "context": int(prob_organic * 100),
                "source": int(prob_organic * 100),
            },
            "graph_nodes": nodes_data,
            "graph_edges": edges_data
        }
        
    except Exception as e:
        logger.exception("Failed to process payload through GNN.")
        return {"error": str(e), "trust_score": 0, "verdict": "suspicious"}


class ExtensionHTTPHandler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        self._send_response(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/ping":
            self._send_response(200, {"status": "ok", "service": "Propagation GNN Bridge"})
            return
        self._send_response(200, {"status": "ok", "service": "Propagation GNN Bridge"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/analyze", "/extract"):
            self._send_response(404, {"error": "Not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_response(400, {"error": "Invalid JSON"})
            return

        # Perform Graph Analysis
        response_json = evaluate_payload(payload)

        self._send_response(200, response_json)

    def log_message(self, format, *args):
        pass

    def _send_response(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _load_model_lazy():
    global _GLOBAL_MODEL, _GLOBAL_DEVICE, _GLOBAL_CHECKPOINT_PATH
    if not _GLOBAL_CHECKPOINT_PATH:
        return
    
    cp = Path(_GLOBAL_CHECKPOINT_PATH)
    if cp.exists():
        from training.train import build_model
        from training.config import TrainConfig
        
        logger.info(f"Loading BiGCN checkpoint from {cp}...")
        ckpt = torch.load(cp, map_location=_GLOBAL_DEVICE, weights_only=True)
        # Handle cases where config in checkpoint might have extra keys
        cfg_dict = {k: v for k, v in ckpt.get("config", {}).items() if k in TrainConfig.__dataclass_fields__}
        cfg = TrainConfig(**cfg_dict)
        _GLOBAL_MODEL = build_model(cfg, 407).to(_GLOBAL_DEVICE)
        _GLOBAL_MODEL.load_state_dict(ckpt["model_state_dict"])
        _GLOBAL_MODEL.eval()
        logger.info("BiGCN state ready.")
    else:
        logger.warning(f"Checkpoint not found at {_GLOBAL_CHECKPOINT_PATH}!")


def run_bridge_server(
    port: int = 8000,
    checkpoint_path: Optional[str] = None,
    enrich_osint: bool = False
):
    global _GLOBAL_MODEL, _GLOBAL_EXTRACTOR, _GLOBAL_DEVICE, _GLOBAL_SPIDERFOOT, _GLOBAL_CHECKPOINT_PATH
    
    _GLOBAL_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    _GLOBAL_CHECKPOINT_PATH = checkpoint_path
    
    # We do NOT load FeatureExtractor here anymore, it's lazy-loaded on first request
    
    if enrich_osint:
        _GLOBAL_SPIDERFOOT = SpiderfootClient()

    server = ThreadingHTTPServer(("", port), ExtensionHTTPHandler)
    logger.info("=========================================================")
    logger.info(f" 🚀 Extension Bridge Active @ http://localhost:{port}")
    logger.info(f" 🧠 OSINT Enrichment: {'[ON]' if enrich_osint else '[OFF]'}")
    logger.info(f" 📈 Inference Device: {_GLOBAL_DEVICE.upper()}")
    logger.info("=========================================================")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server terminated by user.")
        server.server_close()
