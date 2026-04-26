# 0001 — Email Templates & Layouts

## Problem Statement

Consumers of Sendly currently own all email HTML. Every service that sends emails must store, maintain, and pass the full rendered HTML in each send request. This creates duplication across consumers: the same header, footer, and structural chrome is copy-pasted into every template. When a brand change is needed (new logo, updated footer, color scheme), every consumer must update their HTML independently.

There is no central place to manage what emails look like. Sendly is an email abstraction layer, but it doesn't yet abstract the content — only the delivery.

## Solution

Introduce first-class `Template` and `Layout` resources in Sendly that consumers can manage via a CRUD API. A `Template` stores the subject line and body HTML for one type of email (e.g. "welcome", "password-reset"). A `Layout` stores the structural chrome (header, footer, full HTML skeleton) with a `${content}` placeholder where template body HTML is injected.

When sending, a caller can reference a template by UUID or slug alias plus a variables map. Sendly fetches the template, optionally wraps it in its layout, renders the combined HTML and subject through Mako, and sends the result — exactly as it does today with inline HTML, but without the caller needing to own any HTML.

Inline HTML sending continues to work unchanged. The two modes are mutually exclusive per request.

## User Stories

1. As a Sendly consumer, I want to create a named email template with a subject and HTML body, so that I don't have to store email HTML in my own service.
2. As a Sendly consumer, I want to update a template's HTML and subject, so that I can iterate on email content without deploying my own service.
3. As a Sendly consumer, I want to delete a template I no longer use, so that the template list stays clean.
4. As a Sendly consumer, I want to retrieve a template by ID or alias, so that I can inspect or preview its current content.
5. As a Sendly consumer, I want to list all templates, so that I can see what templates are available to use.
6. As a Sendly consumer, I want to send an email by providing a template alias and a variables map, so that I don't have to pass HTML in the send request.
7. As a Sendly consumer, I want to send an email by providing a template UUID and a variables map, as an alternative to using the alias.
8. As a Sendly consumer, I want the template's subject line to support Mako variable interpolation (e.g. `Welcome, ${name}!`), so that subject lines can be personalised per send.
9. As a Sendly consumer, I want to store a default `from_email` on a template, so that I don't have to pass it on every send request.
10. As a Sendly consumer, I want to store a default `reply_to` on a template, so that reply routing is centralised with the template.
11. As a Sendly consumer, I want to override a template's `from_email` at send time, so that multi-brand services can use the same template with different senders.
12. As a Sendly consumer, I want to override a template's `reply_to` at send time, so that I can route replies differently per send.
13. As a Sendly consumer, I want to create a layout with a structural HTML shell and a `${content}` placeholder, so that I can define a consistent header/footer once.
14. As a Sendly consumer, I want to update a layout's HTML, so that a brand change propagates to all templates that use it without touching each template.
15. As a Sendly consumer, I want to delete a layout, so that unused layouts don't accumulate.
16. As a Sendly consumer, I want to list all layouts, so that I can see what structural shells are available.
17. As a Sendly consumer, I want to retrieve a layout by ID or alias, so that I can inspect its current HTML.
18. As a Sendly consumer, I want to assign a layout to a template, so that the template's HTML is automatically wrapped in the layout when sent.
19. As a Sendly consumer, I want to create a template without a layout, so that simple transactional emails don't need full structural chrome.
20. As a Sendly consumer, I want to reassign a template to a different layout, so that I can restructure email chrome without recreating templates.
21. As a Sendly consumer, I want to remove a layout association from a template (set it to none), so that the template renders standalone.
22. As a Sendly consumer, I want a 400 error if I send both a template reference and inline HTML in the same request, so that the intent of the request is always unambiguous.
23. As a Sendly consumer, I want a 422 error if I use a template that has no `from_email` and I also don't provide one in the send request, so that the error is clear and actionable.
24. As a Sendly consumer, I want a 404 error if the template alias or UUID I reference does not exist, so that misconfigured callers fail loudly.
25. As a Sendly consumer, I want template aliases to be URL-safe slugs, so that they are easy to embed in config files and environment variables.
26. As a Sendly consumer, I want alias uniqueness enforced at the API level, so that two templates cannot accidentally share the same alias.
27. As a Sendly consumer, I want layout aliases to also be unique slugs, so that layouts can be referenced unambiguously.
28. As a Sendly consumer, I want the rendered HTML (after layout wrapping and variable substitution) stored in `Email.body` as today, so that the email record is a self-contained audit trail regardless of future template changes.
29. As a Sendly operator, I want template and layout records to support soft-delete, so that deletions are recoverable and consistent with how emails are managed.

## Implementation Decisions

### New models

**`Layout`**
- Fields: `id` (UUID PK), `alias` (unique slug, indexed), `html` (text, required — must contain `${content}`), `name` (optional human-friendly label), `created_at`, `updated_at`, `deleted_at`
- Inherits `TimestampMixin` and `SoftDeleteMixin` (consistent with `Email`)
- No `project_id` — layouts are global

**`Template`**
- Fields: `id` (UUID PK), `alias` (unique slug, indexed), `subject` (text, required, Mako-renderable), `html` (text, required, Mako-renderable), `from_email` (nullable), `reply_to` (nullable), `layout_id` (nullable FK → `layouts.id`), `created_at`, `updated_at`, `deleted_at`
- Inherits `TimestampMixin` and `SoftDeleteMixin`
- No `project_id` — templates are global
- SQLAlchemy relationship to `Layout` (lazy or joined load as needed)

