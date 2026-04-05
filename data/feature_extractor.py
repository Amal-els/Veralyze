"""
Feature extractor: converts raw node data into fixed-size numerical
feature vectors for GNN input.

Feature dimensions:
  - Text embedding:  384  (MiniLM-L6-v2)
  - User profile:     10  (normalized account stats)
  - Temporal:          4  (time deltas and patterns)
  - Bot score:         6  (heuristic signals + OSINT)
  - Edge type:         3  (one-hot: reply/retweet/quote)
  ─────────────────────────
  Total:             407
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded sentence transformer (heavy import)
_sentence_model = None


def _get_sentence_model():
    global _sentence_model
    if _sentence_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading sentence-transformers model (first time only)…")
        _sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _sentence_model


class FeatureExtractor:
    """
    Extracts a fixed-size feature vector per propagation node.

    Supports two modes:
    - Full mode (with text embeddings): 406 dims
    - Profile-only mode (no text model): 22 dims
    """

    def __init__(self, use_text_embeddings: bool = True):
        self.use_text = use_text_embeddings
        self.text_dim = 384 if use_text_embeddings else 0
        self.profile_dim = 10
        self.temporal_dim = 4
        self.bot_dim = 6
        self.edge_type_dim = 3
        self.total_dim = (
            self.text_dim + self.profile_dim + self.temporal_dim
            + self.bot_dim + self.edge_type_dim
        )

    def extract_single(
        self,
        text: str = "",
        user_profile: Optional[dict] = None,
        bot_score: Optional[dict] = None,
        created_at: Optional[str] = None,
        root_created_at: Optional[str] = None,
        edge_type: str = "root",
    ) -> np.ndarray:
        """Extract feature vector for a single node."""
        parts = []

        # 1. Text embedding (384d)
        if self.use_text:
            parts.append(self._text_features(text))

        # 2. User profile (10d)
        parts.append(self._profile_features(user_profile))

        # 3. Temporal features (4d)
        parts.append(self._temporal_features(created_at, root_created_at))

        # 4. Bot score (5d)
        parts.append(self._bot_features(bot_score))

        # 5. Edge type one-hot (3d)
        parts.append(self._edge_type_features(edge_type))

        return np.concatenate(parts).astype(np.float32)

    def extract_batch(self, nodes: list, root_created_at: Optional[str] = None) -> np.ndarray:
        """
        Extract features for all nodes in a propagation tree.

        Args:
            nodes: list of dicts with keys matching PropagationNode fields
            root_created_at: ISO timestamp of the root tweet

        Returns:
            np.ndarray of shape [num_nodes, feature_dim]
        """
        # Batch text embedding for efficiency
        if self.use_text:
            texts = [n.get("text", "") or "" for n in nodes]
            text_embeddings = self._batch_text_features(texts)
        else:
            text_embeddings = [np.array([])] * len(nodes)

        features = []
        for i, node in enumerate(nodes):
            parts = []

            if self.use_text:
                parts.append(text_embeddings[i])

            parts.append(self._profile_features(node.get("user_profile")))
            parts.append(
                self._temporal_features(node.get("created_at"), root_created_at)
            )
            parts.append(self._bot_features(node.get("bot_score")))
            parts.append(self._edge_type_features(node.get("edge_type", "root")))

            features.append(np.concatenate(parts).astype(np.float32))

        return np.stack(features)

    # ------------------------------------------------------------------ #
    #  Feature group extractors                                           #
    # ------------------------------------------------------------------ #

    def _text_features(self, text: str) -> np.ndarray:
        """Encode text into 384d embedding."""
        if not text:
            return np.zeros(384, dtype=np.float32)
        model = _get_sentence_model()
        return model.encode(text, show_progress_bar=False).astype(np.float32)

    def _batch_text_features(self, texts: List[str]) -> np.ndarray:
        """Batch-encode multiple texts."""
        model = _get_sentence_model()
        # Replace empty strings with a placeholder
        clean = [t if t else "[empty]" for t in texts]
        embeddings = model.encode(clean, show_progress_bar=False, batch_size=64)
        return embeddings.astype(np.float32)

    def _profile_features(self, profile: Optional[dict]) -> np.ndarray:
        """
        10d user profile features (log-normalized counts + booleans).
        """
        if not profile:
            return np.zeros(self.profile_dim, dtype=np.float32)

        return np.array([
            _log_norm(profile.get("followers_count", 0)),
            _log_norm(profile.get("following_count", 0)),
            _log_norm(profile.get("tweet_count", 0)),
            _log_norm(profile.get("listed_count", 0)),
            1.0 if profile.get("verified") else 0.0,
            _account_age_norm(profile.get("account_created_at")),
            1.0 if profile.get("has_url") else 0.0,
            1.0 if profile.get("has_description") else 0.0,
            1.0 if profile.get("default_profile_image") else 0.0,
            _log_norm(profile.get("tweet_count", 0)),  # statuses (duplicate but useful)
        ], dtype=np.float32)

    def _temporal_features(
        self, created_at: Optional[str], root_created_at: Optional[str]
    ) -> np.ndarray:
        """
        4d temporal features:
        [time_delta_seconds, hour_of_day, day_of_week, reply_speed_normalized]
        """
        feat = np.zeros(self.temporal_dim, dtype=np.float32)

        if not created_at:
            return feat

        try:
            ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return feat

        feat[1] = ts.hour / 23.0      # hour normalized to [0, 1]
        feat[2] = ts.weekday() / 6.0   # day normalized to [0, 1]

        if root_created_at:
            try:
                root_ts = datetime.fromisoformat(
                    root_created_at.replace("Z", "+00:00")
                )
                delta = (ts - root_ts).total_seconds()
                feat[0] = _log_norm(max(delta, 0))   # log-norm time delta
                # Reply speed: fast reply → higher value
                feat[3] = 1.0 / (1.0 + delta / 3600.0) if delta >= 0 else 0.0
            except (ValueError, AttributeError):
                pass

        return feat

    def _bot_features(self, bot_score: Optional[dict]) -> np.ndarray:
        """5d bot-score vector."""
        if not bot_score:
            return np.full(self.bot_dim, 0.5, dtype=np.float32)  # unknown → 0.5
        vector = bot_score.get("vector", [0.5] * self.bot_dim)
        return np.array(vector[:self.bot_dim], dtype=np.float32)

    def _edge_type_features(self, edge_type: str) -> np.ndarray:
        """3d one-hot encoding of edge type."""
        mapping = {"reply": 0, "retweet": 1, "quote": 2}
        vec = np.zeros(self.edge_type_dim, dtype=np.float32)
        if edge_type in mapping:
            vec[mapping[edge_type]] = 1.0
        # root gets all-zeros (it's the source, not a propagation edge)
        return vec


# ------------------------------------------------------------------ #
#  Utility functions                                                   #
# ------------------------------------------------------------------ #

def _log_norm(value: float, base: float = 10.0) -> float:
    """Log-normalize a count to roughly [0, 1] range."""
    import math
    return math.log1p(abs(value)) / math.log1p(1e7)  # ~16.1 at 10M


def _account_age_norm(created_at_str: Optional[str]) -> float:
    """Normalize account age to [0, 1]. 0=brand new, 1=very old."""
    if not created_at_str:
        return 0.5
    try:
        created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - created).days
        return min(age_days / 3650.0, 1.0)  # cap at ~10 years
    except (ValueError, AttributeError):
        return 0.5
