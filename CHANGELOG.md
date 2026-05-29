# Confluence ↔ IronRAG connector — Changelog

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
