"""
Twitter Mentions Module

Handles mention detection, classification, and tracking for bidirectional Twitter interaction.
Part of feature 040-twitter-mentions.
"""

import os
import re
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import tweepy

logger = logging.getLogger("twitter-mcp.mentions")


class MentionCategory(Enum):
    """Classification categories for incoming mentions."""
    NETCLAW_REQUEST = "netclaw_request"
    TECHNICAL_NETWORK = "technical_network"
    FRIENDLY = "friendly"
    OFF_TOPIC = "off_topic"
    SPAM = "spam"


@dataclass
class Mention:
    """Represents a Twitter mention."""
    tweet_id: str
    author_id: str
    author_handle: str
    text: str
    created_at: datetime
    conversation_id: Optional[str] = None
    in_reply_to_tweet_id: Optional[str] = None
    category: Optional[MentionCategory] = None
    processed: bool = False
    processed_at: Optional[datetime] = None


@dataclass
class ConversationContext:
    """Thread context for a mention."""
    conversation_id: str
    tweets: List[Dict[str, Any]] = field(default_factory=list)
    fetched_at: Optional[datetime] = None


# Keywords for classification
NETCLAW_KEYWORDS = [
    "netclaw", "automation", "diagram", "mcp", "skill", "pyats",
    "openclaw", "automate", "script", "topology"
]

NETWORK_KEYWORDS = [
    "ospf", "bgp", "eigrp", "isis", "vlan", "routing", "switching",
    "firewall", "aci", "cisco", "juniper", "f5", "palo", "fortigate",
    "meraki", "arista", "nexus", "catalyst", "asa", "ftd", "ise",
    "netbox", "nautobot", "ansible", "terraform", "nso",
    "mpls", "vpn", "ipsec", "ssl", "tls", "acl", "nat", "dhcp", "dns",
    "snmp", "syslog", "netconf", "restconf", "yang", "grpc", "gnmi",
    "interface", "trunk", "port-channel", "lacp", "stp", "rstp",
    "qos", "cef", "arp", "mac", "layer2", "layer3", "subnet", "cidr"
]

FRIENDLY_KEYWORDS = [
    "thanks", "thank you", "thx", "ty", "hello", "hi", "hey",
    "awesome", "great", "love", "cool", "nice", "congrats",
    "welcome", "appreciate"
]


class ProcessedMentionTracker:
    """
    Tracks processed mentions to prevent duplicate handling.
    Uses Memory MCP for persistence with 24-hour TTL.
    """

    def __init__(self, memory_client=None):
        """
        Initialize the tracker.

        Args:
            memory_client: Optional Memory MCP client for persistence.
                          Falls back to in-memory tracking if not provided.
        """
        self.memory_client = memory_client
        self._local_cache: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(hours=24)

    async def is_processed(self, mention_id: str) -> bool:
        """Check if a mention has already been processed."""
        # Check local cache first
        if mention_id in self._local_cache:
            if datetime.utcnow() - self._local_cache[mention_id] < self._cache_ttl:
                return True
            else:
                del self._local_cache[mention_id]

        # Check Memory MCP if available
        if self.memory_client:
            try:
                key = f"twitter_mention_{mention_id}"
                result = await self.memory_client.recall(key)
                if result:
                    return True
            except Exception as e:
                logger.warning(f"Memory MCP recall failed: {e}")

        return False

    async def mark_processed(self, mention_id: str, action: str, reply_id: Optional[str] = None):
        """
        Mark a mention as processed.

        Args:
            mention_id: The tweet ID of the mention
            action: What was done (replied, skipped_off_topic, skipped_spam, flagged_review)
            reply_id: The reply tweet ID if action was 'replied'
        """
        now = datetime.utcnow()
        self._local_cache[mention_id] = now

        # Store in Memory MCP if available
        if self.memory_client:
            try:
                key = f"twitter_mention_{mention_id}"
                value = {
                    "processed_at": now.isoformat(),
                    "action": action,
                    "reply_id": reply_id
                }
                await self.memory_client.remember(key, value, ttl_days=1)
            except Exception as e:
                logger.warning(f"Memory MCP remember failed: {e}")

    def cleanup_cache(self):
        """Remove expired entries from local cache."""
        now = datetime.utcnow()
        expired = [
            mid for mid, ts in self._local_cache.items()
            if now - ts >= self._cache_ttl
        ]
        for mid in expired:
            del self._local_cache[mid]


