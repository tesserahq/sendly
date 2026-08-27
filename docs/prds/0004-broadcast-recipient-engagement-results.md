# Broadcast Recipient Engagement Results

## Problem Statement

Sendly accepts a broadcast as a list of structured recipients, persists those raw recipients, and
later creates one email per non-suppressed recipient. It also records provider webhook events for
opens and clicks. These pieces are not connected through a stable, caller-visible recipient
identity:

- A caller cannot attach its own recipient-record identifier to one broadcast recipient.
- The durable broadcast-recipient row is not linked to the email created for it.
- Sendly stores a first-open timestamp but does not store a first-click timestamp.
- Batch status reports an open count but not a click count.
- The batch interface does not expose a paginated recipient-results view combining the submitted
  recipient, its resulting email, and its engagement timestamps.

Downstream systems therefore have to correlate results by email address. Concretely, today's only
connection between a submitted recipient and its outcome is `Email.batch_id` plus `Email.to_email`
(`prepare_broadcast_chunk_task.py`) — the prepare stage never writes anything back onto the
`broadcast_recipients` row it consumed, so there is no join key other than the address itself. This
is unsafe for reasons that are already reachable with the existing code, not hypothetical
edge cases:

- **An address changes in the downstream system.** If a consumer's own contact record is later
  re-keyed to a new email, historical Sendly results indexed by the old address become orphaned
  with no other identifier to re-anchor them.
- **The same address appears more than once in one broadcast.** Nothing in `SendBroadcastCommand`
  rejects duplicate addresses — it builds its suppression lookup as a plain set over
  `[str(r.email) for r in req.recipients]`, so two distinct submitted recipients sharing an address
  are accepted as two rows. Matching results back by address alone cannot tell them apart or assign
  the right engagement outcome to the right originating recipient.
- **A recipient never produces an email.** A suppressed recipient, or one whose preparation fails,
  gets no `Email` row at all (`prepare_broadcast_chunk_task.py` skips both cases before creating
  one). A consumer polling by address has no record to distinguish "suppressed," "preparation
  failed," and "not yet prepared" — all three look identical: nothing found.

Consumers such as Looply cannot reliably cache per-recipient engagement or build segments such as
“recipients who did not open Campaign A.”

## Solution

Give every submitted broadcast recipient an optional caller-supplied reference, preserve a durable
one-to-one relationship between that recipient and the email produced for it, and expose engagement
through a batch-scoped recipient-results endpoint.

Sendly will record first-open and first-click timestamps independently from the email's current
delivery status. A click webhook will update an exact batch-level count only when an email records
its first click, so webhook retries and repeated link clicks do not inflate the number. The existing
open path will use the same first-occurrence mechanism so both engagement counters have consistent
idempotency semantics.

The recipient-results endpoint will be paginated and will return the caller reference, immutable
submitted email address, preparation/suppression outcome, resulting email identity and status, and
first-open/first-click timestamps. Suppressed recipients and preparation failures remain visible
even though they have no email. Authorization will be evaluated against the broadcast batch's
actual project, never a project identifier supplied by the caller.

Existing broadcast clients remain compatible because the caller reference is optional and the
immediate send response is unchanged.

## User Stories

1. As a Sendly consumer, I want to attach my own stable reference to each broadcast recipient, so
   that I can correlate later results without matching mutable email addresses.
2. As a Sendly consumer, I want the recipient reference to be returned with engagement results, so
   that I can update the exact record that originated the send.
3. As a Sendly consumer, I want caller references to be unique within a broadcast when supplied,
   so that one result cannot ambiguously identify multiple submitted recipients.
4. As a Sendly consumer, I want broadcasts without caller references to continue working, so that
   existing integrations remain backward compatible.
5. As a Sendly consumer retrying a broadcast, I want recipient references included in idempotency
   comparison, so that changing correlation identities under the same idempotency key is rejected.
6. As a Sendly consumer, I want each prepared broadcast recipient linked to exactly one resulting
   email, so that delivery and engagement data have an unambiguous origin.
7. As a Sendly consumer, I want suppressed recipients included in recipient results, so that I can
   reconcile the submitted audience even when no email was created.
8. As a Sendly consumer, I want recipients that fail during preparation included in recipient
   results, so that a missing email is distinguishable from an omitted recipient.
9. As a Sendly consumer, I want to know the first time an email was opened, so that I can cache
   recipient engagement.
10. As a Sendly consumer, I want to know the first time a link in an email was clicked, so that I
    can distinguish stronger engagement from opens.
11. As a Sendly consumer, I want repeated open or click webhooks to leave the first timestamp
    unchanged, so that provider retries do not rewrite engagement history.
12. As a Sendly consumer, I want multiple link clicks by one recipient to count as one clicked
    recipient, so that batch metrics measure recipients rather than click events.
13. As a Sendly consumer, I want engagement timestamps recorded even when an out-of-order webhook
    does not change the email's current status, so that status ordering does not discard evidence
    of engagement.
