# Broadcast Sending

Sendly's broadcast feature fans a single piece of content out to a list of recipients in one API call (`POST /broadcasts/send`), with light per-recipient personalization, automatic skipping of unsubscribed recipients, and delivery via Postmark's Bulk API. Design rationale lives in [`docs/prds/0002-broadcast-sending.md`](prds/0002-broadcast-sending.md) and [`docs/features/feat-001/feature.md`](features/feat-001/feature.md); this page documents the resulting data flow and schema.

## API

### `POST /broadcasts/send`

```json
{
  "project_id": "5b8a...",
  "from_email": "news@example.com",
  "subject": "Hello ${first_name}",
  "html": "<p>Hi ${first_name}, ...</p>",
  "template_id": null,
  "template_alias": null,
  "template_variables": {},
  "custom_headers": {},
  "idempotency_key": "campaign-2026-07-launch",
  "tags": ["campaign-x"],
  "metadata": {"source": "crm"},
  "recipients": [
    {"email": "a@example.com", "first_name": "Alice", "attributes": {"plan": "Pro"}},
    {"email": "b@example.com"}
  ]
}
```

Returns immediately (before the prepare/send stages have run):

```json
{"batch_id": "b3f1...", "queued_count": 1, "suppressed_count": 1}
```

`cc`, `bcc`, `priority`, and `batch_id` are intentionally not accepted — Sendly generates `batch_id`, and `cc`/`bcc` have no coherent per-recipient meaning for a fan-out send.

### `GET /broadcasts/{batch_id}?project_id=...`

Accept-time counts plus live prepare-stage progress:

```json
{"batch_id": "b3f1...", "queued_count": 1, "suppressed_count": 1, "prepared_count": 1}
```

### `GET /emails?batch_id=...&tag=...`

The existing `/emails` listing, extended with `batch_id` (exact match) and `tag` (exact membership in the `tags` array) filters, so a broadcast's individual per-recipient delivery statuses can be queried the same way single-sent emails are.

## Configuration

| Setting | Env var | Default | Notes |
|---|---|---|---|
| `postmark_broadcast_stream_id` | `POSTMARK_BROADCAST_STREAM_ID` | `""` | Postmark's Broadcast message stream ID. Set on every broadcast's `EmailDeliveryPayload.message_stream`; single-sends leave this unset and use Postmark's default transactional stream. One global value — no per-project override. |
| `broadcast_chunk_size` | `BROADCAST_CHUNK_SIZE` | `100` | Recipients per prepare/send Celery task. Validated `<= 500` — Postmark's Bulk API (`POST /email/batch`) hard-caps a single call at 500 messages. |

## Idempotency

`SendBroadcastCommand` computes `request_fingerprint` as a SHA-256 hex digest over a canonical (sorted-keys) JSON dump of `{content_spec, recipients}`. On a request carrying an `idempotency_key`:

- **Key seen before, same fingerprint** → returns the original batch's `{batch_id, queued_count, suppressed_count}` without creating anything new.
- **Key seen before, different fingerprint** → `409 Conflict`.
- **Key not seen** → proceeds normally.

The `(project_id, idempotency_key)` partial unique index (non-null keys only) on `broadcast_batches` is the durable backstop for this check.

## Status values

`Email.status` (see `app/constants/email.py`): `queued → sent → delivered → opened/clicked`, or one of the terminal outcomes — `bounced`, `complained`, `dropped`, `failed`, `unsubscribed`, `suppressed`. Once an `Email` reaches a terminal status, `EmailLifecycleService` never overwrites it, even from a later out-of-order webhook. `suppressed` is written only by `EmailLifecycleService.record_send_suppressed`, called from `send_broadcast_chunk_task` when a recipient turns out to be suppressed at send time.

## Why three stages

A naive implementation would render each recipient's content and call Postmark once per recipient, all inside the original HTTP request — that doesn't scale to large lists without risking a request timeout. Sendly splits the work into three stages so the only synchronous, in-request work is O(1) round-trips regardless of list size:

