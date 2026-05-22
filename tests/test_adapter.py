from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest

from confluence_connector.adapter import ConfluenceAdapter
from confluence_connector.config import ConfluenceSettings
from confluence_connector.mapping import KIND_ATTACHMENT, KIND_PAGE


def _settings() -> ConfluenceSettings:
    return ConfluenceSettings(
        confluence_base_url="https://wiki.example.com",
        confluence_auth_mode="anonymous",
        ironrag_base_url="http://ironrag.example.com",
        ironrag_api_token="token",
        admin_bearer_token="admin",
    )


class FakeConfluence:
    async def list_pages(self) -> AsyncIterator[dict[str, Any]]:
        yield {
            "id": "42",
            "title": "Runbook",
            "status": "current",
            "space": {"key": "OPS", "name": "Operations"},
            "version": {"when": "2026-05-22T00:00:00.000Z"},
            "ancestors": [{"id": "10", "title": "Runbooks"}],
        }

    async def get_page(self, page_id: str) -> dict[str, Any]:
        return {
            "id": page_id,
            "title": "Runbook",
            "status": "current",
            "space": {"key": "OPS", "name": "Operations"},
            "version": {"when": "2026-05-22T00:00:00.000Z"},
            "ancestors": [{"id": "10", "title": "Runbooks"}],
            "body": {"export_view": {"value": "<p>Hello from Confluence.</p>"}},
            "_links": {"webui": "/display/OPS/Runbook"},
        }

    async def list_attachments(self, page_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "77",
                "title": "ops-guide.pdf",
                "version": {"when": "2026-05-22T01:00:00.000Z"},
                "_links": {"download": "/download/attachments/42/ops-guide.pdf"},
            }
        ]

    async def download(self, path_or_url: str) -> tuple[bytes, str]:
        return b"%PDF-fake", "application/pdf"

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_iter_items_and_fetch() -> None:
    fake = FakeConfluence()
    with patch("confluence_connector.adapter.ConfluenceClient", return_value=fake):
        adapter = ConfluenceAdapter(_settings())
        refs = [ref async for ref in adapter.iter_items()]
        assert len(refs) == 1
        ref = refs[0]
        assert ref.kind == KIND_PAGE
        assert ref.external_key == "confluence:page:42"
        assert ref.routing_facts["space_key"] == "OPS"
        assert ref.routing_facts["ancestor_title"] == ["Runbooks"]

        item = await adapter.fetch(ref)
        assert item is not None
        assert item.mime_type == "text/html"
        assert item.document_hint == "https://wiki.example.com/display/OPS/Runbook"
        assert len(item.dependents) == 1
        dependent = item.dependents[0]
        assert dependent.ref.kind == KIND_ATTACHMENT
        assert dependent.ref.external_key == "confluence:attachment:77"
        assert dependent.mime_type == "application/pdf"
