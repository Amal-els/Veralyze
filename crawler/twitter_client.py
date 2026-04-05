"""
Twitter/X API v2 client wrapper for crawling propagation graphs.
Uses tweepy with automatic rate-limit handling.
"""

import os
import time
import logging
from typing import Optional

import tweepy
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Full set of tweet fields we request from the API
TWEET_FIELDS = [
    "author_id",
    "conversation_id",
    "created_at",
    "in_reply_to_user_id",
    "referenced_tweets",
    "public_metrics",
    "lang",
    "source",
]

USER_FIELDS = [
    "created_at",
    "description",
    "public_metrics",
    "profile_image_url",
    "verified",
    "url",
    "username",
    "name",
]

EXPANSIONS = ["author_id", "referenced_tweets.id"]


class TwitterClient:
    """Thin wrapper around tweepy.Client with rate-limit handling."""

    def __init__(self, bearer_token: Optional[str] = None, max_retries: int = 3):
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")
        if not self.bearer_token:
            raise ValueError(
                "Twitter Bearer Token is required. Set TWITTER_BEARER_TOKEN "
                "in your .env file or pass it directly."
            )
        self.client = tweepy.Client(
            bearer_token=self.bearer_token,
            wait_on_rate_limit=True,  # tweepy handles 429s automatically
        )
        self.max_retries = max_retries

    def _retry(self, fn, *args, **kwargs):
        """Execute a tweepy call with exponential backoff on transient errors."""
        for attempt in range(1, self.max_retries + 1):
            try:
                return fn(*args, **kwargs)
            except tweepy.TooManyRequests:
                wait = 2**attempt * 15  # 30s, 60s, 120s
                logger.warning(f"Rate limited. Waiting {wait}s (attempt {attempt})…")
                time.sleep(wait)
            except tweepy.TwitterServerError as e:
                logger.warning(f"Server error {e}. Retrying ({attempt})…")
                time.sleep(5)
        logger.error(f"Failed after {self.max_retries} retries.")
        return None

    # ------------------------------------------------------------------ #
    #  Core API methods                                                    #
    # ------------------------------------------------------------------ #

    def get_tweet(self, tweet_id: str):
        """Fetch a single tweet with full metadata."""
        resp = self._retry(
            self.client.get_tweet,
            tweet_id,
            tweet_fields=TWEET_FIELDS,
            user_fields=USER_FIELDS,
            expansions=EXPANSIONS,
        )
        if resp and resp.data:
            return resp
        return None

    def get_conversation(self, conversation_id: str, max_results: int = 500):
        """
        Fetch all tweets in a conversation thread via paginated search.
        Uses `conversation_id:{id}` query on the recent-search endpoint.
        """
        query = f"conversation_id:{conversation_id}"
        tweets = []
        includes_users = {}

        for response in tweepy.Paginator(
            self.client.search_recent_tweets,
            query=query,
            tweet_fields=TWEET_FIELDS,
            user_fields=USER_FIELDS,
            expansions=EXPANSIONS,
            max_results=100,  # API max per page
        ):
            if response.data:
                tweets.extend(response.data)
            # Collect user objects from includes
            if response.includes and "users" in response.includes:
                for user in response.includes["users"]:
                    includes_users[user.id] = user
            if len(tweets) >= max_results:
                break

        logger.info(f"Fetched {len(tweets)} tweets for conversation {conversation_id}")
        return tweets, includes_users

    def get_retweeters(self, tweet_id: str, max_results: int = 100):
        """Get users who retweeted a specific tweet."""
        resp = self._retry(
            self.client.get_retweeters,
            tweet_id,
            user_fields=USER_FIELDS,
            max_results=min(max_results, 100),
        )
        if resp and resp.data:
            return resp.data
        return []

    def get_quote_tweets(self, tweet_id: str, max_results: int = 100):
        """Get quote tweets referencing a specific tweet."""
        quotes = []
        for response in tweepy.Paginator(
            self.client.get_quote_tweets,
            tweet_id,
            tweet_fields=TWEET_FIELDS,
            user_fields=USER_FIELDS,
            expansions=EXPANSIONS,
            max_results=min(max_results, 100),
        ):
            if response.data:
                quotes.extend(response.data)
            if len(quotes) >= max_results:
                break
        return quotes

    def get_user(self, user_id: str):
        """Fetch a single user profile."""
        resp = self._retry(
            self.client.get_user,
            id=user_id,
            user_fields=USER_FIELDS,
        )
        if resp and resp.data:
            return resp.data
        return None