### Alias slugging
- Aliases are generated/validated using `python-slugify` (already in deps)
- Alias is caller-supplied; Sendly normalises it through slugify on write
- Uniqueness enforced via a DB unique constraint (not just application-level)
- Alias mutability: aliases **can** be renamed. There is no immutability constraint; the caller owns the alias lifecycle. Renaming is a deliberate update action.

### Rendering pipeline (updated `SendEmailCommand`)

When a template reference is present:
1. Fetch `Template` by `template_id` (UUID) or `template_alias` (slug); 404 if not found
2. If `template.layout_id` is set, fetch the `Layout`; inject template HTML into layout HTML by rendering layout with `{"content": template.html}` as a Mako template — this produces the combined HTML string
3. Render the combined HTML (or standalone template HTML) through Mako with the caller's `template_variables`
4. Render `template.subject` through Mako with `template_variables`
5. Resolve `from_email`: caller-provided value takes precedence over template default; if neither is set, raise a validation error before hitting the provider
6. Proceed with the existing `EmailCreate` → provider send → lifecycle recording flow unchanged

When inline HTML is present (existing flow): unchanged.

Mutual exclusion validation: if both `html` and (`template_id` or `template_alias`) are set, raise HTTP 400 before any DB access.

### `EmailCreateRequest` changes
- `template_id` field already exists (UUID, nullable) — wire it up
- Add `template_alias` field (string, nullable)
- `html`, `subject`, and `from_email` become fully optional (nullable) at the schema level; required-ness is now contextual and enforced in `SendEmailCommand`

### New repositories
- `TemplateRepository(SoftDeleteRepository[Template])` — CRUD + lookup by alias
- `LayoutRepository(SoftDeleteRepository[Layout])` — CRUD + lookup by alias
- Both follow the same pattern as `EmailRepository`

### New commands (one class per operation, `execute()` method)
- `CreateTemplateCommand`, `UpdateTemplateCommand`, `DeleteTemplateCommand`, `GetTemplateCommand`, `ListTemplatesCommand`
- `CreateLayoutCommand`, `UpdateLayoutCommand`, `DeleteLayoutCommand`, `GetLayoutCommand`, `ListLayoutsCommand`

### New routers
- `POST/GET/PATCH/DELETE /templates` and `/templates/{id_or_alias}`
- `POST/GET/PATCH/DELETE /layouts` and `/layouts/{id_or_alias}`
- Both follow the RBAC pattern via `build_rbac_dependencies` with resource names `"template"` and `"layout"`

### Pagination
- List endpoints use `fastapi-pagination` (same as `GET /emails`)

### Schema layer
- `TemplateCreate`, `TemplateUpdate` (all-optional fields), `TemplateInDB`, `Template` response schema
- `LayoutCreate`, `LayoutUpdate`, `LayoutInDB`, `Layout` response schema

## Testing Decisions

**What makes a good test here:** test external behaviour (what the API or command returns given inputs), not internal implementation (don't assert on which private methods were called). Tests should use the real `sendly_test` database via the `db` fixture and rolled-back transactions — no mocking of the DB layer.

**`TemplateRepository` and `LayoutRepository`** — integration tests against the real DB. Verify create, read-by-id, read-by-alias, update, soft-delete, and uniqueness constraint enforcement. Prior art: `tests/app/repositories/test_email_repository.py`.

**`SendEmailCommand` (template path)** — integration tests using the `db` fixture. Seed a `Template` (with and without a `Layout`), call `execute()`, assert the returned `Email` has the correct rendered `body`, `subject`, `from_email`, and `status`. Test the mutual-exclusion 400, the missing-`from_email` 422, and the template-not-found 404. Prior art: existing command tests.

**Template and Layout routers** — HTTP-level tests using the `client` fixture. Cover the full CRUD surface, alias uniqueness conflicts (409), and the send-with-template flow end-to-end. Prior art: `tests/app/routers/test_email.py`.

**`EmailLifecycleService`** — no changes needed; existing unit tests remain valid.

**Fixtures** — add `setup_layout` and `setup_template` fixtures to `tests/fixtures/` following the pattern of `email_fixtures.py`.

## Out of Scope

- **Template versioning** — no history of which template version was used for a given send. The rendered HTML is stored in `Email.body` as the audit record.
- **Per-project template scoping** — templates and layouts are global in this iteration.
- **Provider-native templates** — no passthrough to Postmark's template system; Sendly always renders locally.
- **Template preview endpoint** — rendering a template with sample variables without sending.
- **Multiple recipients** — the existing single-recipient limitation in `Email.to_email` is unchanged.
- **Text/plain body** — the existing `req.text` field is not templated; templates only manage HTML body.
- **Template validation at save time** — Mako syntax is not validated when a template is created or updated; errors surface at send time.

## Further Notes

- The `${content}` placeholder in layouts is a reserved Mako variable name within Sendly's rendering pipeline. Layouts that omit it will cause template body HTML to be silently dropped; a warning log is appropriate but enforcement is out of scope for this iteration.
- `python-slugify` normalises aliases on write, so callers can submit `"Welcome Email"` and receive back `"welcome-email"`. The stored value is always the normalised slug.
- Since `from_email` is now contextually optional on `EmailCreateRequest`, existing callers who always pass it are unaffected. The breaking case (omitting `from_email` without a template default) produces a clear 422 with a descriptive message.
- The biggest operational risk is template mutation: if a template's HTML is changed after being used, there is no record of the version used for historical sends. Operators should treat `Email.body` as the canonical rendered record for any audit or re-send scenario.
