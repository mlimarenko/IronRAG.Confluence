<h1 align="center">IronRAG ↔ Confluence connector</h1>
<p align="center"><b>Sync Confluence spaces into <a href="https://github.com/mlimarenko/IronRAG">IronRAG</a> with configurable routing, auth, and incremental polling.</b></p>

---

This connector is built on the IronRAG Connector Template and focuses on
Confluence-specific behavior:

- Confluence REST API pagination and retries.
- Auth modes: `anonymous`, `basic`, `bearer`, or `auto`.
- Flexible source selection via CQL + include/exclude space keys.
- Routing facts that let you map different spaces/sections to different
  IronRAG workspaces/libraries.
- Optional attachment sync as dependent items.

## Quick start

```bash
cd confluence
cp .env.example .env.local
cp routing.yaml.example routing.yaml

uv sync --all-extras
uv run pytest
uv run confluence-connector
```

## Required env vars

```env
CONFLUENCE_BASE_URL=https://confluence.example.com
CONFLUENCE_AUTH_MODE=auto

IRONRAG_BASE_URL=http://localhost:19000
IRONRAG_API_TOKEN=...
ADMIN_BEARER_TOKEN=...
```

Auth examples:

- Anonymous public Confluence:
  - `CONFLUENCE_AUTH_MODE=anonymous`
- Basic auth:
  - `CONFLUENCE_AUTH_MODE=basic`
  - `CONFLUENCE_USERNAME=...`
  - `CONFLUENCE_PASSWORD=...` (or `CONFLUENCE_TOKEN=...`)
- Bearer/PAT:
  - `CONFLUENCE_AUTH_MODE=bearer`
  - `CONFLUENCE_TOKEN=...`

Space selection modes:

- All spaces (default): leave `CONFLUENCE_SPACE_KEYS` empty, or set it to
  `all`, `any`, or `*`.
- Explicit include-list: `CONFLUENCE_SPACE_KEYS=ENG,DOCS,OPS`.
- Exclude-list (works with both modes): `CONFLUENCE_EXCLUDE_SPACE_KEYS=ARCHIVE,OLD`.
- Additional narrowing: `CONFLUENCE_CQL=label = "public"`.

## Routing strategy

The adapter emits routing facts such as:

- `space` / `space_key`
- `space_name`
- `ancestor_title` (list)
- `ancestor_id` (list)

That allows rules like:

- send `space_key=ENG` to engineering library;
- send pages under ancestor section `Runbooks` to ops library.

See `routing.yaml.example`.
