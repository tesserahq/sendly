import importlib


def test_celery_uses_sdk_redis_connection_url(monkeypatch):
    redis_url = "redis://sendly:test-password@redis:6379/0"
    monkeypatch.setenv("REDIS_URL", redis_url)

    from app.core import celery_app as celery_module

    celery_module = importlib.reload(celery_module)

    assert celery_module.celery_app.conf.broker_url == redis_url
    assert celery_module.celery_app.conf.result_backend == redis_url