1. **Accept** (sync, in the HTTP request) — one bulk suppression lookup, one bulk insert of raw recipient data. No rendering, no `Email` rows yet.
2. **Prepare** (async, chunked) — renders each recipient's content and creates their `Email` row, delivery payload, and outbox entry.
3. **Send** (async, chunked) — sends a chunk's payloads to Postmark's Bulk API in one HTTP call and records each recipient's outcome.

```mermaid
flowchart LR
    subgraph Accept["1. Accept (synchronous, in-request)"]
        A1["POST /broadcasts/send"] --> A2["SendBroadcastCommand"]
        A2 --> A3["bulk suppression lookup\n(1 query)"]
        A2 --> A4["insert BroadcastBatch\n+ BroadcastRecipient rows\n(1 transaction)"]
    end

    subgraph Prepare["2. Prepare (async, chunked)"]
        P1["prepare_broadcast_chunk_task"] --> P2["recheck suppression\n(bulk)"]
        P2 --> P3["EmailRenderingService\n(Mako render)"]
        P3 --> P4["create Email +\nEmailDeliveryPayload +\nEmailSendOutbox rows"]
    end

    subgraph Send["3. Send (async, chunked)"]
        S1["send_broadcast_chunk_task"] --> S2["recheck suppression\n(bulk)"]
        S2 --> S3["PostmarkProvider.send_batch\n(1 HTTP call/chunk)"]
        S3 --> S4["record per-recipient\nsuccess / failure /\nsuppressed"]
    end

    A4 -- "dispatch fast-path\n(after commit)" --> P1
    P4 -- "dispatch fast-path\n(after commit)" --> S1

    Sweep1["prepare_recovery_sweep\n(Celery-beat, every 60s)"] -. "crash backstop" .-> P1
    Sweep2["outbox_recovery_sweep\n(Celery-beat, every 60s)"] -. "crash backstop" .-> S1
```

Both dispatches follow the same two-trigger shape: a synchronous fast-path call immediately after the producing transaction commits, plus a periodic Celery-beat recovery sweep that picks up anything left behind by a crash between commit and dispatch.

## Request/response sequence

```mermaid
sequenceDiagram
    participant Caller
    participant Router as POST /broadcasts/send
    participant Cmd as SendBroadcastCommand
    participant DB
    participant Prep as prepare_broadcast_chunk_task
    participant Send as send_broadcast_chunk_task
    participant Postmark

    Caller->>Router: recipients + content options
    Router->>Cmd: execute(request)
    Cmd->>DB: is_suppressed_bulk(project_id, emails)
    DB-->>Cmd: suppressed emails
    Cmd->>DB: INSERT BroadcastBatch + BroadcastRecipient rows
    Cmd-->>Router: {batch_id, queued_count, suppressed_count}
    Router-->>Caller: 200 OK (immediate)

    Cmd->>Prep: dispatch chunk(s) [async]
    Prep->>DB: recheck suppression (bulk)
    Prep->>Prep: render content (EmailRenderingService)
    Prep->>DB: INSERT Email + EmailDeliveryPayload + EmailSendOutbox
    Prep->>Send: dispatch chunk(s) [async]

    Send->>DB: recheck suppression (bulk)
    Send->>Postmark: POST /email/batch (1 call/chunk)
    Postmark-->>Send: per-message results
    Send->>DB: record success / failure / suppressed per recipient
    Send->>DB: mark EmailSendOutbox processed
```

## Entity relationships

