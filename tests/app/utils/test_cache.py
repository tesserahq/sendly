import pytest
from unittest.mock import Mock, patch
import json

from app.utils.cache import Cache


@pytest.fixture
def mock_redis():
    with patch("app.utils.cache.Redis") as mock_redis_class:
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        yield mock_redis_instance


@pytest.fixture
def cache(mock_redis):
    return Cache("test")


def test_get_cache_key(cache):
    """Test cache key generation with namespace."""
    key = "test-key"
    expected_key = "test:test-key"
    assert cache._get_cache_key(key) == expected_key


def test_serialize_value(cache):
    """Test value serialization."""
    test_data = {"name": "test", "value": 123}
    serialized = cache._serialize_value(test_data)
    assert json.loads(serialized) == test_data


def test_deserialize_value(cache):
    """Test value deserialization."""
    test_data = {"name": "test", "value": 123}
    serialized = json.dumps(test_data)
    deserialized = cache._deserialize_value(serialized)
    assert deserialized == test_data


def test_read_cache_hit(cache, mock_redis):
    """Test reading from cache when value exists."""
    test_data = {"name": "test", "value": 123}
    serialized_data = json.dumps(test_data)
    mock_redis.get.return_value = serialized_data

    result = cache.read("test-key")

    assert result == test_data
    mock_redis.get.assert_called_once_with("test:test-key")


def test_read_cache_miss(cache, mock_redis):
    """Test reading from cache when value doesn't exist."""
    mock_redis.get.return_value = None

    result = cache.read("test-key")

    assert result is None
    mock_redis.get.assert_called_once_with("test:test-key")


def test_read_redis_error(cache, mock_redis):
    """Test reading when Redis connection fails."""
    from redis import ConnectionError

    mock_redis.get.side_effect = ConnectionError("Connection failed")

    result = cache.read("test-key")

    assert result is None


def test_write_success(cache, mock_redis):
    """Test writing to cache successfully."""
    mock_redis.setex.return_value = True
    test_data = {"name": "test", "value": 123}

    result = cache.write("test-key", test_data)

    assert result is True
    mock_redis.setex.assert_called_once()
    call_args = mock_redis.setex.call_args
    assert call_args[0][0] == "test:test-key"  # cache key
    assert call_args[0][1] == 3600  # default TTL
    assert json.loads(call_args[0][2]) == test_data  # serialized value


def test_write_custom_ttl(cache, mock_redis):
    """Test writing to cache with custom TTL."""
    mock_redis.setex.return_value = True
    test_data = {"name": "test"}
    custom_ttl = 7200

    result = cache.write("test-key", test_data, ttl=custom_ttl)

    assert result is True
    call_args = mock_redis.setex.call_args
    assert call_args[0][1] == custom_ttl


def test_write_redis_error(cache, mock_redis):
    """Test writing when Redis connection fails."""
    from redis import ConnectionError

    mock_redis.setex.side_effect = ConnectionError("Connection failed")

    result = cache.write("test-key", {"test": "data"})

    assert result is False


def test_delete_success(cache, mock_redis):
    """Test deleting from cache successfully."""
    mock_redis.delete.return_value = 1

    result = cache.delete("test-key")

    assert result is True
    mock_redis.delete.assert_called_once_with("test:test-key")


def test_delete_not_found(cache, mock_redis):
    """Test deleting key that doesn't exist in cache."""
    mock_redis.delete.return_value = 0

    result = cache.delete("test-key")

    assert result is False


def test_exists_true(cache, mock_redis):
    """Test checking if key exists when it does."""
    mock_redis.exists.return_value = 1

    result = cache.exists("test-key")

    assert result is True
    mock_redis.exists.assert_called_once_with("test:test-key")


def test_exists_false(cache, mock_redis):
    """Test checking if key exists when it doesn't."""
    mock_redis.exists.return_value = 0

    result = cache.exists("test-key")

    assert result is False
    mock_redis.exists.assert_called_once_with("test:test-key")


def test_ttl_with_ttl(cache, mock_redis):
    """Test getting TTL when key has TTL."""
    mock_redis.ttl.return_value = 1800  # 30 minutes

    result = cache.ttl("test-key")

    assert result == 1800
    mock_redis.ttl.assert_called_once_with("test:test-key")


def test_ttl_no_ttl(cache, mock_redis):
    """Test getting TTL when key has no TTL."""
    mock_redis.ttl.return_value = -1  # No TTL

    result = cache.ttl("test-key")

    assert result == -1


def test_ttl_key_not_exists(cache, mock_redis):
    """Test getting TTL when key doesn't exist."""
    mock_redis.ttl.return_value = -2  # Key doesn't exist

    result = cache.ttl("test-key")

    assert result is None


def test_clear_pattern_success(cache, mock_redis):
    """Test clearing cache entries matching a pattern."""
    mock_redis.keys.return_value = ["test:user1", "test:user2"]
    mock_redis.delete.return_value = 2

    result = cache.clear_pattern("user*")

    assert result is True
    mock_redis.keys.assert_called_once_with("test:user*")
    mock_redis.delete.assert_called_once_with("test:user1", "test:user2")


def test_clear_pattern_empty(cache, mock_redis):
    """Test clearing pattern when no keys match."""
    mock_redis.keys.return_value = []

    result = cache.clear_pattern("nonexistent*")

    assert result is True
    mock_redis.keys.assert_called_once_with("test:nonexistent*")
    mock_redis.delete.assert_not_called()


def test_clear_all(cache, mock_redis):
    """Test clearing all cache entries."""
    mock_redis.keys.return_value = ["test:key1", "test:key2"]
    mock_redis.delete.return_value = 2

    result = cache.clear_all()

    assert result is True
    mock_redis.keys.assert_called_once_with("test:*")
    mock_redis.delete.assert_called_once_with("test:key1", "test:key2")


def test_ping_success(cache, mock_redis):
    """Test Redis ping when connection is successful."""
    mock_redis.ping.return_value = True

    result = cache.ping()

    assert result is True
    mock_redis.ping.assert_called_once()


def test_ping_failure(cache, mock_redis):
    """Test Redis ping when connection fails."""
    mock_redis.ping.side_effect = Exception("Connection failed")

    result = cache.ping()

    assert result is False


def test_create_cache_function():
    """Test the convenience function to create cache instances."""
    from app.utils.cache import create_cache

    cache = create_cache("custom")
    assert cache.namespace == "custom"
    assert cache._get_cache_key("test") == "custom:test"


def test_different_namespaces():
    """Test that different cache instances use different namespaces."""
    cache1 = Cache("namespace1")
    cache2 = Cache("namespace2")

    assert cache1._get_cache_key("key") == "namespace1:key"
    assert cache2._get_cache_key("key") == "namespace2:key"