def classify_mention(text: str, author_data: Optional[Dict] = None) -> MentionCategory:
    """
    Classify a mention into response categories.

    Args:
        text: The mention text
        author_data: Optional author metadata for spam detection

    Returns:
        MentionCategory indicating how to handle the mention
    """
    text_lower = text.lower()

    # Check for spam first
    if author_data and is_likely_spam(author_data, text):
        return MentionCategory.SPAM

    # Check for NetClaw-related requests
    if any(kw in text_lower for kw in NETCLAW_KEYWORDS):
        return MentionCategory.NETCLAW_REQUEST

    # Check for technical network topics
    if any(kw in text_lower for kw in NETWORK_KEYWORDS):
        return MentionCategory.TECHNICAL_NETWORK

    # Check for friendly engagement
    if any(kw in text_lower for kw in FRIENDLY_KEYWORDS):
        return MentionCategory.FRIENDLY

    # Default to off-topic
    return MentionCategory.OFF_TOPIC


def is_likely_spam(author_data: Dict, tweet_text: str) -> bool:
    """
    Detect likely spam/bot accounts using heuristics.

    Heuristics per research.md:
    1. Account created within last 7 days
    2. Following/followers ratio > 100:1
    3. Username contains 8+ digits
    4. Known spam patterns

    Args:
        author_data: Author metadata from Twitter API
        tweet_text: The mention text

    Returns:
        True if likely spam, False otherwise
    """
    # Check account age
    created_at_str = author_data.get("created_at")
    if created_at_str:
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            if (datetime.now(created_at.tzinfo) - created_at).days < 7:
                logger.debug(f"Spam heuristic: Account too new")
                return True
        except (ValueError, TypeError):
            pass

    # Check follower ratio
    public_metrics = author_data.get("public_metrics", {})
    following = public_metrics.get("following_count", 0)
    followers = public_metrics.get("followers_count", 1)
    if following > 0 and followers > 0:
        ratio = following / max(followers, 1)
        if ratio > 100:
            logger.debug(f"Spam heuristic: Following/followers ratio {ratio}")
            return True

    # Check username for excessive digits
    username = author_data.get("username", "")
    digit_count = sum(1 for c in username if c.isdigit())
    if digit_count >= 8:
        logger.debug(f"Spam heuristic: Username has {digit_count} digits")
        return True

    # Check for common spam patterns in text
    spam_patterns = [
        r"crypto", r"nft", r"giveaway", r"airdrop",
        r"dm me", r"check bio", r"click link",
        r"\$\d+k", r"make money", r"earn \$"
    ]
    text_lower = tweet_text.lower()
    for pattern in spam_patterns:
        if re.search(pattern, text_lower):
            logger.debug(f"Spam heuristic: Matched pattern '{pattern}'")
            return True

    return False


async def get_authenticated_user_id(client: tweepy.Client) -> str:
    """
    Get the authenticated user's Twitter ID.

    Args:
        client: Authenticated tweepy Client

    Returns:
        User ID string for the authenticated account
    """
    # Get the authenticated user's info
    me = client.get_me(user_fields=["id", "username"])
    if me and me.data:
        logger.info(f"Authenticated as @{me.data.username} (ID: {me.data.id})")
        return str(me.data.id)
    raise ValueError("Could not get authenticated user ID")


async def get_authenticated_user_id_oauth2(oauth2_token: str) -> str:
    """
    Get the authenticated user's Twitter ID using OAuth 2.0.

    Args:
        oauth2_token: OAuth 2.0 Bearer Token

    Returns:
        User ID string for the authenticated account
    """
    headers = {
        "Authorization": f"Bearer {oauth2_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(
        "https://api.twitter.com/2/users/me",
        headers=headers
    )
    if response.status_code == 200:
        data = response.json()
        user_id = data["data"]["id"]
        username = data["data"]["username"]
        logger.info(f"Authenticated as @{username} (ID: {user_id})")
        return user_id
    raise ValueError(f"Could not get authenticated user ID: {response.text}")


