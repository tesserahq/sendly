import json
import logging
from typing import Optional, Any
from redis import Redis, ConnectionError
from app.config import get_settings

logger = logging.getLogger(__name__)


class Cache:
    """Generic Redis-based cache for any type of data."""

    def __init__(self, namespace: str = "cache"):
        self.settings = get_settings()
        self.redis_client = Redis(
            host=self.settings.redis_host,
            port=self.settings.redis_port,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self.namespace = namespace
        self.default_ttl = 3600  # 1 hour in seconds

    def _get_cache_key(self, key: str) -> str:
        """Generate cache key with namespace."""
        return f"{self.namespace}:{key}"

    def _serialize_value(self, value: Any) -> str:
        """Serialize value to JSON string."""
        return json.dumps(value)

    def _deserialize_value(self, value: str) -> Any:
        """Deserialize JSON string to value."""
        return json.loads(value)

    def read(self, key: str) -> Optional[Any]:
        """
        Read value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value if found, None otherwise
        """
        try:
            cache_key = self._get_cache_key(key)
            cached_value = self.redis_client.get(cache_key)

            if cached_value is not None:
                logger.debug(f"Cache hit for key: {key}")
                return self._deserialize_value(cached_value)

            logger.debug(f"Cache miss for key: {key}")
            return None

        except ConnectionError as e:
            logger.warning(f"Redis connection error while reading key {key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading key {key} from cache: {e}")
            return None

    def write(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Write value to cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (defaults to default_ttl)

        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._get_cache_key(key)
            serialized_value = self._serialize_value(value)
            ttl = ttl or self.default_ttl

            success = self.redis_client.setex(cache_key, ttl, serialized_value)
            if success:
                logger.debug(f"Cached key {key} with TTL {ttl}s")
            return success

        except ConnectionError as e:
            logger.warning(f"Redis connection error while writing key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error writing key {key} to cache: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._get_cache_key(key)
            deleted = self.redis_client.delete(cache_key)
            if deleted:
                logger.debug(f"Deleted key {key} from cache")
            return bool(deleted)

        except ConnectionError as e:
            logger.warning(f"Redis connection error while deleting key {key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting key {key} from cache: {e}")
            return False

    def clear_pattern(self, pattern: str) -> bool:
        """
        Clear all cache entries matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "user:*")

        Returns:
            True if successful, False otherwise
        """
        try:
            full_pattern = f"{self.namespace}:{pattern}"
            keys = self.redis_client.keys(full_pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(
                    f"Cleared {deleted} cache entries matching pattern: {pattern}"
                )
                return True
            return True

        except ConnectionError as e:
            logger.warning(
                f"Redis connection error while clearing pattern {pattern}: {e}"
            )
            return False
        except Exception as e:
            logger.error(f"Error clearing pattern {pattern} from cache: {e}")
            return False

    def clear_all(self) -> bool:
        """
        Clear all cache entries for this namespace.

        Returns:
            True if successful, False otherwise
        """
        return self.clear_pattern("*")

    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        try:
            cache_key = self._get_cache_key(key)
            return bool(self.redis_client.exists(cache_key))

        except ConnectionError as e:
            logger.warning(
                f"Redis connection error while checking existence of key {key}: {e}"
            )
            return False
        except Exception as e:
            logger.error(f"Error checking existence of key {key}: {e}")
            return False

    def ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for a key.

        Args:
            key: Cache key

        Returns:
            Remaining TTL in seconds, -1 if no TTL, None if key doesn't exist
        """
        try:
            cache_key = self._get_cache_key(key)
            ttl = self.redis_client.ttl(cache_key)
            return ttl if ttl != -2 else None  # -2 means key doesn't exist

        except ConnectionError as e:
            logger.warning(
                f"Redis connection error while getting TTL for key {key}: {e}"
            )
            return None
        except Exception as e:
            logger.error(f"Error getting TTL for key {key}: {e}")
            return None

    def ping(self) -> bool:
        """
        Test Redis connection.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            return self.redis_client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False


# Convenience function to create cache instances
def create_cache(namespace: str = "cache") -> Cache:
    """
    Create a new cache instance with the specified namespace.

    Args:
        namespace: Namespace for cache keys

    Returns:
        Cache instance
    """
    return Cache(namespace)


# Common cache instances
user_cache = Cache("user")
workspace_cache = Cache("workspace")
project_cache = Cache("project")
