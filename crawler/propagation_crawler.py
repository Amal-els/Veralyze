"""
Propagation tree crawler: orchestrates multi-hop crawling of tweet
conversation threads, retweets, and quote tweets to build a full
propagation tree structure.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .twitter_client import TwitterClient
from .spiderfoot_client import SpiderfootClient
from .bot_features import (
    UserProfile,
    BotScore,
    compute_bot_score,
    profile_from_tweepy_user,
)

logger = logging.getLogger(__name__)


@dataclass
class PropagationNode:
    """A single node in the propagation tree."""
    node_id: str                          # unique id (tweet_id or user_id for retweets)
    tweet_id: Optional[str] = None
    author_id: Optional[str] = None
    text: str = ""
    created_at: Optional[str] = None       # ISO format string
    edge_type: str = "root"                # root | reply | retweet | quote
    depth: int = 0
    parent_id: Optional[str] = None        # node_id of parent
    user_profile: Optional[dict] = None    # serialized UserProfile
    bot_score: Optional[dict] = None       # serialized BotScore vector
    public_metrics: Optional[dict] = None  # likes, retweets, replies, quotes


@dataclass
class PropagationTree:
    """
    Tree-structured propagation graph.
    Nodes are tweets/users; edges represent reply/retweet/quote relationships.
    """
    root_id: str
    nodes: Dict[str, PropagationNode] = field(default_factory=dict)
    edges: List[tuple] = field(default_factory=list)  # (parent_id, child_id, edge_type)

    def add_node(self, node: PropagationNode):
        self.nodes[node.node_id] = node

    def add_edge(self, parent_id: str, child_id: str, edge_type: str):
        self.edges.append((parent_id, child_id, edge_type))

    @property
    def num_nodes(self) -> int:
        return len(self.nodes)

    @property
    def num_edges(self) -> int:
        return len(self.edges)

    def get_edges_top_down(self) -> List[tuple]:
        """Edges in propagation direction: parent → child."""
        return [(p, c) for p, c, _ in self.edges]

    def get_edges_bottom_up(self) -> List[tuple]:
        """Reversed edges: child → parent."""
        return [(c, p) for p, c, _ in self.edges]

    def to_dict(self) -> dict:
        return {
            "root_id": self.root_id,
            "num_nodes": self.num_nodes,
            "num_edges": self.num_edges,
            "nodes": {k: asdict(v) for k, v in self.nodes.items()},
            "edges": [
                {"parent": p, "child": c, "type": t} for p, c, t in self.edges
            ],
        }

    def save(self, path: str):
        """Save tree to JSON file."""
        filepath = Path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info(f"Saved propagation tree ({self.num_nodes} nodes) → {filepath}")

    @classmethod
    def load(cls, path: str) -> "PropagationTree":
        """Load tree from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tree = cls(root_id=data["root_id"])
        for node_id, node_data in data["nodes"].items():
            tree.add_node(PropagationNode(**node_data))
        for edge in data["edges"]:
            tree.add_edge(edge["parent"], edge["child"], edge["type"])
        return tree


