from __future__ import annotations

import httpx
import pytest

from confluence_connector.config import ConfluenceSettings
from confluence_connector.confluence import ConfluenceClient


def _settings(**overrides: object) -> ConfluenceSettings:
    data = {
        "confluence_base_url": "https://wiki.example.com",
        "confluence_auth_mode": "anonymous",
        "ironrag_base_url": "http://ironrag.example.com",
        "ironrag_api_token": "token",
        "admin_bearer_token": "admin",
    }
    data.update(overrides)
    return ConfluenceSettings(**data)


@pytest.mark.asyncio
async def test_list_pages_uses_composed_cql() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["cql"] = request.url.params.get("cql", "")
        return httpx.Response(
            200,
            json={"results": [{"id": "1"}, {"id": "2"}]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        base_url="https://wiki.example.com",
        transport=transport,
    )
    settings = _settings(
        confluence_space_keys="ENG,DOCS",
        confluence_exclude_space_keys="ARCHIVE",
        confluence_cql='label = "ops"',
    )
    api = ConfluenceClient(settings, client=client)
    items = [item async for item in api.list_pages()]
    assert [item["id"] for item in items] == ["1", "2"]
    assert "space in (\"ENG\", \"DOCS\")" in captured["cql"]
    assert "space not in (\"ARCHIVE\")" in captured["cql"]
    assert '(label = "ops")' in captured["cql"]
    await api.aclose()
    await client.aclose()


@pytest.mark.asyncio
async def test_auto_auth_uses_bearer_when_token_only() -> None:
    captured_auth: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        base_url="https://wiki.example.com",
        transport=transport,
    )
    settings = _settings(confluence_auth_mode="auto", confluence_token="abc123")
    api = ConfluenceClient(settings, client=client)
    _ = [item async for item in api.list_pages()]
    assert captured_auth["authorization"] == "Bearer abc123"
    await api.aclose()
    await client.aclose()


@pytest.mark.asyncio
async def test_space_all_marker_disables_include_filter() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["cql"] = request.url.params.get("cql", "")
        return httpx.Response(200, json={"results": []})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(
        base_url="https://wiki.example.com",
        transport=transport,
    )
    settings = _settings(
        confluence_space_keys="all",
        confluence_exclude_space_keys="ARCHIVE",
    )
    api = ConfluenceClient(settings, client=client)
    _ = [item async for item in api.list_pages()]
    assert "space in (" not in captured["cql"]
    assert "space not in (\"ARCHIVE\")" in captured["cql"]
    await api.aclose()
    await client.aclose()