```mermaid
erDiagram
    EMAILS ||--o| EMAIL_DELIVERY_PAYLOADS : "has one"
    EMAILS ||--o| EMAIL_SEND_OUTBOX : "has one"
    EMAILS }o--o| BROADCAST_BATCHES : "batch_id (loose, string)"
    BROADCAST_BATCHES ||--o{ BROADCAST_RECIPIENTS : "has many"

    EMAILS {
        uuid id PK
        uuid project_id
        string to_email
        string status
        string batch_id "broadcast-only, never caller-settable"
        jsonb tags
        jsonb metadata "column name; Python attr is metadata_"
    }

    BROADCAST_BATCHES {
        uuid id PK
        uuid project_id
        string batch_id "server-generated UUID, public identifier"
        string idempotency_key
        string request_fingerprint
        jsonb content_spec "unrendered shared content"
        int queued_count
        int suppressed_count
    }

    BROADCAST_RECIPIENTS {
        uuid id PK
        uuid broadcast_batch_id FK
        string email
        string first_name
        string last_name
        jsonb attributes
        bool suppressed
        bool prepared
    }

    EMAIL_DELIVERY_PAYLOADS {
        uuid id PK
        uuid email_id FK "unique"
        string from_email
        string to_email
        string subject
        text html
        text text
        jsonb attachments
        jsonb custom_headers
        string message_stream
    }

    EMAIL_SEND_OUTBOX {
        uuid id PK
        uuid email_id FK "unique"
        datetime processed_at "null = pending"
    }

    EMAIL_SUPPRESSIONS {
        uuid id PK
        uuid project_id
        string email
        datetime unsubscribed_at
        string source
    }
```

Note: `Email.batch_id` (a string) and `BroadcastBatch.batch_id` (the same string) are the *public* identifier used for querying (`GET /emails?batch_id=`, `GET /broadcasts/{batch_id}`). `BroadcastRecipient.broadcast_batch_id` is a real foreign key to `BroadcastBatch.id` (the internal UUID primary key) — the two `batch_id`-shaped names are intentionally different concepts; see [Naming](#naming) below.

## Entities

### `Email` (extended)

The existing per-recipient email row, extended with three broadcast-related columns. Every recipient of a broadcast gets exactly one `Email` row, created by the prepare stage — same status lifecycle (`queued → sent/failed/...`) and query surface (`GET /emails/{id}`) as single-send emails.

| Column | Type | Notes |
|---|---|---|
| `batch_id` | `string`, indexed | The owning broadcast's public `batch_id`. `NULL` for single-sends via `/emails`. Never caller-settable. |
| `tags` | `jsonb` (array of strings) | Copied from the batch's `content_spec.tags` at prepare time. Also settable on single-send. |
| `metadata` | `jsonb` (object) | Copied from `content_spec.metadata`. Python attribute is `metadata_` — `metadata` is reserved on SQLAlchemy's declarative `Base` (it holds the schema's `MetaData` registry). |

Written by: `EmailRepository.create_email` (called from `prepare_broadcast_chunk_task` for broadcasts, `SendEmailCommand` for single-sends). Status transitions after creation go exclusively through `EmailLifecycleService`.

### `BroadcastBatch`

One row per accepted `POST /broadcasts/send` request — the durable idempotency authority and the source of the shared, *unrendered* content every recipient's `Email` is rendered from.

| Column | Type | Notes |
|---|---|---|
| `id` | `uuid` PK | Internal identifier; other tables FK to this. |
| `project_id` | `uuid` | Tenant scope. |
| `batch_id` | `string` | Server-generated UUID string — the *public* identifier callers use to query (`GET /broadcasts/{batch_id}`). Unique per `(project_id, batch_id)`. |
| `idempotency_key` | `string`, nullable | Caller-supplied. Unique per `(project_id, idempotency_key)` when non-null. |
| `request_fingerprint` | `string` | SHA-256 of the canonical `(content_spec, recipients)` payload — used to detect a retried idempotency key with *different* content (→ `409`). |
| `content_spec` | `jsonb` | The shared, not-yet-rendered content options (`html`/`text`/`template_id`/`template_alias`/`template_variables`/`subject`/`from_email`/`custom_headers`/`attachments`/`tags`/`metadata`). Stored as plain JSON, but the read/write boundary is the typed `app.schemas.broadcast.ContentSpec` — `SendBroadcastCommand` writes `ContentSpec.from_request(req).model_dump(mode="json")`, `prepare_broadcast_chunk_task` reads it back via `ContentSpec.model_validate(batch.content_spec)`. Avoids `dict.get("some_key")` string lookups scattered across the pipeline. |
| `queued_count`, `suppressed_count` | `int` | Fixed at accept time — the counts returned in the `POST /broadcasts/send` response and later re-shown by `GET /broadcasts/{batch_id}`. |