async def fetch_mentions(
    client: tweepy.Client,
    user_id: str,
    limit: int = 10,
    since_id: Optional[str] = None
) -> List[Mention]:
    """
    Fetch recent mentions for a user.

    Args:
        client: Authenticated tweepy Client
        user_id: Twitter user ID to get mentions for
        limit: Maximum number of mentions to return
        since_id: Only return mentions newer than this tweet ID

    Returns:
        List of Mention objects
    """
    try:
        response = client.get_users_mentions(
            id=user_id,
            max_results=min(limit, 100),
            since_id=since_id,
            tweet_fields=["created_at", "conversation_id", "in_reply_to_user_id", "author_id"],
            expansions=["author_id"],
            user_fields=["username", "created_at", "public_metrics"]
        )

        if not response or not response.data:
            return []

        # Build author lookup
        authors = {}
        if response.includes and "users" in response.includes:
            for user in response.includes["users"]:
                authors[str(user.id)] = {
                    "username": user.username,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "public_metrics": user.public_metrics if hasattr(user, "public_metrics") else {}
                }

        mentions = []
        for tweet in response.data:
            author_id = str(tweet.author_id)
            author_data = authors.get(author_id, {})

            mention = Mention(
                tweet_id=str(tweet.id),
                author_id=author_id,
                author_handle=author_data.get("username", "unknown"),
                text=tweet.text,
                created_at=tweet.created_at or datetime.utcnow(),
                conversation_id=str(tweet.conversation_id) if tweet.conversation_id else None,
                in_reply_to_tweet_id=str(tweet.in_reply_to_user_id) if tweet.in_reply_to_user_id else None
            )

            # Classify the mention
            mention.category = classify_mention(tweet.text, author_data)

            mentions.append(mention)

        return mentions

    except tweepy.TooManyRequests as e:
        logger.warning(f"Rate limited when fetching mentions: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching mentions: {e}")
        raise


async def fetch_mentions_oauth2(
    oauth2_token: str,
    user_id: str,
    limit: int = 10,
    since_id: Optional[str] = None
) -> List[Mention]:
    """
    Fetch recent mentions using OAuth 2.0 (required for pay-as-you-go tier).

    Args:
        oauth2_token: OAuth 2.0 Bearer Token
        user_id: Twitter user ID to get mentions for
        limit: Maximum number of mentions to return
        since_id: Only return mentions newer than this tweet ID

    Returns:
        List of Mention objects
    """
    headers = {
        "Authorization": f"Bearer {oauth2_token}",
        "Content-Type": "application/json"
    }

    params = {
        "max_results": max(5, min(limit, 100)),  # API requires between 5-100
        "tweet.fields": "created_at,conversation_id,in_reply_to_user_id,author_id",
        "expansions": "author_id",
        "user.fields": "username,created_at,public_metrics"
    }
    if since_id:
        params["since_id"] = since_id

    try:
        response = requests.get(
            f"https://api.twitter.com/2/users/{user_id}/mentions",
            headers=headers,
            params=params
        )

        if response.status_code == 429:
            raise tweepy.TooManyRequests(response)

        if response.status_code != 200:
            logger.error(f"Error fetching mentions: {response.text}")
            return []

        data = response.json()

        if "data" not in data:
            return []

        # Build author lookup
        authors = {}
        if "includes" in data and "users" in data["includes"]:
            for user in data["includes"]["users"]:
                authors[user["id"]] = {
                    "username": user["username"],
                    "created_at": user.get("created_at"),
                    "public_metrics": user.get("public_metrics", {})
                }

        mentions = []
        for tweet in data["data"]:
            author_id = tweet["author_id"]
            author_data = authors.get(author_id, {})

            mention = Mention(
                tweet_id=tweet["id"],
                author_id=author_id,
                author_handle=author_data.get("username", "unknown"),
                text=tweet["text"],
                created_at=datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00")) if tweet.get("created_at") else datetime.utcnow(),
                conversation_id=tweet.get("conversation_id"),
                in_reply_to_tweet_id=tweet.get("in_reply_to_user_id")
            )

            # Classify the mention
            mention.category = classify_mention(tweet["text"], author_data)

            mentions.append(mention)

        return mentions

    except Exception as e:
        logger.error(f"Error fetching mentions: {e}")
        raise


