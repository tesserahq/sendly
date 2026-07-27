# Feature: Broadcast Sending

**ID**: `feat-001`
**Status**: Approved
**Created**: 2026-07-26

---

## Summary

Sendly currently sends one email to one recipient at a time via `POST /emails`, with no way to fan a single piece of content out to a recipient list, no batch-level tracking, and no unsubscribe handling (Postmark's `SubscriptionChange` webhook is silently dropped into an unmapped event type). This feature adds `POST /broadcasts/send`, which accepts a list of structured recipients plus the same content options `/emails` already supports, and fans them out — through a new chunked, asynchronous prepare/send pipeline built on the previously-empty `app/tasks/` — to Postmark's Bulk API on the Broadcast message stream. It also adds a project-scoped suppression table so recipients who unsubscribe (via a correctly-mapped `SubscriptionChange` webhook) are automatically skipped on future broadcasts, and publishes a `email.unsubscribed` NATS event so external systems can react.

---

## Target Users

- **Primary**: External applications/services integrated with Sendly that need to send newsletter-style content to a list of recipients with light per-recipient personalization (first name, custom attributes).
- **Context**: Campaign/broadcast sends triggered programmatically by a caller's own system (e.g. a marketing or notification service), as opposed to the existing transactional single-recipient `/emails` flow.

---

## Scope

### In Scope

- [ ] `POST /broadcasts/send` — accepts `recipients: List[BroadcastRecipient]` (email required; first_name/last_name/attributes optional) plus shared content options (`html`/`text`/`template_id`/`template_alias`/`template_variables`/`subject`/`from_email`/`custom_headers`/`attachments`/`idempotency_key`/`tags`/`metadata`); returns `{batch_id, queued_count, suppressed_count}` immediately.
- [ ] `tags`/`metadata` columns added to `Email`, also accepted (optional) on `POST /emails`.
- [ ] `batch_id` column on `Email` — broadcast-only, never caller-settable on `/emails`.
- [ ] New tables: `broadcast_batches`, `broadcast_recipients`, `email_send_outbox`, `email_delivery_payloads`, `email_suppressions`.
- [ ] `EmailRenderingService` extracted from `SendEmailCommand`'s rendering helpers; both single-send and broadcast rendering share it.
- [ ] `SendBroadcastCommand` — idempotency check, one bulk suppression lookup, one transaction writing the batch + raw recipient rows. No rendering, no `Email` rows created synchronously.
- [ ] Prepare stage: `broadcast_prepare_publisher` (fast-path direct dispatch + periodic recovery sweep) + `prepare_broadcast_chunk_task` (renders content, creates `Email`/payload/outbox rows per non-suppressed recipient in a chunk).
- [ ] Send stage: `broadcast_outbox_publisher` (same two-trigger shape) + `send_broadcast_chunk_task` (calls `PostmarkProvider.send_batch` via Postmark's Bulk API, maps per-message results back individually).
- [ ] `EmailStatus.SUPPRESSED` (terminal) + `EmailLifecycleService.record_send_suppressed`.
- [ ] `EmailStatus.UNSUBSCRIBED` added to `_TERMINAL_STATUSES`.
- [ ] `PostmarkProvider.send_batch`, and `SubscriptionChange` webhook correctly parsed (not a blanket `subscriptionchange -> unsubscribed` mapping) with `Recipient`/`ChangedAt`/`SuppressSending`/`Origin`/`SuppressionReason`/`MessageStream`/nullable `MessageID` preserved.
- [ ] `SuppressionRepository` + `HandleSubscriptionChangeCommand`, invoked from `ProcessDeliveryEventsCommand` after the existing lifecycle write.
- [ ] `email.unsubscribed` NATS event via `tessera_sdk.infra.events`, published after the suppression commit.
- [ ] `GET /emails` extended with `batch_id`/`tag` filters; `GET /broadcasts/{batch_id}` for accept-time counts + live `prepared_count`.
- [ ] Config: `postmark_broadcast_stream_id`, `broadcast_chunk_size` (default 100).
- [ ] Celery: real tasks in `app/tasks/` for the first time, plus a beat schedule for the two recovery sweeps, plus eager-mode test config.

### Out of Scope (this iteration)

- Persistent audiences/subscriber lists (caller's list is the source of truth every call).
- A Sendly-hosted unsubscribe link/token/endpoint.
- Per-project/tenant Postmark broadcast stream or chunk-size configuration.
- `cc`/`bcc` on broadcast sends.
- Reconciling exact per-message outcomes before a transport-level chunk failure (whole-chunk retry double-send risk is accepted, see PRD Further Notes).
- A real-Redis-broker test environment (Celery eager mode only).
- Recipient list size limits/rate limiting.
- Any change to `/emails`'s request contract beyond optional `tags`/`metadata`.

### Dependencies

- `tessera_sdk.infra.events` (`Event`, `NatsEventPublisher`, `event_type`, `event_source`) — confirmed present in the locked `tessera-sdk` version; NATS publishing itself is a no-op when `nats_enabled` is false.
- `postmarker`'s `client.emails.send_batch` (`POST /email/batch`, hard-capped at 500 messages/call) — confirmed present in the installed library version.
- Celery + Redis (already a wired dependency, previously with zero real tasks).

---

## Key Decisions

| Decision | Rationale | Alternatives Considered |
|----------|-----------|-------------------------|
| Split accept/prepare/send into three stages instead of rendering inside `SendBroadcastCommand` | Keeps request-acceptance O(1) regardless of list size — the same timeout risk chunked *sending* was built to avoid would otherwise reappear one step earlier (per-recipient Mako render + inserts inside the request) | Render + create `Email` rows synchronously inside `SendBroadcastCommand` (rejected: reintroduces per-recipient-list-size request cost) |
| `EmailRenderingService` raises plain exceptions, not `HTTPException` | It's called from both a FastAPI request path (`SendEmailCommand`) and a Celery task with no HTTP context (`prepare_broadcast_chunk_task`); the task must catch failures per-recipient without one bad render blocking the rest of the chunk | Keep `HTTPException` and catch/rethrow generically in the task (rejected: leaks a web-framework concern into task code) |
| NATS subject passed to `publish_sync(event, subject)` is `event.event_type`, not the REST-style `event.subject` path | Confirmed by reading the actual pattern in the sibling `identies` repo (`app/commands/clients/create_client_command.py`) — `event.subject` is CloudEvents payload metadata only; the wire-level NATS subject is the dotted, prefixed `event_type` | Use `event.subject` (the REST path) as the NATS subject (rejected: doesn't match established sibling-service convention) |
| `EmailStatus.UNSUBSCRIBED` added to `_TERMINAL_STATUSES` alongside new `SUPPRESSED` | A later out-of-order/duplicate webhook (e.g. a delayed `Delivery` event) shouldn't be able to overwrite an unsubscribe; user confirmed this should be fixed as part of this work | Leave `UNSUBSCRIBED` non-terminal, only add `SUPPRESSED` as terminal (rejected per user decision) |
| Celery tasks always open their own fresh DB session in production; broadcast pipeline integration tests get a dedicated non-nested-transaction fixture instead of session-injection into task signatures | Keeps task code production-realistic (no test-only parameters); the existing `db` fixture's outer-transaction-per-test pattern is fundamentally incompatible with a second, independently-opened session seeing "committed" rows (normal Postgres cross-connection isolation, not a bug) | Inject `db: Session` as an explicit task parameter so tests can pass the same fixture session (rejected per user decision — makes task signatures test-shaped) |
| Bulk-insert `broadcast_recipients` via `db.add_all([...]) + db.commit()` | Matches the codebase's existing plain single-object `add`/`commit`/`refresh` repository style; no `bulk_insert_mappings`/Core-level bulk API used anywhere else in the repo | SQLAlchemy Core `bulk_insert_mappings` (rejected: would be the only such usage in the codebase, inconsistent with existing repository conventions) |
| `request_fingerprint` = SHA-256 hex digest of canonical (sorted-keys) JSON of `content_spec` + recipient list | No existing idempotency implementation anywhere in the codebase to pattern-match; needs a fresh, deterministic, order-independent-content comparison | Store the raw request JSON verbatim and compare byte-for-byte (rejected: fragile to key-ordering/whitespace differences between otherwise-identical retries) |

---

## Architecture

### Chosen Approach

Follow the PRD's Implementation Decisions directly — it is already a fully specified architecture (exact classes, tables, method signatures) rather than a set of options to choose between. This feature doc's role is to record how those decisions map onto this codebase's actual conventions (RBAC via `build_rbac_dependencies`, `SoftDeleteRepository` base class, migration style, DI-via-constructor for services) and to resolve the handful of implementation-level gaps the PRD left open (listed above under Key Decisions).

Three-stage pipeline:
1. **Accept** (sync, in-request): `SendBroadcastCommand` — idempotency check, one bulk suppression query, one transaction (batch + raw recipient rows). Returns immediately.
2. **Prepare** (async, chunked): `prepare_broadcast_chunk_task` — per chunk, recheck suppression, merge recipient attributes into template variables, render via `EmailRenderingService`, create `Email` + delivery payload + outbox rows.
3. **Send** (async, chunked): `send_broadcast_chunk_task` — per chunk, recheck suppression, call `PostmarkProvider.send_batch` (Postmark Bulk API), map per-message results back via `EmailLifecycleService`.

Each stage's publisher (`broadcast_prepare_publisher`, `broadcast_outbox_publisher`) has the same two-trigger shape: a synchronous fast-path dispatch immediately after the producing transaction commits, plus a periodic Celery-beat recovery sweep as a crash-recovery backstop.

### Trade-offs

- **Pros**: Request-acceptance time and per-recipient rendering/DB cost are both decoupled from list size; per-recipient status tracking and retry semantics are preserved even though dispatch/rendering/sending are chunk-shaped; single-send and broadcast rendering behavior cannot drift since both go through `EmailRenderingService`.
- **Cons / Mitigations**: Whole-chunk retry on a transport-level failure can double-send a subset of a chunk (Postmark's Bulk API has no per-message idempotency key) — accepted risk, bounded by keeping `broadcast_chunk_size` well under Postmark's 500 max (default 100). Two new async stages (prepare + send) both need worker deployment to actually run in every environment — an operational requirement introduced for the first time by this feature.

### Implementation Notes

- **Key files**:
  - `app/routers/broadcast.py`, `app/schemas/broadcast.py`, `app/commands/send_broadcast_command.py`
  - `app/services/email_rendering_service.py` (new, extracted from `app/commands/send_email_command.py`)
  - `app/services/broadcast_prepare_publisher.py`, `app/services/broadcast_outbox_publisher.py`
  - `app/tasks/prepare_broadcast_chunk_task.py`, `app/tasks/send_broadcast_chunk_task.py`
  - `app/repositories/suppression_repository.py`, `app/models/email_suppression.py`, `app/models/broadcast_batch.py`, `app/models/broadcast_recipient.py`, `app/models/email_delivery_payload.py`
  - `app/commands/providers/handle_subscription_change_command.py`
  - `app/events/email_events.py`
  - `app/providers/postmark_provider.py` (`send_batch`, `_map_pm_type` fix), `app/providers/base.py` (extend `EmailCreateRequest`/add batch types as needed)
  - `app/core/celery_app.py` (beat schedule), `tests/conftest.py` (eager-mode fixture, new non-nested-transaction fixture)
  - `alembic/versions/` new migration(s) for all new tables/columns
- **Extension points**: `EmailRenderingService` is now the single shared seam for any future template-resolution change; `PostmarkProvider.send_batch` follows the existing provider-strategy pattern so a second provider could implement it later.
- **Constraints**: `SendBroadcastCommand.execute()` must remain O(1) round-trips regardless of recipient count (explicit timing test per PRD Testing Decisions). `broadcast_chunk_size` is global config only (default 100, hard cap 500).

---

## Open Questions

_None outstanding — all identified ambiguities were resolved during Phase 3 (see Key Decisions)._

---

## Changelog

| Date | Change |
|------|--------|
| 2026-07-26 | Initial draft, approved to proceed to implementation |
