# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Sendly

FastAPI/SQLAlchemy multi-tenant email abstraction service. Python 3.12, Poetry.

## Commands

- `poetry run pytest` — run all tests
- `poetry run pytest tests/path/to/test.py -v` — run specific test file
- `poetry run pytest tests/path/to/test.py::test_function_name -v` — run single test
- `poetry run black app tests` — format code
- `poetry run ruff check app tests` — lint
- `alembic revision --autogenerate -m "description"` — generate migration
- `alembic upgrade head` — apply migrations

## Architecture

### Layers (top to bottom)
- `app/routers/` — FastAPI route handlers; thin, delegate immediately to commands
- `app/commands/` — orchestration layer (one class per operation, `execute()` method)
- `app/services/` — cross-cutting logic commands delegate to (e.g. `EmailLifecycleService` owns all `Email.status` writes)
- `app/repositories/` — data access; `EmailRepository` inherits `SoftDeleteRepository[T]`
- `app/providers/` — email provider strategy implementations (Postmark only currently)

### Key files
- `app/providers/base.py` — `EmailCreateRequest` (send payload) and `EmailSendResult`; `template_id` field exists but is unused
- `app/constants/email.py` — `EmailStatus` constants (source of truth for all status strings)
- `app/schemas/email.py` — Pydantic I/O models; `EmailUpdate` fields are all optional
- `app/main.py` — `create_app(testing, auth_middleware)` factory; routers registered here

### Multi-tenancy
Scoped via `project_id` (UUID) on `Email`. RBAC is enforced per-resource via `app/auth/rbac.py`, which wraps `tessera_sdk.server.dependencies.authorization.authorize`. Each router calls `build_rbac_dependencies(resource=..., project_resolver=...)` to get FastAPI `Depends` callables.

### Templating
`SendEmailCommand` renders `req.html` through Mako (`mako.template.Template`) before sending. Variables are passed via `req.template_variables`. The `template_id` field on `EmailCreateRequest` is reserved for future template-lookup support but not yet wired.

## Testing

- Tests use a real PostgreSQL database (`sendly_test`); Alembic migrations run automatically via the `engine` session-scoped fixture in `conftest.py`
- Each test function gets a rolled-back transaction (`db` fixture) — commits inside tests are safe and rolled back after
- Auth is globally mocked in `conftest.py` **before** routers are imported — the patch on `tessera_sdk.server.dependencies.authorization.authorize` must happen before `create_app` is called
- Router tests use `client` (or `client_another_user`, `client_test_user`) fixtures created by `create_client_fixture()` factory in `conftest.py`; inject a user via `app.state.test_user`
- Unit tests for services use `MagicMock` for `EmailRepository`; no DB needed

## Gotchas

- `PostmarkProvider.send_email()` ignores `self.settings` and calls `get_settings()` globally — per-tenant provider config not yet supported
- `Email.to_email` only stores `req.to[0]` — multiple recipients are silently dropped
- Soft-delete filter is applied globally via SQLAlchemy event listener; bypass with `.execution_options(skip_soft_delete_filter=True)`
- `app/tasks/` is wired (Celery + Redis) but contains no actual tasks — email sending is synchronous