async def fetch_mentions_with_retry(
    client: tweepy.Client,
    user_id: str,
    limit: int = 10,
    since_id: Optional[str] = None,
    max_retries: int = 3
) -> List[Mention]:
    """
    Fetch mentions with exponential backoff on rate limits.

    Args:
        client: Authenticated tweepy Client
        user_id: Twitter user ID
        limit: Maximum mentions to return
        since_id: Only return newer mentions
        max_retries: Maximum retry attempts

    Returns:
        List of Mention objects
    """
    for attempt in range(max_retries):
        try:
            return await fetch_mentions(client, user_id, limit, since_id)
        except tweepy.TooManyRequests:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 60  # 1, 2, 4 minutes
                logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                logger.error("Rate limit exceeded after all retries")
                raise
    return []


async def get_conversation_context(
    client: tweepy.Client,
    tweet_id: str,
    max_depth: int = 5
) -> ConversationContext:
    """
    Retrieve conversation context (parent tweets) for a mention.

    Args:
        client: Authenticated tweepy Client
        tweet_id: The tweet ID to get context for
        max_depth: Maximum number of parent tweets to retrieve

    Returns:
        ConversationContext with parent tweets
    """
    context = ConversationContext(conversation_id="", fetched_at=datetime.utcnow())
    tweets = []
    current_id = tweet_id

    for _ in range(max_depth):
        try:
            response = client.get_tweet(
                id=current_id,
                tweet_fields=["conversation_id", "in_reply_to_user_id", "author_id", "created_at"],
                expansions=["author_id", "referenced_tweets.id"],
                user_fields=["username"]
            )

            if not response or not response.data:
                break

            tweet = response.data

            # Set conversation ID from first tweet
            if not context.conversation_id and tweet.conversation_id:
                context.conversation_id = str(tweet.conversation_id)

            # Get author info
            author_username = "unknown"
            if response.includes and "users" in response.includes:
                for user in response.includes["users"]:
                    if str(user.id) == str(tweet.author_id):
                        author_username = user.username
                        break

            tweets.append({
                "tweet_id": str(tweet.id),
                "author_handle": author_username,
                "text": tweet.text,
                "created_at": tweet.created_at.isoformat() if tweet.created_at else None
            })

            # Find parent tweet
            parent_id = None
            if response.includes and "tweets" in response.includes:
                for ref_tweet in response.includes["tweets"]:
                    # This is the replied-to tweet
                    parent_id = str(ref_tweet.id)
                    break

            if not parent_id:
                break

            current_id = parent_id

        except Exception as e:
            logger.warning(f"Error fetching conversation context: {e}")
            break

    # Reverse to get chronological order (oldest first)
    context.tweets = list(reversed(tweets))
    return context


class InteractionHistory:
    """Manages interaction history with Twitter users via Memory MCP."""

    def __init__(self, memory_client=None):
        self.memory_client = memory_client

    async def get_history(self, username: str) -> Optional[Dict]:
        """Get interaction history for a user."""
        if not self.memory_client:
            return None

        try:
            key = f"twitter_user_{username.lower()}"
            return await self.memory_client.recall(key)
        except Exception as e:
            logger.warning(f"Error getting user history: {e}")
            return None

    async def update_history(
        self,
        username: str,
        user_id: str,
        topic: Optional[str] = None
    ):
        """Update interaction history for a user."""
        if not self.memory_client:
            return

        try:
            key = f"twitter_user_{username.lower()}"
            existing = await self.memory_client.recall(key) or {}

            now = datetime.utcnow().isoformat()
            history = {
                "user_handle": username,
                "user_id": user_id,
                "first_interaction": existing.get("first_interaction", now),
                "last_interaction": now,
                "interaction_count": existing.get("interaction_count", 0) + 1,
                "topics": existing.get("topics", []),
                "sentiment": existing.get("sentiment", "neutral")
            }

            if topic and topic not in history["topics"]:
                history["topics"].append(topic)
                # Keep only last 10 topics
                history["topics"] = history["topics"][-10:]

            await self.memory_client.remember(key, history, ttl_days=30)

        except Exception as e:
            logger.warning(f"Error updating user history: {e}")
