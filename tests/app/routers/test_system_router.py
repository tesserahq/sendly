from types import SimpleNamespace

from app.routers import system


def test_redis_group_uses_sdk_connection_settings(monkeypatch):
    monkeypatch.setattr(
        system,
        "get_sdk_settings",
        lambda: SimpleNamespace(
            redis_connection_url="redis://sendly:test-password@redis-primary:6380/0",
            redis_host="ignored-host",
            redis_port=6379,
            redis_namespace="sendly",
        ),
    )

    group = system._get_redis_group()

    assert group.host == "redis-primary"
    assert group.port == 6380
    assert group.namespace == "sendly"
