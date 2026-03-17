# Sendly

FastAPI/SQLAlchemy multi-tenant email abstraction service. Python 3.12, Poetry.

## Commands

- `poetry run pytest` — run tests
- `poetry run pytest tests/path/to/test.py -v` — run specific test file

## Architecture

- `app/commands/` — orchestration layer (one class per operation)
- `app/repositories/` — data access; `EmailRepository` inherits `SoftDeleteRepository[T]`
- `app/providers/` — email provider strategy implementations (Postmark only currently)
- `app/services/` — cross-cutting logic that commands delegate to
- `app/schemas/` — Pydantic models for API I/O; `EmailUpdate` fields are all optional
- `app/constants/email.py` — `EmailStatus` constants (source of truth for status strings)

## Testing

- Tests use a real PostgreSQL database (`sendly_test`); Alembic migrations run automatically via `conftest.py`
- Each test function gets a rolled-back transaction (`db` fixture) — commits inside tests are safe
- Auth is globally mocked in `conftest.py` before routers are imported (patch must happen before `create_app`)
- Unit tests for services use `MagicMock` for `EmailRepository`; no DB needed

## Gotchas

- `PostmarkProvider.send_email()` ignores `self.settings` and calls `get_settings()` globally — per-tenant provider config not yet supported
- `Email.to_email` only stores `req.to[0]` — multiple recipients are silently dropped
- Soft-delete filter is applied globally via SQLAlchemy event listener; bypass with `.execution_options(skip_soft_delete_filter=True)`
- `app/tasks/` is wired (Celery + Redis) but contains no actual tasks — email sending is synchronous
