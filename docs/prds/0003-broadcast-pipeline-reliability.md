# 0003 — Broadcast Pipeline Reliability

## Problem Statement

Broadcast sending accepts a batch, prepares recipient-specific email payloads asynchronously, and sends those payloads asynchronously. This pipeline must remain correct when database writes fail, publishers run concurrently, Celery redelivers a task, or a worker stops partway through a task.

An accepted broadcast must not become permanently incomplete, and a recipient must not receive duplicate email merely because the system recovered work or retried a task.

## Goal

Make the broadcast prepare and send pipeline durable, recoverable, and concurrency-safe while preserving the existing asynchronous response contract.

## Requirements

### Atomic broadcast acceptance

- Creating a broadcast batch and its `broadcast_recipients` rows must occur in one database transaction.
- The transaction must include the durable idempotency record, the batch counts, and every submitted recipient row.
- The system must not return a successful broadcast response until this transaction commits.
- If the transaction fails, no idempotency record or partially created batch may remain visible. A retry using the same idempotency key must be able to create the batch normally.
- Prepare-stage dispatch must occur only after the acceptance transaction commits.

### Accurate recipient counts

- `queued_count` and `suppressed_count` represent recipient rows, not distinct email-address values.
- Duplicate recipient addresses are allowed and count once per submitted recipient.
- If the same suppressed address appears multiple times, every matching recipient contributes to `suppressed_count`.
- The invariant `queued_count + suppressed_count == submitted recipient count` must hold for every accepted broadcast.

### Durable, exclusive prepare work

- A `broadcast_recipient` may be prepared at most once.
- Before rendering or creating any `Email`, delivery payload, or outbox entry, a prepare worker must atomically claim its recipient rows.
- Claims must be safe when a direct publisher, a periodic recovery sweep, and a redelivered Celery task run concurrently.
- A claim records a token, attempt count, and lease timestamp. A recovery sweep may reclaim only an expired lease.
- Preparing a chunk is atomic: for every successfully prepared recipient, the `Email` row, immutable delivery payload, outbox row, and prepared-state transition commit in the same transaction.
- A failed or interrupted prepare transaction must leave no queued `Email` without its delivery payload and outbox row, and must leave the recipient eligible for safe recovery.
- The data model must enforce at most one prepared `Email` per `broadcast_recipient` (for example, through a unique foreign key or unique constraint), as a final guard against duplicate preparation.

### Durable, exclusive send work

- An outbox entry may be sent by only one active worker at a time.
- Before calling Postmark, a send worker must atomically claim only pending outbox rows and record a claim token, attempt count, and lease timestamp.
- The send task must send only the rows it successfully claimed; it must ignore IDs that are already processed or actively claimed by another worker.
- A recovery sweep may reclaim an outbox entry only after its claim lease expires.
- On a successful provider response, the worker must record each recipient result and finalize the corresponding claimed outbox row.
- On a provider-level transport failure, the claimed rows remain recoverable after the retry policy or lease expiry. The established, documented risk of duplicate delivery after an ambiguous provider response remains unchanged.

### Observable recovery state

- `broadcast_recipients` and `email_send_outbox` must expose enough state to distinguish pending, claimed, completed, and retryable work.
- Broadcast status responses must include counts for at least pending, claimed/in-progress, prepared, sent, failed, and suppressed recipients.
- Operational logs and metrics must include batch ID, chunk/claim token, attempt count, and recovery reason for reclaimed work.

## Data Model Additions

`broadcast_recipients` gains:

- `prepare_state` (`pending`, `claimed`, `prepared`, `failed`)
- `prepare_claim_token`
- `prepare_claimed_at`
- `prepare_attempt_count`
- a unique relationship to the prepared `Email` row

`email_send_outbox` gains:

- `state` (`pending`, `claimed`, `processed`)
- `claim_token`
- `claimed_at`
- `attempt_count`
- `processed_at`
- `last_error`

Lease duration and maximum retry behavior are configurable operational settings. A lease must be long enough for the largest permitted chunk to render or send, with a safety margin.

## Acceptance Criteria

1. A database error while creating a batch or any recipient row leaves no visible batch/idempotency record; a retry with the same idempotency key succeeds.
2. Repeating a suppressed address twice produces two suppressed recipient rows and increments `suppressed_count` by two.
3. Concurrent prepare tasks for the same recipient IDs create exactly one `Email`, one delivery payload, and one outbox row per recipient.
4. A worker failure between preparing an email and creating its outbox row leaves neither committed; recovery can prepare the recipient once.
5. Concurrent or redelivered send tasks for the same outbox IDs result in one active provider call for each claimed entry.
6. A recovery sweep does not redispatch actively claimed work, but safely reclaims expired claims.
7. Every broadcast status response reconciles with its recipient rows: accepted recipient count equals the sum of terminal and non-terminal recipient states.

## Out of Scope

- Eliminating the accepted duplicate-send risk after an ambiguous Postmark transport failure.
- Changing broadcast content, template rendering semantics, suppression policy, or the public `POST /broadcasts/send` response shape.
- Per-project configuration of lease durations or chunk sizes.