class PropagationCrawler:
    """
    Crawls a tweet's propagation chain via the Twitter API v2.

    Builds a PropagationTree by:
    1. Fetching the root tweet
    2. Searching conversation_id for all replies (with parent linking)
    3. Fetching retweeters for the root
    4. Fetching quote tweets for the root
    """

    def __init__(self, client: Optional[TwitterClient] = None, enrich_osint: bool = False):
        self.client = client or TwitterClient()
        self._user_cache: Dict[str, UserProfile] = {}
        self.enrich_osint = enrich_osint
        self.spiderfoot = SpiderfootClient() if enrich_osint else None

    def crawl(
        self,
        root_tweet_id: str,
        include_retweets: bool = True,
        include_quotes: bool = True,
        max_conversation_tweets: int = 500,
        max_retweeters: int = 100,
        max_quotes: int = 100,
    ) -> PropagationTree:
        """
        Crawl the full propagation tree for a given root tweet.

        Args:
            root_tweet_id: ID of the source tweet
            include_retweets: Whether to crawl retweeters
            include_quotes: Whether to crawl quote tweets
            max_conversation_tweets: Max replies to fetch
            max_retweeters: Max retweeter users to fetch
            max_quotes: Max quote tweets to fetch

        Returns:
            PropagationTree with all nodes and edges
        """
        tree = PropagationTree(root_id=root_tweet_id)

        # Step 1: Fetch root tweet
        logger.info(f"Crawling propagation for tweet {root_tweet_id}…")
        root_resp = self.client.get_tweet(root_tweet_id)
        if not root_resp or not root_resp.data:
            logger.error(f"Could not fetch root tweet {root_tweet_id}")
            return tree

        root_tweet = root_resp.data

        # Cache users from includes
        if root_resp.includes and "users" in root_resp.includes:
            for user in root_resp.includes["users"]:
                profile = profile_from_tweepy_user(user)
                self._user_cache[profile.user_id] = profile

        # Create root node
        root_node = self._make_node(
            tweet=root_tweet, edge_type="root", depth=0, parent_id=None
        )
        tree.add_node(root_node)

        # Step 2: Fetch conversation (replies)
        conversation_id = str(root_tweet.conversation_id or root_tweet_id)
        conv_tweets, conv_users = self.client.get_conversation(
            conversation_id, max_results=max_conversation_tweets
        )

        # Cache users
        for uid, user in conv_users.items():
            profile = profile_from_tweepy_user(user)
            self._user_cache[profile.user_id] = profile

        # Build reply nodes and link to parents
        for tweet in conv_tweets:
            parent_tweet_id = self._find_parent(tweet)
            parent_node_id = f"tweet_{parent_tweet_id}" if parent_tweet_id else root_node.node_id

            node = self._make_node(
                tweet=tweet,
                edge_type="reply",
                depth=self._get_depth(tree, parent_node_id) + 1,
                parent_id=parent_node_id,
            )
            tree.add_node(node)
            tree.add_edge(parent_node_id, node.node_id, "reply")

        # Step 3: Fetch retweeters
        if include_retweets:
            retweeters = self.client.get_retweeters(
                root_tweet_id, max_results=max_retweeters
            )
            for user in retweeters:
                profile = profile_from_tweepy_user(user)
                self._user_cache[profile.user_id] = profile
                bot = compute_bot_score(profile)
                
                if self.enrich_osint and self.spiderfoot and profile.username:
                    bot.osint_score = self.spiderfoot.scan_target(profile.username)

                node = PropagationNode(
                    node_id=f"rt_{user.id}",
                    author_id=str(user.id),
                    text="[RETWEET]",
                    edge_type="retweet",
                    depth=1,
                    parent_id=root_node.node_id,
                    user_profile=self._profile_dict(profile),
                    bot_score={"vector": bot.to_vector(), "aggregate": bot.aggregate},
                )
                tree.add_node(node)
                tree.add_edge(root_node.node_id, node.node_id, "retweet")

        # Step 4: Fetch quote tweets
        if include_quotes:
            quotes = self.client.get_quote_tweets(
                root_tweet_id, max_results=max_quotes
            )
            for tweet in quotes:
                node = self._make_node(
                    tweet=tweet,
                    edge_type="quote",
                    depth=1,
                    parent_id=root_node.node_id,
                )
                tree.add_node(node)
                tree.add_edge(root_node.node_id, node.node_id, "quote")

        logger.info(
            f"Crawl complete: {tree.num_nodes} nodes, {tree.num_edges} edges"
        )
        return tree

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _make_node(self, tweet, edge_type: str, depth: int, parent_id: Optional[str]) -> PropagationNode:
        """Create a PropagationNode from a tweepy Tweet object."""
        author_id = str(tweet.author_id) if tweet.author_id else None
        profile = self._user_cache.get(author_id)
        if profile:
            bot = compute_bot_score(profile)
            if self.enrich_osint and self.spiderfoot and profile.username:
                bot.osint_score = self.spiderfoot.scan_target(profile.username)
        else:
            bot = None

        metrics = None
        if hasattr(tweet, "public_metrics") and tweet.public_metrics:
            metrics = dict(tweet.public_metrics)

        return PropagationNode(
            node_id=f"tweet_{tweet.id}",
            tweet_id=str(tweet.id),
            author_id=author_id,
            text=tweet.text or "",
            created_at=tweet.created_at.isoformat() if tweet.created_at else None,
            edge_type=edge_type,
            depth=depth,
            parent_id=parent_id,
            user_profile=self._profile_dict(profile) if profile else None,
            bot_score={"vector": bot.to_vector(), "aggregate": bot.aggregate} if bot else None,
            public_metrics=metrics,
        )

    def _find_parent(self, tweet) -> Optional[str]:
        """Find the parent tweet ID from referenced_tweets."""
        if tweet.referenced_tweets:
            for ref in tweet.referenced_tweets:
                if ref.type == "replied_to":
                    return str(ref.id)
        return None

    def _get_depth(self, tree: PropagationTree, node_id: str) -> int:
        """Get depth of a node in the tree, defaulting to 0."""
        if node_id in tree.nodes:
            return tree.nodes[node_id].depth
        return 0

    def _profile_dict(self, profile: UserProfile) -> dict:
        """Serialize a UserProfile for JSON storage."""
        return {
            "user_id": profile.user_id,
            "username": profile.username,
            "followers_count": profile.followers_count,
            "following_count": profile.following_count,
            "tweet_count": profile.tweet_count,
            "listed_count": profile.listed_count,
            "verified": profile.verified,
            "account_created_at": profile.account_created_at.isoformat()
                if profile.account_created_at else None,
            "has_url": profile.has_url,
            "has_description": profile.has_description,
            "default_profile_image": profile.default_profile_image,
        }
