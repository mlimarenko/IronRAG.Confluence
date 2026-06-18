# Confluence ↔ IronRAG connector — Changelog

## 0.1.7 — 2026-06-18

- Build against framework `v0.0.9`: one source ref's fetch/push work,
  including dependents, is bounded by `SYNC_ITEM_TIMEOUT_SECONDS`. A stuck item
  is cancelled and counted as an item error so the sweep can continue to
  `sync.done` instead of holding the single-flight sync lock indefinitely.
- Inherits `sync.item.start` and `sync.item_timeout` logs for identifying the
  source ref that is currently in flight or timed out.

## 0.1.6 — 2026-06-18

- Build against framework `v0.0.8`: full sweeps are now single-flight inside
  the connector process, so manual, startup, and periodic triggers cannot run
  overlapping mutation passes against the same cursor database. Concurrent
  manual `/sync/run` requests return HTTP 409 while an existing sweep is active.
- Inherits framework cancellation cleanup for manual sync requests that are
  disconnected before the sweep finishes.

## 0.1.5 — 2026-06-18

- Build against framework `v0.0.7`: large legacy cursor databases now cap
  best-effort document-detail backfill before source enumeration, and the
  same-route path backfills cursor ownership via the target library's
  external-key lookup before trying slower document-detail calls.

## 0.1.4 — 2026-06-18

- Build against framework `v0.0.6`: legacy cursor library backfill is now
  bounded and non-fatal, so a slow document-detail lookup no longer makes
  manual `/sync/run` return 500 before Confluence enumeration starts.
  Unresolved legacy cursor ownership still blocks possible duplicate uploads;
  destructive cleanup for unknown historical libraries is deferred to a later
  sweep.

## 0.1.3 — 2026-06-18

- Build against framework `v0.0.5`: cursor rows now retain the target
  library, orphan scans follow cursor pagination, route moves avoid deleting
  newly-routed documents, legacy cursor rows are backfilled from IronRAG
  document details, and transient conflicting mutations are retried on a later
  sweep without advancing the cursor.
- Tightened connector type annotations so strict mypy passes against the typed
  framework package.

## 0.1.2 — 2026-06-10

- Page attachments and inline images now ingest as attached context of
  their source page instead of as peer documents. Each dependent is
  auto-linked to its page via the framework's `parent_external_key`; no
  config change is required. Inherited from the connector SDK — IronRAG
  derives the child's role from the declared parent and media class.

## 0.1.1 — 2026-05-29

- Pages whose own body is empty but which host attachments are no longer
  dropped. The page is emitted with a synthesized index body listing its
  attachments, and each attachment is ingested as its own document.
  Previously an empty page body caused the whole item — including its
  attachments — to be skipped.
- Build against framework `v0.0.3`: content-addressed idempotency keys
  (fixes `409 idempotency_conflict` on re-rendered page updates),
  single-request external-key lookup via the list `search` filter, and
  cursor document-id persistence on the unchanged path (steady-state
  sweeps no longer re-scan the IronRAG list endpoint).

## 0.1.0 — 2026-05-22

- Initial public release.