14. As a Sendly consumer, I want batch status to include an exact clicked-recipient count, so that
    I can show campaign results without scanning every recipient.
15. As a Sendly consumer, I want the existing opened-recipient count to use the same exact
    first-occurrence semantics as clicks, so that the two metrics behave consistently under retry.
16. As a Sendly consumer, I want recipient results paginated with a stable order and a total count,
    so that I can synchronize broadcasts larger than one page without skipping or duplicating
    recipients.
17. As a Sendly consumer, I want one recipient-results request to return submitted identity,
    preparation outcome, email status, and engagement timestamps, so that I do not need an N+1
    series of email/event requests.
18. As a Sendly consumer, I want recipient results scoped to a single batch, so that results from
    unrelated broadcasts cannot be mixed together.
19. As a project owner, I want recipient results authorized against the batch's stored project, so
    that changing or omitting a query parameter cannot expose another project's recipient data.
20. As an operator, I want recipient-result queries to avoid joining the full event history, so
    that pagination cost remains predictable as events accumulate.
21. As a developer maintaining Sendly, I want first-engagement recording concentrated behind one
    interface, so that webhook handlers do not independently implement timestamp and counter
    idempotency.
22. As a developer maintaining Sendly, I want the recipient-results query concentrated behind one
    interface, so that routing, authorization, joins, result shaping, and stable pagination do not
    leak into multiple callers.
23. As a developer implementing broadcast reliability work, I want this feature's
    recipient-to-email relationship to be the same unique relationship required by the reliability
    design, so that the schema does not acquire competing correlation mechanisms.

## Implementation Decisions

- Extend the broadcast recipient request contract with an optional client_reference_id. It is a
  UUID owned by the caller, validated and rejected as a request error if it is not a well-formed
  UUID, and has no template-rendering semantics. Restricting the type (rather than accepting any
  opaque string) removes ambiguity about collation/case-sensitivity in the per-batch uniqueness
  check and keeps the column a fixed-width, indexable type instead of a caller-controlled-length
  string.
- Persist client_reference_id directly on the durable broadcast-recipient row. Do not place it in
  recipient attributes or shared metadata: attributes are template variables, while shared
  metadata cannot vary per recipient.
- Require non-null caller references to be unique within one broadcast batch. Reusing the same
  reference in different batches is allowed. Reject duplicate references as request validation
  errors before accepting the batch.
- Include client_reference_id in the canonical recipient representation used by the existing
  request fingerprint. Retrying the same idempotency key with changed references therefore remains
  a conflict.
- Add a nullable, unique relationship from a broadcast recipient to its resulting email. The
  relationship is populated by the prepare stage in the same transaction that creates the email,
  delivery payload, outbox entry, and successful preparation state. A suppressed recipient or a
  recipient whose preparation fails has no related email.
- Treat this relationship as the implementation of the one-email-per-recipient invariant already
  required by the broadcast pipeline reliability design. Later reliability work must reuse it
  instead of adding a second relationship.
- Add a nullable first-click timestamp to the email model and response schemas. Its semantics match
  the existing first-open timestamp: it records the earliest known occurrence for that email, not a
  log of every engagement event.
- Preserve the full email-event rows. First-open and first-click timestamps are denormalized query
  fields; they do not replace the event log.
- Deepen the email lifecycle module so one interface records a webhook event and reports
  first-occurrence outcomes separately from status changes. The implementation atomically records
  the first open or click, remains correct under duplicate or concurrent webhook delivery, and does
  not rely on the current status being advanced.
- Update batch engagement counters only from successful first-occurrence outcomes. Add an exact,
  non-null clicked_count with a default of zero. Refactor opened_count to use the same
  first-occurrence outcome rather than assuming every status is reachable only once.
- A clicked recipient means an email with at least one accepted click webhook. Multiple links and
  repeated clicks from the same email do not increment the batch count again.
- Keep open and click semantics independent. A click does not synthesize an open event or opened_at;
  each field reflects the corresponding provider event.
- Extend both individual batch status and batch-list summaries with clicked_count. Existing fields
  and the immediate broadcast-send response remain unchanged.
- Introduce a deep recipient-results query module with one interface: resolve one authorized
  batch's recipient results as a stable paginated query. The module owns the left join from
  broadcast recipients to emails, ordering, and result projection; callers do not assemble these
  joins themselves.
- Add a nested, read-only GET /broadcasts/{batch_id}/recipients endpoint. It returns a standard page
  containing:
  - Sendly's broadcast-recipient identifier
  - client_reference_id
  - the immutable submitted email address
  - suppression and preparation outcome
  - the resulting email identifier, when one exists
  - the email's current delivery status, when one exists
  - opened_at
  - clicked_at
- The endpoint uses a stable order with a unique tie-breaker and returns normal pagination metadata,
  including the total recipient count. Consumers must be able to traverse every page without
  depending on a provider-specific maximum page size.
