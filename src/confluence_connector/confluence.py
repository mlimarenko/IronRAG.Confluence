from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from ironrag_connector.observability import get_logger

from .config import ConfluenceSettings

log = get_logger(__name__)

RETRYABLE_STATUS = {429, 502, 503, 504}


class ConfluenceError(RuntimeError):
    pass


class ConfluenceNotFoundError(ConfluenceError):
    pass


class ConfluenceClient:
    def __init__(
        self, settings: ConfluenceSettings, client: httpx.AsyncClient | None = None
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        headers = {"Accept": "application/json"}
        auth, auth_headers = _build_auth(settings)
        headers.update(auth_headers)
        if client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.confluence_base_url.rstrip("/"),
                timeout=settings.request_timeout_seconds,
                headers=headers,
                auth=auth,
                follow_redirects=True,
            )
        else:
            client.headers.update(headers)
            if auth is not None:
                client.auth = auth
            self._client = client
        self._rate_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            async with self._rate_lock:
                min_interval = self._settings.confluence_min_request_interval_seconds
                if min_interval > 0:
                    elapsed = time.monotonic() - self._last_request_at
                    wait = min_interval - elapsed
                    if wait > 0:
                        await asyncio.sleep(wait)
                self._last_request_at = time.monotonic()
                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                )

            if (
                response.status_code in RETRYABLE_STATUS
                and attempt < self._settings.confluence_retry_max
            ):
                delay = _retry_delay(
                    response.headers,
                    attempt,
                    self._settings.confluence_retry_backoff_seconds,
                    self._settings.confluence_retry_max_sleep_seconds,
                )
                log.warning(
                    "confluence.retry",
                    status=response.status_code,
                    attempt=attempt,
                    delay_seconds=delay,
                    path=path,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            return response

    async def list_pages(self) -> AsyncIterator[dict[str, Any]]:
        start = 0
        while True:
            response = await self._request(
                "GET",
                "/rest/api/content/search",
                params={
                    "cql": self._build_cql(),
                    "start": start,
                    "limit": self._settings.confluence_page_size,
                    "expand": "version,space,history,ancestors",
                },
            )
            if response.status_code >= 400:
                raise ConfluenceError(
                    "Confluence search failed: "
                    f"{response.status_code} {response.text[:400]}"
                )
            payload = response.json()
            results = payload.get("results", [])
            if not isinstance(results, list):
                return
            for page in results:
                if isinstance(page, dict):
                    yield page
            if len(results) < self._settings.confluence_page_size:
                return
            start += self._settings.confluence_page_size

    async def get_page(self, page_id: str) -> dict[str, Any]:
        response = await self._request(
            "GET",
            f"/rest/api/content/{page_id}",
            params={
                "expand": (
                    "body.export_view,body.storage,version,space,metadata.labels,ancestors"
                )
            },
        )
        if response.status_code == 404:
            raise ConfluenceNotFoundError(f"page {page_id} not found")
        if response.status_code >= 400:
            raise ConfluenceError(
                f"Confluence page fetch failed: {response.status_code} {response.text[:400]}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ConfluenceError(f"unexpected payload for page {page_id}")
        return payload

    async def list_attachments(self, page_id: str) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        start = 0
        while True:
            response = await self._request(
                "GET",
                f"/rest/api/content/{page_id}/child/attachment",
                params={
                    "start": start,
                    "limit": self._settings.confluence_page_size,
                    "expand": "version,metadata,space",
                },
            )
            if response.status_code == 404:
                return []
            if response.status_code >= 400:
                raise ConfluenceError(
                    "Confluence attachment list failed: "
                    f"{response.status_code} {response.text[:400]}"
                )
            payload = response.json()
            results = payload.get("results", [])
            if not isinstance(results, list):
                return attachments
            attachments.extend([a for a in results if isinstance(a, dict)])
            if len(results) < self._settings.confluence_page_size:
                return attachments
            start += self._settings.confluence_page_size

    async def download(self, path_or_url: str) -> tuple[bytes, str]:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            response = await self._client.get(path_or_url)
        else:
            response = await self._request("GET", path_or_url)
        if response.status_code == 404:
            raise ConfluenceNotFoundError(f"download target not found: {path_or_url}")
        if response.status_code >= 400:
            raise ConfluenceError(
                f"Confluence download failed: {response.status_code} {response.text[:400]}"
            )
        mime = response.headers.get("content-type", "application/octet-stream")
        return response.content, mime.split(";")[0].strip()

    def _build_cql(self) -> str:
        clauses: list[str] = ["type=page"]

        included = self._settings.included_space_keys()
        if included is not None:
            clauses.append(f"space in ({_quote_csv(included)})")

        excluded = self._settings.excluded_space_keys()
        if excluded:
            clauses.append(f"space not in ({_quote_csv(excluded)})")

        custom = (self._settings.confluence_cql or "").strip()
        if custom:
            clauses.append(f"({custom})")

        return f"{' and '.join(clauses)} order by id asc"


def _build_auth(
    settings: ConfluenceSettings,
) -> tuple[httpx.Auth | None, dict[str, str]]:
    mode = settings.confluence_auth_mode
    headers: dict[str, str] = {}

    if mode == "auto":
        if settings.confluence_username and (
            settings.confluence_password or settings.confluence_token
        ):
            mode = "basic"
        elif settings.confluence_token:
            mode = "bearer"
        else:
            mode = "anonymous"

    if mode == "anonymous":
        return None, headers
    if mode == "bearer":
        if not settings.confluence_token:
            raise ValueError("CONFLUENCE_TOKEN is required for bearer auth mode")
        headers["Authorization"] = f"Bearer {settings.confluence_token}"
        return None, headers
    if mode == "basic":
        if not settings.confluence_username:
            raise ValueError("CONFLUENCE_USERNAME is required for basic auth mode")
        secret = settings.confluence_password or settings.confluence_token
        if not secret:
            raise ValueError(
                "CONFLUENCE_PASSWORD or CONFLUENCE_TOKEN is required for basic auth mode"
            )
        return httpx.BasicAuth(settings.confluence_username, secret), headers

    raise ValueError(f"unsupported auth mode: {mode}")


def _quote_csv(values: tuple[str, ...]) -> str:
    escaped = [value.replace('"', '\\"') for value in values]
    return ", ".join(f'"{value}"' for value in escaped)


def _retry_delay(
    headers: httpx.Headers,
    attempt: int,
    backoff_seconds: float,
    max_sleep_seconds: float,
) -> float:
    retry_after = headers.get("Retry-After")
    if retry_after:
        stripped = retry_after.strip()
        if stripped.isdigit():
            return min(float(stripped), max_sleep_seconds)
        try:
            target = parsedate_to_datetime(stripped)
            if target.tzinfo is None:
                target = target.replace(tzinfo=UTC)
            from time import time as wall_time

            delta = max(0.0, target.timestamp() - wall_time())
            return min(delta, max_sleep_seconds)
        except (TypeError, ValueError, OverflowError):
            pass
    return float(min(backoff_seconds * (2**attempt), max_sleep_seconds))