Written once by `SendBroadcastCommand`, in the same transaction as the batch's `BroadcastRecipient` rows. Never updated afterward.

### `BroadcastRecipient`

The raw, unrendered per-recipient data submitted with the request — one row per recipient, created in bulk by `SendBroadcastCommand` and consumed (and marked `prepared`) by `prepare_broadcast_chunk_task`. Distinct from `Email`: a suppressed recipient gets a `BroadcastRecipient` row but never an `Email` row.

| Column | Type | Notes |
|---|---|---|
| `broadcast_batch_id` | `uuid` FK → `broadcast_batches.id` | |
| `email`, `first_name`, `last_name` | `string` | `email` required; names optional. |
| `attributes` | `jsonb` | Arbitrary per-recipient personalization data, merged into `content_spec.template_variables` at render time. |
| `suppressed` | `bool` | Set from the bulk suppression lookup at accept time. Rows with `suppressed=true` are never dispatched to the prepare stage. |
| `prepared` | `bool` | Set once the prepare stage has processed the row (whether or not it produced an `Email` — a recipient suppressed *since* acceptance also gets `prepared=true` with no `Email` row). |

`GET /broadcasts/{batch_id}`'s `prepared_count` is `COUNT(*) WHERE broadcast_batch_id = ? AND prepared = true`.

### `EmailDeliveryPayload`

The immutable, fully-resolved delivery payload for one `Email` — written once by the prepare stage, read verbatim by the send stage. Exists so the send stage never re-fetches a template or depends on request-only recipient data (both of which may have changed or vanished by send time).

