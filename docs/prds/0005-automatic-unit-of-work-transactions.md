# PRD 0005: Automatic Unit-of-Work Transactions

**Status:** Proposed

## Problem Statement

Sendly's repositories currently decide when database work becomes durable. Most create, update, delete, soft-delete, lifecycle, broadcast, suppression, delivery-payload, and outbox mutations call `commit()` themselves. A command or Celery task that composes several repository methods therefore crosses hidden transaction boundaries even though callers treat the work as one business operation.

This conflicts with the guarantees already required of the broadcast pipeline. Accepting a broadcast must atomically create its batch and recipients. Preparing a recipient must atomically create the email, immutable payload, outbox entry, and recipient link. Today those steps can commit independently, leaving partial batches or queued emails without all required artifacts. Celery dispatch also relies on undocumented repository commits happening before `.delay()`.

Single-email sending has an equally important but different requirement. The queued email must be durable before Postmark is called, but the database transaction and connection should not remain open during network I/O. Provider success or failure must then be recorded in a fresh transaction. Those phases currently occur accidentally through repository commits rather than through an explicit workflow contract. Broadcast send workers have the same problem at chunk scale.

Transaction ownership is split across several mechanisms:

- the FastAPI database dependency opens and closes a session without committing or rolling back;
- a commit-on-success context manager owns Celery task sessions;
- an unused database middleware implements another transaction policy;
- authentication and onboarding construct repositories through the shared SDK's service factory;
- repositories and the settings manager finalize transactions directly.

Developers cannot safely compose repository methods without inspecting their implementations. Tests can hide this because the normal fixture wraps a session in an outer transaction that survives inner `commit()` calls. Moving every commit into commands would only transfer responsibility to more developers. Ordinary code must work automatically, while the few workflows that intentionally cross a durability boundary use an explicit, allowlisted early commit.

## Goal

Give every Sendly execution entry point an automatic Unit of Work using SQLAlchemy's existing `Session`, make repositories non-committing persistence adapters, and add only thin post-commit and savepoint helpers around native SQLAlchemy behavior.

Sendly will be the smaller pilot for the design intended for Linden. It must validate the repository pattern, automatic commit behavior, external-service phases, Celery integration, and architecture enforcement before the design is rolled out to the larger API.

## Solution

API requests, Celery tasks, authentication/onboarding operations, and standalone recovery jobs will use one `session_scope()` behavior. Each execution opens one SQLAlchemy `Session`, commits when execution succeeds, rolls back when an exception escapes, and always closes. SQLAlchemy's `Session` is the Unit of Work; Sendly will not add a custom Unit-of-Work class, phase controller, rollback controller, or transaction framework.

Repositories query, stage mutations, and flush only when generated identifiers, database defaults, locks, or early constraint validation are required. A flush is never a durability boundary. Every repository constructed with the managed session participates in the same transaction without flags or transaction-aware method variants.

The database module adds only two helpers around SQLAlchemy and one restricted native operation:

- `on_commit()` registers work that may run only after the current outer transaction commits;
- `savepoint()` wraps `Session.begin_nested()` and discards hooks registered inside a failed savepoint;
- an allowlisted top-level workflow may call `Session.commit()` early before external I/O, after which SQLAlchemy autobegins a fresh transaction on later database access.

There is no rollback-only mechanism. Code that must prevent the normal success commit raises, and global exception handlers translate domain exceptions into HTTP responses. An error that is intentionally handled so processing can continue must be contained by a savepoint.

Broadcast acceptance will stage the batch and all recipients atomically. Preparation writes will commit atomically and send dispatch will run after commit. Single-email and broadcast sends will persist or claim work, finish the database phase and release the connection, call Postmark, and then use a fresh phase to record outcomes. NATS unsubscribe publication will run only after the corresponding database changes commit.

This design does not make PostgreSQL, Celery, Postmark, and NATS one distributed transaction. Reliable asynchronous work continues to use durable outbox or claim state and recovery sweeps. Postmark's documented ambiguous-response duplicate-delivery risk remains explicit.

## User Stories

