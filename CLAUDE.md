# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Sendly

FastAPI/SQLAlchemy multi-tenant email abstraction service. Python 3.12, Poetry.

Sendly runs as **two processes** sharing one codebase and one Postgres database:

- **API** — FastAPI app (`app.main:app`). Single sends (`POST /emails`) are synchronous; broadcasts are accepted here and handed off to the worker.
- **Worker** — Celery worker (`run_worker.py`, `poetry run worker`) consuming the `sendly` queue on Redis. Runs the broadcast prepare/send pipeline and the recovery sweeps.

External runtime dependencies: **PostgreSQL**, **Redis** (Celery broker + result backend), **NATS** (outbound domain events, optional), and **Postmark** (email provider).

## Commands

- `ENV=test poetry run pytest` — run all tests
- `ENV=test poetry run pytest tests/path/to/test.py -v` — run specific test file
- `ENV=test poetry run pytest tests/path/to/test.py::test_function_name -v` — run single test
- `poetry run black app tests` — format code
- `poetry run ruff check app tests` — lint
- `poetry run alembic revision --autogenerate -m "description"` — generate migration
- `poetry run alembic upgrade head` — apply migrations
- `poetry run dev` — run the API with reload (`run.py`)
- `poetry run worker` — run the Celery worker (`run_worker.py`)
- `poetry run celery -A app.core.celery_app beat` — run Celery beat (schedules the recovery sweeps; not started by `run_worker.py`)

After pulling, run `poetry install` — `tessera-sdk` is pinned to a git commit in `poetry.lock`, and a stale venv fails at import (e.g. missing `redis_connection_url`).

## Architecture

### Layers (top to bottom)

- `app/routers/` — FastAPI route handlers; thin, delegate immediately to commands
- `app/commands/` — orchestration layer (one class per operation, `execute()` method)
- `app/services/` — cross-cutting logic commands and tasks delegate to
  - `EmailLifecycleService` owns all `Email.status` / `EmailEvent` writes
  - `EmailRenderingService` owns template resolution + Mako rendering (shared by API and worker)
  - `BroadcastPreparePublisher` / `BroadcastOutboxPublisher` dispatch Celery tasks and run recovery sweeps
- `app/repositories/` — data access; `EmailRepository` inherits `SoftDeleteRepository[T]`
- `app/providers/` — email provider strategy implementations (Postmark only); `registry.py` maps slug → provider class
- `app/tasks/` — Celery tasks (worker-side entry points)
- `app/events/` — NATS event builders

### Key files

- `app/main.py` — `create_app(testing, auth_middleware)` factory; routers registered here (`app/routers/system.py` exists but is **not** registered)
- `app/config.py` — Sendly settings (DB, Postmark, broadcast chunk size, etc.)
- `app/core/celery_app.py` — Celery app, queue routing, beat schedule
- `run_worker.py` — worker entrypoint (also starts a Prometheus metrics server)
- `app/providers/base.py` — `EmailCreateRequest` (send payload) and `EmailSendResult`
- `app/constants/email.py` — `EmailStatus` constants (source of truth for all status strings)
- `app/schemas/email.py` — Pydantic I/O models; `EmailUpdate` fields are all optional
- `docs/broadcast-sending.md` — detailed broadcast pipeline design (diagrams); `docs/prds/` — feature PRDs

### Multi-tenancy

Scoped via `project_id` (UUID) on `Email`, `BroadcastBatch`, and suppressions. RBAC is enforced per-resource via `app/auth/rbac.py`, which wraps `tessera_sdk.server.dependencies.authorization.authorize`. Each router calls `build_rbac_dependencies(resource=..., project_resolver=...)` to get FastAPI `Depends` callables.

### Rendering / templates

`EmailRenderingService.resolve(req)` is used by both `SendEmailCommand` and the broadcast prepare task:

- `template_id` or `template_alias` set → load `Template` from DB, render `html` and `subject` with Mako, and wrap in the template's `Layout` (passed as `content`) if one is attached. Template defaults fill `from_email` / `reply_to`.
- Otherwise → inline `html` rendered with Mako using `template_variables`.
- Template and inline `html` are mutually exclusive (`ConflictingContentError`).
- Raises plain exceptions (not `HTTPException`) because it runs in the worker too.

## Background worker (Celery + Redis)

- Broker and result backend both use `tessera_sdk.config.get_settings().redis_connection_url` — set `REDIS_URL`, or fall back to `REDIS_HOST`/`REDIS_PORT` (db 0).
- All `app.tasks.*` route to the `sendly` queue. Tasks are registered by explicit import in `app/tasks/__init__.py`; add new task modules there.
- Worker env knobs: `CELERY_POOL` (defaults to `solo` on macOS to avoid fork segfaults, `prefork` elsewhere), `CELERY_CONCURRENCY`, `CELERY_QUEUES`, `CELERY_LOGLEVEL`, `CELERY_NODENAME`, `METRICS_PORT` (default 9100).
- Tasks open their own DB session via `app/utils/db/db_session_helper.db_session()`. They have no request context, so don't raise `HTTPException` from code the worker calls.
- The Docker image's `start.sh` runs migrations and the API only. The worker and beat have to be started as separate processes from the same image, with a different command.