| Column | Type | Notes |
|---|---|---|
| `email_id` | `uuid` FK → `emails.id`, unique | One payload per email. |
| `from_email`, `to_email`, `subject`, `html`, `text` | | Fully rendered — no further templating happens downstream. |
| `attachments`, `custom_headers` | `jsonb` | |
| `message_stream` | `string`, nullable | The configured Postmark broadcast stream ID for broadcasts; `NULL` for single-sends (Postmark's default transactional stream applies). |

Written by `prepare_broadcast_chunk_task`. Never updated.

### `EmailSendOutbox`

One pending-send marker per `Email`, consumed (chunked) by the send stage — the mechanism both the fast-path dispatch and the recovery sweep use to find work.

| Column | Type | Notes |
|---|---|---|
| `email_id` | `uuid` FK → `emails.id`, unique | |
| `processed_at` | `datetime`, nullable, indexed | `NULL` = pending. Set once `send_broadcast_chunk_task` has recorded a terminal outcome (success, failure, or suppressed) for the email. |

Written by `prepare_broadcast_chunk_task` (creation), updated by `send_broadcast_chunk_task` (`mark_processed`).

### `EmailSuppression`

A project-scoped recipient who has unsubscribed — checked (in bulk) at every stage of every future broadcast, and by `send_broadcast_chunk_task` as a final recheck immediately before sending.

| Column | Type | Notes |
|---|---|---|
| `project_id` | `uuid` | |
| `email` | `string` | Unique per `(project_id, email)`. |
| `unsubscribed_at` | `datetime` | |
| `source` | `string` | e.g. `postmark:Recipient`, `postmark:Admin`. |

Written/removed by `HandleSubscriptionChangeCommand`, driven by Postmark's `SubscriptionChange` webhook (see below) — never by the broadcast send path itself.

## Unsubscribe flow

Postmark's `SubscriptionChange` webhook is the only way a suppression is created or removed. `SuppressSending=true` distinguishes an unsubscribe from `SuppressSending=false` (a reactivation) — this is **not** a blanket "any SubscriptionChange = unsubscribed" mapping.

```mermaid
sequenceDiagram
    participant Postmark
    participant Router as POST /providers/postmark/delivery-events
    participant PDE as ProcessDeliveryEventsCommand
    participant Lifecycle as EmailLifecycleService
    participant HSC as HandleSubscriptionChangeCommand
    participant DB
    participant NATS

    Postmark->>Router: SubscriptionChange webhook
    Router->>PDE: execute(payload)
    PDE->>PDE: parse_webhook() → type = "unsubscribed" | "resubscribed"
    PDE->>Lifecycle: record_webhook_event(email, type)
    Lifecycle->>DB: write EmailEvent + advance Email.status

    alt type is unsubscribed or resubscribed
        PDE->>HSC: execute(email, raw_payload)
        alt SuppressSending = true
            HSC->>DB: upsert EmailSuppression
            alt Origin = "Recipient"
                HSC->>NATS: publish_sync(email.unsubscribed)
            end
        else SuppressSending = false
            HSC->>DB: remove EmailSuppression
        end
    end
```

A `SubscriptionChange` with a null `MessageID` can't be resolved to an `Email`/`project_id` — `HandleSubscriptionChangeCommand` logs it for operations and skips the suppression mutation rather than guessing.

## Naming

Three different "batch id" concepts appear across this feature — worth being explicit about, since the names are easy to confuse:

| Name | Type | What it identifies |
|---|---|---|
| `BroadcastBatch.id` | `uuid` (PK) | Internal row identifier. What `BroadcastRecipient.broadcast_batch_id` actually references. |
| `BroadcastBatch.batch_id` / `Email.batch_id` | `string` | The *public* identifier — what callers pass to `GET /broadcasts/{batch_id}` and `GET /emails?batch_id=`. |
| `BroadcastRecipient.broadcast_batch_id` | `uuid` (FK) | Foreign key to `BroadcastBatch.id` — despite the similar name, this is **not** the same value as `BroadcastBatch.batch_id`. |

## Recovery sweeps

Both async stages dispatch synchronously right after their producing transaction commits — the periodic sweeps below exist only to catch rows left behind by a crash between commit and dispatch; they are not the normal path.

```mermaid
flowchart TB
    Beat["Celery beat\n(every 60s)"] --> S1["prepare_recovery_sweep_task"]
    Beat --> S2["outbox_recovery_sweep_task"]
    S1 --> Q1["BroadcastRecipient rows:\nprepared=false, suppressed=false,\ncreated_at < now-5min"]
    S2 --> Q2["EmailSendOutbox rows:\nprocessed_at IS NULL,\ncreated_at < now-5min"]
    Q1 --> D1["dispatch prepare_broadcast_chunk_task\nper stale batch\n(chunk boundary never spans batches)"]
    Q2 --> D2["dispatch send_broadcast_chunk_task\ngrouped by Email.batch_id\n(chunk boundary never spans batches)"]
```

## Known limitations

- **No exactly-once guarantee across a crash mid-chunk.** `prepare_broadcast_chunk_task` commits each recipient's `Email`/payload/outbox rows individually rather than as one transaction for the whole chunk, and `BroadcastRecipient.prepared` is only set once, after the loop finishes. If the task dies partway through, already-created rows for earlier recipients stay `prepared=false` — the recovery sweep will re-dispatch them and duplicate those rows (a real send, twice). The recovery sweeps also have no "claimed" marker, so a slow-but-healthy chunk task that outlives the 5-minute grace period can be re-dispatched by the sweep while still in flight.
- **Accepted, separate risk**: a whole-chunk retry on a Postmark transport failure (not the crash case above) can double-send a subset of a chunk, since the Bulk API has no per-message idempotency key. This one is an intentional trade-off from the original design (see the PRD's Further Notes), not a bug.
- A fix for the first limitation — durable claim tokens/leases on `broadcast_recipients` and `email_send_outbox`, atomic per-chunk transactions, and a unique constraint tying an `Email` to the `broadcast_recipient` that produced it — is specified but not yet implemented; see [`docs/prds/0003-broadcast-pipeline-reliability.md`](prds/0003-broadcast-pipeline-reliability.md).
- `Email.to_email` only stores the first address even for a multi-recipient single-send `to` list (Postmark itself now receives all of them, comma-joined) — tracked in [issue #82](https://github.com/tesserahq/sendly/issues/82). Not applicable to broadcasts, where every recipient already gets its own `Email` row.