1. As an API client, I want an accepted broadcast to contain the complete batch and recipient set or nothing.
2. As a recipient, I want a prepared email, payload, outbox entry, and recipient association committed together.
3. As an API client, I want success to mean database commit completed before the response.
4. As a developer, I want requests and tasks to commit on success automatically.
5. As a developer, I want escaping exceptions to roll back automatically without losing their original type or cause.
6. As a developer, I want all repositories in an operation to share one Unit of Work without transaction flags.
7. As a developer, I want flushed writes visible in the current session but invisible to other sessions before commit.
8. As a developer, I want repositories to express domain persistence rather than transaction control.
9. As a developer, I want nested commands and services to join the current Unit of Work automatically.
10. As a worker developer, I want Celery tasks to have the same commit and rollback semantics as HTTP requests.
11. As a developer sending one email, I want queued state durable before Postmark and no database connection held during the call.
12. As a developer sending a broadcast chunk, I want claims durable before Postmark and outcomes reconciled afterward.
13. As a developer, I want only identifiers and immutable data to cross phase boundaries.
14. As an operator, I want logs to distinguish persistence, provider-call, and reconciliation failures.
15. As an operator, I want provider success followed by reconciliation failure to leave observable, recoverable state.
16. As a developer dispatching Celery work, I want publication only after another session can see its input rows.
17. As an operator, I want failed immediate dispatch to leave pending work for recovery sweeps.
18. As a developer publishing unsubscribe events, I want NATS publication only after database commit.
19. As a developer processing a batch, I want explicit savepoints when one bad item may be skipped.
20. As a developer handling an expected error after writes, I want to raise and let the execution boundary roll back, or contain an intentional partial failure in a savepoint.
21. As a test author, I want durability verified from an independent PostgreSQL session.
22. As a test author, I want shared adapter contract tests for HTTP and Celery.
23. As a maintainer, I want CI to reject transaction-finalization calls outside infrastructure.
24. As a maintainer, I want CI to reject unmanaged application session construction.
25. As a maintainer, I want the unused middleware and duplicate session helper removed.
26. As a Linden maintainer, I want Sendly's pilot findings documented before the larger migration.

## Implementation Decisions

- The execution entry point owns transaction completion. Managed adapters cover HTTP dependency execution, Celery tasks, SDK-driven authentication/onboarding, and recovery jobs.
- The HTTP dependency is function-scoped so commit or rollback finishes before the response is sent. A commit failure is an API failure.
- SQLAlchemy's `Session` is the Unit of Work. A small database helper module owns session construction and provides the HTTP dependency, `session_scope()`, `on_commit()`, and `savepoint()`; no custom transaction object or controller hierarchy is introduced.
- The non-HTTP scope wraps the shared SDK's existing commit-on-success context manager instead of reimplementing commit, rollback, and close behavior.
- The HTTP dependency is asynchronous even though the session remains synchronous, so its context variable remains visible to route code rather than being isolated in FastAPI's threadpool.
- A context variable identifies the active session for `on_commit()` without requiring transaction plumbing through publisher signatures.
- Receiving the managed session is the entire interface for ordinary code. Developers do not manually enter a Unit of Work or annotate commands as transactional.
- Only allowlisted top-level workflows may commit early. Repositories and nested operations cannot commit their caller's work.
- An early `Session.commit()` flushes and commits, runs hooks registered for that transaction, expires ORM instances, releases the connection, and leaves the session open. Later database access starts a fresh transaction through SQLAlchemy autobegin.
- Every allowlisted early commit has a named phase in its adjacent comment and structured log. There is no phase API.
- An early commit is irreversibly durable. Later failure requires retry, reconciliation, persisted workflow state, or compensation; it is not described as a rollback.
- Repositories remain cohesive, domain-oriented persistence adapters. The migration does not require one repository per table or a wholesale domain-model rewrite.
- Repository mutations add, update, or delete and flush only when necessary. They never commit, roll back, close, begin a root transaction, or accept transaction-control flags.
- Persistence-aware services and the settings manager follow the repository rule and share the caller's managed session.
- Domain exceptions propagate unchanged. Translated low-level exceptions use typed errors and retain the original cause.
- Code that catches an error after writes or a failed flush must re-raise it or contain it in a savepoint. Returning normally after an uncontained write failure is prohibited.
- Savepoints are opt-in and only support an explicit partial-success contract.
- `savepoint()` uses `Session.begin_nested()` and records the current hook-list position. If the savepoint fails, hooks registered since that position are discarded before the exception is re-raised.
- `on_commit()` stores hooks on the session. The outermost successful commit runs them in registration order; root rollback clears them; savepoint release does not run them.
- Each hook failure is logged with its name and correlation context, is swallowed, and does not prevent later hooks from running. A hook cannot use the committing session for SQL.
- Calling `on_commit()` without an active session runs the hook immediately, while architecture tests prevent mutation commands from accidentally depending on that fallback.
- Post-commit callbacks are for best-effort or recoverable notifications. Their failure cannot roll back committed data or turn a committed HTTP request into an error response.
- Required external work uses durable outbox or claim state. Recovery workers remain the backstop when immediate dispatch fails.
- Data crossing phases consists of identifiers and immutable values. Later phases reload authoritative state.
- Default SQLAlchemy expiration behavior is retained and covered by response-serialization and phase tests.

### Broadcast acceptance and preparation