- Recipient rows remain present in results when the email side of the relationship is absent.
  Engagement fields and email status are null in that case; suppression/preparation fields explain
  the known outcome without fabricating an email status.
- Resolve the batch by its server-generated batch identifier, then authorize against the batch's
  stored project before returning recipient data. A caller-supplied project identifier is never
  trusted for resource ownership.
- The query reads denormalized engagement timestamps rather than joining email events, keeping one
  page proportional to the requested recipient page rather than to accumulated webhook history.
- Add indexes and constraints supporting batch-scoped stable pagination, per-batch caller-reference
  uniqueness, and the unique recipient-to-email relationship.
- Backfill first-click timestamps from the earliest stored click event per existing email and
  backfill batch click counts from distinct emails with a click timestamp. Recompute existing open
  counts from first-open timestamps so the counters start from consistent semantics.
- Do not infer recipient-to-email relationships for historical broadcasts by matching email
  addresses. Duplicate addresses are valid, so such a backfill would create false correlations.
  Historical recipient rows without the relationship remain visible with null email/engagement
  fields; the complete correlation contract is guaranteed for broadcasts accepted after rollout.
- Update Sendly's broadcast documentation to describe caller references, recipient-to-email
  correlation, click metrics, pagination, historical limitations, and first-occurrence semantics.

## Testing Decisions

- Good tests exercise observable database and HTTP behavior: given a broadcast, preparation
  outcomes, and webhook events, assert the recipient results and aggregate counts. Tests should not
  assert private helper sequencing.
- Extend broadcast command tests to cover optional caller references, duplicate-reference
  rejection, persistence, and idempotency conflicts when references change.
- Extend prepare-task integration tests to prove that a successfully prepared recipient is linked
  to exactly one email and that suppressed or failed recipients have no email relationship.
- Extend lifecycle tests to cover first-click persistence, repeated clicks, multiple clicked links,
  click-before-open and open-before-click ordering, engagement after a terminal status, and
  preservation of the earliest known timestamp.
- Add database-backed concurrency coverage showing that simultaneous duplicate click deliveries
  produce one first-click transition and increment the batch count once.
- Extend delivery-event command tests to verify exact opened_count and clicked_count updates from
  first-occurrence outcomes rather than ordinary status changes.
- Extend broadcast status and list-router tests to cover clicked_count, including migrated or
  pre-existing batches with zero engagement.
- Add recipient-results repository/query tests covering a normal prepared recipient, a suppressed
  recipient, a preparation failure, a null caller reference, duplicate email addresses with
  distinct caller references, and historical rows without an email relationship.
- Add recipient-results router tests covering response fields, stable multi-page traversal beyond
  the default page size, an empty batch, missing batches, and authorization against the batch's
  actual project.
- Use the existing broadcast router tests as prior art for full accept-to-prepare behavior and
  batch authorization. Use the existing email lifecycle and delivery-event tests as prior art for
  webhook transition behavior.
- Migration tests or explicit migration verification must cover the timestamp/count backfill and
  confirm that ambiguous historical recipient-to-email links are left null.

## Out of Scope

- Changes to Looply's campaign, recipient, polling, or segment models.
- Changes to the Python SDK. The SDK must subsequently expose client_reference_id, clicked_count,
  and typed paginated recipient results, but that work is delivered in its own repository.
- A push event from Sendly to Looply for every open or click. Consumers continue to read results
  through Sendly's HTTP interface.
- Storing every click URL or exposing total click-event counts. This PRD tracks whether and when
  each email first clicked.
- Replacing or removing the existing email-event log.
- A live, unpaginated export of an entire broadcast audience.
- Caller-controlled Sendly recipient identifiers. Sendly continues to generate its own primary
  keys; client_reference_id is correlation data only.
- Retrofitting reliable recipient-to-email links onto historical broadcasts by email matching.
- The claim/lease, atomic chunk, retry-state, and recovery changes defined by the broadcast
  pipeline reliability PRD, except for implementing the shared unique recipient-to-email
  relationship.
- Changes to webhook authentication or provider parsing beyond using the already-normalized open
  and click events.
- Synthesizing an open when a click arrives.

## Further Notes

- There are two concepts named broadcast recipient: the request schema accepted from callers and
  the durable database row consumed by preparation. Both gain the same caller-reference value, but
  only the durable row participates in the email relationship and results query.
- The recipient-results interface deliberately starts from the durable recipient row rather than
  the email list. This preserves suppressed and failed recipients and avoids treating email
  addresses as identifiers.
- The unique recipient-to-email relationship is also a prerequisite for making prepare retries
  safe. Implementations should coordinate this PRD with the broadcast pipeline reliability work so
  migrations and invariants land once.
- The downstream SDK must retain pagination metadata and must not hide page traversal behind a
  single default-size response. Consumers such as Looply are responsible for traversing all pages
  during synchronization.
- Because the endpoint returns recipient email addresses and engagement data, its authorization
  follows the existing batch lookup pattern that derives the domain from stored data. This is a
  required security property, not an optional router convention.