### Broadcast pipeline (`POST /broadcasts/send`)

Three stages, each chunked (`BROADCAST_CHUNK_SIZE`, default 100, max 500 because of Postmark's Bulk API limit):

1. **Accept** (`SendBroadcastCommand`, in the API) — validate content once, do one bulk suppression lookup, insert the `BroadcastBatch` and `BroadcastRecipient` rows in one transaction, then dispatch prepare chunks. No rendering and no `Email` rows here.
2. **Prepare** (`prepare_broadcast_chunk_task`) — re-check suppression, render per recipient, and create `Email` (status `queued`) + immutable `EmailDeliveryPayload` + `EmailSendOutbox` entry. A rendering failure skips that recipient without failing the chunk. Then dispatches send chunks.
3. **Send** (`send_broadcast_chunk_task`) — one Postmark Bulk API call per chunk, then records each outcome through `EmailLifecycleService`. Transport failures retry the **whole chunk** (max 3, 30s countdown). Duplicate sends are possible because the Bulk API has no idempotency key.

Dispatch is transactional-outbox style: a synchronous fast-path `.delay()` right after commit, plus Celery-beat recovery sweeps (`prepare_recovery_sweep`, `outbox_recovery_sweep`, every 60s) that pick up anything a crash left behind. **If beat isn't running, crashed chunks are never recovered.**

## NATS events

- Sendly **publishes** events and does not consume any. It uses `tessera_sdk.infra.events.NatsEventPublisher` (CloudEvents shape).
- Config comes from tessera-sdk settings: `NATS_ENABLED` (default `false`; when false, `publish_sync` is a logged no-op), `NATS_URL` (default `nats://localhost:4222`), `EVENT_TYPE_PREFIX`, `EVENT_SOURCE_PREFIX`.
- The only current event is `email.unsubscribed` (`app/events/email_events.py`). `HandleSubscriptionChangeCommand` publishes it after upserting a project-scoped suppression for a recipient-originated Postmark `SubscriptionChange` webhook. Reactivation removes the suppression and publishes nothing.
- Convention (shared with sibling TesseraHQ services): the NATS subject passed to `publish_sync(event, subject)` is `event.event_type` (dotted and prefixed), **not** `event.subject`. `event.subject` is REST-style CloudEvents metadata only.
- Publish failures are logged and swallowed, so they never fail the webhook.
- New events: add a `build_*_event` function in `app/events/`, and have the command take an optional `nats_publisher` so tests can inject a `MagicMock`.

## Provider webhooks

`POST /providers/{provider_id}/delivery-events` → `ProcessDeliveryEventsCommand` → `EmailLifecycleService.record_webhook_event` for every event, plus `HandleSubscriptionChangeCommand` for unsubscribe/reactivation. `PostmarkProvider.verify_webhook()` currently always returns `True`; the endpoint is protected only by RBAC.

## Testing

- Tests use a real PostgreSQL database (`sendly_test`); Alembic migrations run automatically via the `engine` session-scoped fixture in `conftest.py`
- Each test function gets a rolled-back transaction (`db` fixture) — commits inside tests are safe and rolled back after
- Auth is globally mocked in `conftest.py` **before** routers are imported — the patch on `tessera_sdk.server.dependencies.authorization.authorize` must happen before `create_app` is called
- Router tests use `client` (or `client_another_user`, `client_test_user`) fixtures created by `create_client_fixture()` factory in `conftest.py`; inject a user via `app.state.test_user`
- Celery runs **eagerly** in tests (`task_always_eager=True`, `task_eager_propagates=True`), so no Redis or worker is needed. Eager tasks open their own session, which can't see rows inside the `db` fixture's uncommitted outer transaction. Broadcast pipeline integration tests therefore use `real_db` / `create_real_db_client_fixture()` (real commits, cleaned up in teardown, guarded to `ENV=test`).
- No NATS is needed in tests: mock `NatsEventPublisher` (patch `app.commands.providers.handle_subscription_change_command.NatsEventPublisher` or inject `nats_publisher=MagicMock()`).
- Unit tests for services use `MagicMock` for `EmailRepository`; no DB needed

## Gotchas

- `PostmarkProvider.send_email()` / `send_batch()` ignore `self.settings` and call `get_settings()` globally, so per-tenant provider config is not yet supported. Broadcasts use `POSTMARK_BROADCAST_STREAM_ID` as the message stream.
- `Email.to_email` only stores `req.to[0]` on single sends — multiple recipients are silently dropped
- Soft-delete filter is applied globally via SQLAlchemy event listener; bypass with `.execution_options(skip_soft_delete_filter=True)`
- A template whose layout was soft-deleted renders without the layout and logs a warning
- Suppression is checked three times (accept, prepare, send). A recipient suppressed mid-flight ends as `suppressed`, not `failed`.