- Acceptance stages its idempotency record, batch counts, batch row, and every recipient in one transaction.
- Prepare dispatch is post-commit work. Dispatch failure leaves committed recipients discoverable by the recovery sweep.
- Prepare claims follow the durable lease and exclusivity requirements in PRD 0003.
- A prepared chunk stages email, immutable payload, outbox entry, recipient link, prepared state, and counters atomically.
- Rendering failures remain per-recipient skips because they occur before that recipient's writes. A database failure rolls back the chunk unless product requirements later introduce database-level partial success with savepoints.
- Send dispatch occurs only after the preparation transaction commits.

### Single-email provider workflow

- Single-email sending is a multi-phase workflow.
- The first phase renders and persists the queued email, then performs an allowlisted early commit annotated as the queued phase. The provider request crosses the seam as immutable data.
- Postmark is called with no open database transaction.
- A fresh phase reloads the email and records sent state and provider identifier, or failed state and error details.
- A normal provider-declared failure is committed and returned under the existing API contract.
- An ambiguous provider result or reconciliation failure leaves the queued row as observable recovery state. The service must not blindly resend because this path has no safe provider idempotency key.
- The pilot defines alerting and manual reconciliation for indefinitely queued single emails. Automatic ambiguous-send replay is out of scope.

### Broadcast provider workflow

- A send worker claims eligible outbox rows under PRD 0003's claim model and performs an allowlisted early commit annotated as the claim phase.
- It materializes immutable delivery requests before that commit and calls Postmark bulk with no open transaction.
- A fresh phase atomically records provider results, lifecycle events, processed outbox state, and batch counters.
- Transport failure leaves claims recoverable by lease and retry policy. The accepted ambiguous-response duplicate risk is unchanged.
- Missing payload and suppressed outcomes commit together with outbox finalization.
- Transaction phases complement durable claims; they do not provide concurrency exclusivity themselves.

### Webhook and event workflow

- All events from one webhook use the request's managed `Session`.
- Because the current contract processes later events after one failure, each event uses an explicit savepoint. Its lifecycle, suppression, and counter writes roll back together on failure.
- Successful events commit together at request completion. Outer commit failure returns failure to the provider and persists none of that delivery.
- Recipient-originated unsubscribe publication to NATS is post-commit and remains best-effort unless a future NATS outbox is required.
- Event payloads are materialized before commit and do not depend on live ORM instances afterward.

### Session unification and enforcement

- The shared database manager provides the engine, session factory, and existing commit-on-success context manager, but only the database helper module constructs application sessions.
- The FastAPI dependency becomes the managed HTTP dependency; test overrides target it.
- Celery tasks replace the duplicate commit-on-success helper with `session_scope()`.
- The unused database middleware is removed.
- Authentication and onboarding factories receive managed sessions. If the SDK lifecycle cannot support this, the integration is wrapped or moved behind an application-owned entry point.
- Static AST-based architecture tests reject rollback, close, root-transaction calls, unmanaged session construction, and legacy session helpers outside infrastructure and tests. They reject commit everywhere except the database module and allowlisted top-level workflows.
- Each early-commit allowlist entry records the module, reason, commit points, and owner. Violations report the module, function, line, and forbidden call.
- The initial Sendly allowlist contains only the single-email top-level send workflow and the broadcast send worker's claim boundary. Additional entries require a documented external-I/O or checkpointing reason.
- The broadcast publisher services and unsubscribe NATS publisher register their existing dispatch operations through `on_commit()`; Sendly does not introduce a generic event gateway solely for transaction handling.
- The architecture guards begin in reporting mode with a measured baseline, shrink with every complete vertical slice, and become blocking at zero.
- Migrate in this order: session helpers, post-commit infrastructure, framework contract tests, and reporting guards; entry points and shared soft-delete mechanics; complete repository/command vertical slices; external multi-phase workflows; zero-baseline enforcement.
- Post-commit infrastructure migrates before repository commits are removed so external dispatch cannot accidentally move ahead of durability.
- Claim-state schema from PRD 0003 remains a prerequisite for concurrency-safe send phases. Transaction ownership alone requires no schema migration.
- The pilot ends with an implementation note recording deviations, complexity, failures, and recommendations for Linden.

## Acceptance Criteria

1. Managed HTTP success commits before response completion; commit failure returns an error.
2. An exception escaping HTTP or Celery rolls back every uncommitted mutation in its session.
3. Injected failures during batch or recipient creation leave no partial broadcast and do not consume the idempotency key.
4. Failure between email, payload, outbox, and recipient-link writes leaves none partially durable.
5. Prepare and send tasks are published only after an independent session can see required rows.
6. Dispatch failure leaves pending work recoverable by existing sweeps.
7. Single and bulk Postmark calls run without an open database transaction or checked-out connection.
8. Database access after Postmark starts a fresh transaction automatically.
9. Reconciliation failure never obscures or rolls back an earlier completed phase.
10. Concurrent or redelivered send workers cannot send the same unexpired claim.
11. One failed webhook event persists none of its writes and does not block valid sibling events.
12. NATS publication never occurs for rolled-back database work.
13. Representative repository writes are visible after flush locally and invisible independently before commit.
14. Production repositories, nested commands, routers, and ordinary services do not finalize transactions; only the database boundary and documented top-level early-commit workflows may commit.
15. Production entry points do not construct unmanaged sessions.
16. Existing API shapes and domain behavior remain compatible except for corrected atomicity.
17. Pilot findings explicitly recommend which decisions Linden should retain or change.

