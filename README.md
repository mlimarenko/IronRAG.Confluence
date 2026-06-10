<h1 align="center">IronRAG ↔ Confluence connector</h1>
<p align="center"><b>Sync Confluence spaces into <a href="https://github.com/mlimarenko/IronRAG">IronRAG</a> with configurable routing, auth, and incremental polling.</b></p>

<p align="center">
  <a href="https://github.com/mlimarenko/IronRAG.Confluence/releases"><img src="https://img.shields.io/github/v/release/mlimarenko/IronRAG.Confluence?style=flat-square&label=release" alt="Release"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License"></a>
  <a href="https://hub.docker.com/r/pipingspace/ironrag.confluence"><img src="https://img.shields.io/docker/pulls/pipingspace/ironrag.confluence?style=flat-square&label=docker%20pulls" alt="Docker pulls"></a>
  <img src="https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square" alt="Python">
</p>

---

This connector is built on the IronRAG Connector Template and focuses on
Confluence-specific behavior:

- Confluence REST API pagination and retries.
- Auth modes: `anonymous`, `basic`, `bearer`, or `auto`.
- Flexible source selection via CQL + include/exclude space keys.
- Routing facts that let you map different spaces/sections to different
  IronRAG workspaces/libraries.
- Optional attachment sync as dependent items. Page attachments and
  inline images now ingest as attached context of their source page
  rather than as peer documents — they are auto-linked to their page by
  the SDK (`parent_external_key`), with no config change required.

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

## Deploy with Docker Compose

```bash
cp .env.example .env.local             # CONFLUENCE_* + IRONRAG_* + ADMIN_BEARER_TOKEN
cp routing.yaml.example routing.yaml   # map spaces/sections → (workspace, library)
docker compose up -d
docker compose logs -f
```

[`docker-compose.yml`](docker-compose.yml) pulls the released image, mounts your
`routing.yaml` read-only, and persists the SQLite cursor in a named volume so a
restart ships only the diff. Port 8088 is published on localhost only — put a
TLS reverse proxy in front and use it only when running `RUN_MODE=webhook`/`both`.

## Related

- [IronRAG](https://github.com/mlimarenko/IronRAG) — the RAG backend these connectors feed.
- [Connector Template](https://github.com/mlimarenko/IronRAG.ConnectorTemplate) — the framework every connector builds on.
- Connectors: [Confluence](https://github.com/mlimarenko/IronRAG.Confluence) · [BookStack](https://github.com/mlimarenko/IronRAG.BookStack) · [Git Repositories](https://github.com/mlimarenko/IronRAG.GitRepos)

## License

MIT — see [LICENSE](./LICENSE).
