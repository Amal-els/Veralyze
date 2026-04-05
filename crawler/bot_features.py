"""
Bot-likelihood heuristic scoring for Twitter user profiles.

Computes a multi-dimensional bot-score vector (5 features) based on
publicly available profile metadata. These scores are used as node
features in the propagation graph GNN.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class UserProfile:
    """Normalized representation of a Twitter user profile."""
    user_id: str
    username: str = ""
    name: str = ""
    followers_count: int = 0
    following_count: int = 0
    tweet_count: int = 0
    listed_count: int = 0
    verified: bool = False
    account_created_at: Optional[datetime] = None
    has_url: bool = False
    has_description: bool = False
    default_profile_image: bool = False
    description: str = ""
    profile_image_url: str = ""


@dataclass
class BotScore:
    """5-dimensional bot-likelihood score vector."""
    age_score: float = 0.0            # 0 = old account, 1 = very new
    ratio_score: float = 0.0          # 0 = balanced, 1 = extreme ratio
    default_profile_score: float = 0.0  # 1 = default image/no bio
    activity_score: float = 0.0       # 0 = normal, 1 = extreme posting rate
    username_entropy_score: float = 0.0  # 0 = readable, 1 = random chars
    osint_score: float = 0.0          # 0 = clean, 1 = malicious OSINT footprint

    def to_vector(self) -> list:
        return [
            self.age_score,
            self.ratio_score,
            self.default_profile_score,
            self.activity_score,
            self.username_entropy_score,
            self.osint_score,
        ]

    @property
    def aggregate(self) -> float:
        """Weighted mean — higher = more bot-like."""
        weights = [0.15, 0.15, 0.15, 0.20, 0.15, 0.20]
        return sum(w * s for w, s in zip(weights, self.to_vector()))


def compute_bot_score(profile: UserProfile) -> BotScore:
    """Compute heuristic bot-likelihood features from a user profile."""
    score = BotScore()

    # --- 1. Account age (newer = more suspicious) ---
    if profile.account_created_at:
        age_days = (datetime.now(timezone.utc) - profile.account_created_at).days
        # Sigmoid-like mapping: <30 days → ~1.0, >365 days → ~0.0
        score.age_score = 1.0 / (1.0 + math.exp(0.02 * (age_days - 90)))
    else:
        score.age_score = 0.5  # unknown

    # --- 2. Follower-to-following ratio ---
    following = max(profile.following_count, 1)
    followers = max(profile.followers_count, 1)
    ratio = following / followers
    # High ratio (follows many, few followers) → suspicious
    # Sigmoid: ratio > 10 → ~1.0, ratio ~1 → ~0.0
    score.ratio_score = 1.0 / (1.0 + math.exp(-0.5 * (ratio - 5)))

    # --- 3. Default profile (no customization) ---
    penalty = 0.0
    if profile.default_profile_image:
        penalty += 0.5
    if not profile.has_description:
        penalty += 0.3
    if not profile.has_url:
        penalty += 0.2
    score.default_profile_score = min(penalty, 1.0)

    # --- 4. Posting activity rate ---
    if profile.account_created_at:
        age_days = max((datetime.now(timezone.utc) - profile.account_created_at).days, 1)
        tweets_per_day = profile.tweet_count / age_days
        # >50 tweets/day is suspicious; sigmoid centered at 30
        score.activity_score = 1.0 / (1.0 + math.exp(-0.1 * (tweets_per_day - 30)))
    else:
        score.activity_score = 0.5

    # --- 5. Username entropy (random strings → high entropy) ---
    score.username_entropy_score = _username_entropy(profile.username)

    return score


def _username_entropy(username: str) -> float:
    """
    Score how 'random' a username looks.
    Uses character-level Shannon entropy + digit ratio as signals.
    Returns 0.0 (human-like) to 1.0 (random/bot-like).
    """
    if not username:
        return 0.5

    username = username.lower()

    # Character frequency entropy
    freq = {}
    for c in username:
        freq[c] = freq.get(c, 0) + 1
    n = len(username)
    entropy = -sum((count / n) * math.log2(count / n) for count in freq.values())

    # Normalize: max entropy for 36 chars (a-z0-9) is log2(36) ≈ 5.17
    norm_entropy = entropy / 5.17

    # Digit ratio — usernames with many digits tend to be generated
    digit_ratio = sum(1 for c in username if c.isdigit()) / max(n, 1)

    # Underscore/number suffix pattern (e.g., user_382847291)
    suffix_pattern = 1.0 if re.search(r"[_]\d{4,}$", username) else 0.0

    # Weighted combination
    combined = 0.4 * norm_entropy + 0.35 * digit_ratio + 0.25 * suffix_pattern
    return min(combined, 1.0)


def profile_from_tweepy_user(user) -> UserProfile:
    """Convert a tweepy User object to our UserProfile dataclass."""
    return UserProfile(
        user_id=str(user.id),
        username=user.username or "",
        name=user.name or "",
        followers_count=getattr(user, "public_metrics", {}).get("followers_count", 0)
            if hasattr(user, "public_metrics") and user.public_metrics else 0,
        following_count=getattr(user, "public_metrics", {}).get("following_count", 0)
            if hasattr(user, "public_metrics") and user.public_metrics else 0,
        tweet_count=getattr(user, "public_metrics", {}).get("tweet_count", 0)
            if hasattr(user, "public_metrics") and user.public_metrics else 0,
        listed_count=getattr(user, "public_metrics", {}).get("listed_count", 0)
            if hasattr(user, "public_metrics") and user.public_metrics else 0,
        verified=getattr(user, "verified", False) or False,
        account_created_at=user.created_at if hasattr(user, "created_at") else None,
        has_url=bool(getattr(user, "url", None)),
        has_description=bool(getattr(user, "description", None)),
        default_profile_image="default_profile" in (getattr(user, "profile_image_url", "") or ""),
        description=getattr(user, "description", "") or "",
        profile_image_url=getattr(user, "profile_image_url", "") or "",
    )