## Testing Decisions

- Framework contract tests cover automatic commit, exception rollback, automatic transaction start from reads, nested operations, `on_commit` ordering, root-rollback clearing, failed-savepoint hook removal, hook failure isolation, early commit, fresh transactions, connection release, and closure.
- A FastAPI contract test proves a function-scoped dependency commit failure produces a 5xx before a response is sent.
- Session event tests prove hooks run after the outermost commit and not after savepoint release.
- Equivalent success and failure scenarios run through HTTP and Celery adapter contract tests. SDK onboarding/authentication receives lifecycle coverage if it performs writes.
- PostgreSQL integration tests observe durability through independent sessions; the ordinary outer-transaction fixture is insufficient evidence. That fixture uses `join_transaction_mode="create_savepoint"` so a rollback by code under test does not destroy fixture setup.
- Repository contracts cover create, update, soft-delete, hard-delete, conditional update, and bulk operations, distinguishing flush visibility from durability.
- Broadcast tests inject failures throughout acceptance and preparation, including reuse of an idempotency key after rollback.
- Publisher tests prove after-commit ordering and sweep recovery after dispatch failure.
- Provider-phase tests use pool checkout/checkin events or session transaction state to prove Postmark calls have no open transaction or checked-out connection.
- Single-email tests cover success, provider-declared failure, ambiguous timeout, provider success followed by reconciliation failure, and discovery of stranded queued rows.
- Broadcast tests cover exclusive claims, lease recovery, transport retry, reconciliation rollback, suppression, missing payload, and documented duplicate risk.
- Webhook tests cover per-event rollback, a middle-event database error, counters, suppression, and NATS ordering.
- Architecture tests scan the whole production application and identify exact violations.
- A guard test proves a mutation command cannot be wired without an active session and silently dispatch its `on_commit` work immediately.
- Tests that relied on repository durability move to a managed adapter or explicitly commit test setup; hidden repository commits are never restored.
- The complete suite and focused concurrency tests run against PostgreSQL. Mocks do not replace database coverage for locks, transactions, or savepoints.

## Out of Scope

- Distributed ACID across PostgreSQL, Celery, Postmark, or NATS.
- Exactly-once delivery or eliminating Postmark's ambiguous-response duplicate risk.
- Automatic replay of ambiguously queued single emails without provider-safe reconciliation.
- Replacing PRD 0003's claim and lease design.
- Replacing SQLAlchemy, PostgreSQL, Celery, Postmark, or the shared SDK.
- A broad domain or repository redesign unrelated to transaction ownership.
- Public API schema changes solely for this migration.
- Reliable NATS delivery; unsubscribe events remain best-effort.
- Making completed phases or partial success appear atomic.
- Implementing the Linden migration; this work validates and informs it.

## Further Notes

- This PRD depends on PRD 0003. Unit-of-Work atomicity makes claims and reconciliation consistent but does not supply exclusivity.
- After the Sendly pilot stabilizes the interface, the generic session scope, function-scoped FastAPI dependency factory, active-session context, `on_commit()` behavior, savepoint hook handling, framework contract tests, and optional architecture-test helpers are candidates for extraction into tessera_sdk. Extraction is a follow-up, not a dependency of this PRD. Application-specific early-commit allowlists, provider workflows, repository boundaries, recovery policy, and compensation remain in each API.
- The selected repository pattern is a concrete, non-committing SQLAlchemy persistence adapter scoped to the caller's `Session`. Abstract repository ports, returned Units of Work, and `commit=false` switches are deliberately excluded.
- Automatic commit is infrastructure behavior, not a convention each developer must remember. Advanced behavior uses native `Session.commit()` under a CI allowlist, plus thin `on_commit()` and `savepoint()` helpers.
- This follows established SQLAlchemy session-per-execution practice and Django's `ATOMIC_REQUESTS`/`on_commit()` model instead of inventing a second transaction vocabulary.
- Sendly is a useful pilot because it contains HTTP and Celery entry points, transactional-outbox-style dispatch, provider calls, webhook batches, and a best-effort event bus in a compact codebase.
- Removing hidden commits may expose tests and flows that relied on cross-session visibility. Those failures are migration evidence and must be resolved at an explicit phase or managed execution boundary.
