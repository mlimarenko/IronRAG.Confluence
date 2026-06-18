from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from ironrag_connector import SourceAdapter, SourceItem, SourceItemRef
from ironrag_connector.observability import get_logger

from .config import ConfluenceSettings
from .confluence import ConfluenceClient, ConfluenceError, ConfluenceNotFoundError
from .mapping import (
    CONNECTOR_NAME,
    KIND_ATTACHMENT,
    KIND_PAGE,
    KINDS,
    attachment_external_key,
    build_external_key,
    page_external_key,
    parse_external_key,
)

log = get_logger(__name__)

_FILENAME_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class ConfluenceAdapter(SourceAdapter):
    name = CONNECTOR_NAME
    kinds = KINDS
    primary_kinds = (KIND_PAGE,)

    def __init__(self, settings: ConfluenceSettings) -> None:
        self._settings = settings
        self._client = ConfluenceClient(settings)
        self._base_url = settings.confluence_base_url.rstrip("/")

    async def close(self) -> None:
        await self._client.aclose()

    def external_key(self, kind: str, item_id: str) -> str:
        return build_external_key(kind, item_id)

    def parse_external_key(self, external_key: str) -> tuple[str, str] | None:
        return parse_external_key(external_key)

    async def iter_items(self) -> AsyncIterator[SourceItemRef]:
        async for page in self._client.list_pages():
            page_id = page.get("id")
            if not isinstance(page_id, str) or not page_id:
                continue
            facts = self._routing_facts_for_page(page)
            yield SourceItemRef(
                item_id=page_id,
                kind=KIND_PAGE,
                external_key=page_external_key(page_id),
                change_token=_extract_change_token(page),
                routing_facts=facts,
                raw=page,
            )

    async def fetch(self, ref: SourceItemRef) -> SourceItem | None:
        if ref.kind != KIND_PAGE:
            return None
        try:
            page = await self._client.get_page(ref.item_id)
        except ConfluenceNotFoundError:
            return None

        title = page.get("title") if isinstance(page.get("title"), str) else None
        html = _extract_best_html(page)
        facts = self._routing_facts_for_page(page)
        page_ref = SourceItemRef(
            item_id=ref.item_id,
            kind=KIND_PAGE,
            external_key=page_external_key(ref.item_id),
            change_token=_extract_change_token(page),
            routing_facts=facts,
            raw=page,
        )

        # Build attachment dependents before deciding whether the page is
        # ingestable. A page can carry no readable body of its own yet still
        # host attachments (specs, PDFs, images) that are the real content —
        # dropping the page on an empty body would silently lose every one of
        # those attachment documents.
        dependents = tuple(await self._build_attachment_dependents(page_ref, page))

        if not html:
            if not dependents:
                log.warning("confluence.fetch.empty_body", page_id=ref.item_id)
                return None
            log.info(
                "confluence.fetch.empty_body_with_attachments",
                page_id=ref.item_id,
                attachment_count=len(dependents),
            )
            html = _synthesize_attachment_index_html(dependents)

        wrapped_html = _wrap_html_document(title or f"Page {ref.item_id}", html)
        item = SourceItem(
            ref=page_ref,
            payload=wrapped_html.encode("utf-8"),
            mime_type="text/html",
            file_name=f"{_safe_filename(title or f'page-{ref.item_id}')}.html",
            title=title,
            document_hint=self._document_hint(page),
            dependents=dependents,
        )
        return item

    async def _build_attachment_dependents(
        self,
        page_ref: SourceItemRef,
        page: dict[str, Any],
    ) -> list[SourceItem]:
        if not self._settings.confluence_include_attachments:
            return []

        page_id = page_ref.item_id
        page_title = page.get("title") if isinstance(page.get("title"), str) else "Page"
        try:
            attachments = await self._client.list_attachments(page_id)
        except ConfluenceError as exc:
            log.warning("confluence.attachments.list_failed", page_id=page_id, error=str(exc))
            return []

        dependents: list[SourceItem] = []
        for attachment in attachments:
            attachment_id = attachment.get("id")
            if not isinstance(attachment_id, str) or not attachment_id:
                continue
            links = attachment.get("_links")
            if not isinstance(links, dict):
                continue
            download_url = links.get("download")
            if not isinstance(download_url, str) or not download_url:
                continue

            try:
                payload, mime_type = await self._client.download(download_url)
            except ConfluenceNotFoundError:
                continue
            except ConfluenceError as exc:
                log.warning(
                    "confluence.attachments.download_failed",
                    page_id=page_id,
                    attachment_id=attachment_id,
                    error=str(exc),
                )
                continue

            if not payload:
                continue
            if len(payload) > self._settings.confluence_attachment_max_bytes:
                log.info(
                    "confluence.attachments.skipped_too_large",
                    attachment_id=attachment_id,
                    bytes=len(payload),
                    max_bytes=self._settings.confluence_attachment_max_bytes,
                )
                continue

            att_title = attachment.get("title")
            att_name = att_title if isinstance(att_title, str) else f"attachment-{attachment_id}"
            att_ref = SourceItemRef(
                item_id=attachment_id,
                kind=KIND_ATTACHMENT,
                external_key=attachment_external_key(attachment_id),
                change_token=_extract_change_token(attachment),
                routing_facts=page_ref.routing_facts,
                raw=attachment,
            )
            dependents.append(
                SourceItem(
                    ref=att_ref,
                    payload=payload,
                    mime_type=mime_type or "application/octet-stream",
                    file_name=_safe_filename(att_name),
                    title=f"{page_title}: {att_name}",
                    document_hint=self._attachment_hint(download_url),
                )
            )
        return dependents

    def _routing_facts_for_page(self, page: dict[str, Any]) -> dict[str, Any]:
        space = page.get("space")
        space_key = None
        space_name = None
        if isinstance(space, dict):
            if isinstance(space.get("key"), str):
                space_key = space["key"]
            if isinstance(space.get("name"), str):
                space_name = space["name"]

        ancestors = page.get("ancestors", [])
        ancestor_titles: list[str] = []
        ancestor_ids: list[str] = []
        if isinstance(ancestors, list):
            for ancestor in ancestors:
                if not isinstance(ancestor, dict):
                    continue
                aid = ancestor.get("id")
                if isinstance(aid, str):
                    ancestor_ids.append(aid)
                atitle = ancestor.get("title")
                if isinstance(atitle, str):
                    ancestor_titles.append(atitle)

        return {
            "space": space_key,
            "space_key": space_key,
            "space_name": space_name,
            "ancestor_id": ancestor_ids,
            "ancestor_title": ancestor_titles,
            "status": page.get("status") if isinstance(page.get("status"), str) else None,
        }

    def _document_hint(self, page: dict[str, Any]) -> str | None:
        links = page.get("_links")
        if not isinstance(links, dict):
            return None
        webui = links.get("webui")
        if isinstance(webui, str) and webui:
            if webui.startswith("http://") or webui.startswith("https://"):
                return webui
            return f"{self._base_url}{webui}"
        return None

    def _attachment_hint(self, download_url: str) -> str:
        if download_url.startswith("http://") or download_url.startswith("https://"):
            return download_url
        return f"{self._base_url}{download_url}"


def _extract_best_html(page: dict[str, Any]) -> str | None:
    body = page.get("body")
    if not isinstance(body, dict):
        return None
    export_view = body.get("export_view")
    if isinstance(export_view, dict):
        value = export_view.get("value")
        if isinstance(value, str) and value.strip():
            return value
    storage = body.get("storage")
    if isinstance(storage, dict):
        value = storage.get("value")
        if isinstance(value, str) and value.strip():
            return value
    return None


def _synthesize_attachment_index_html(dependents: tuple[SourceItem, ...]) -> str:
    """Build a minimal body for a page that has no readable text of its own
    but carries attachments. The body lists each attachment so the page
    document is a useful index that links to its attachment documents,
    instead of being dropped entirely."""
    rows: list[str] = []
    for dep in dependents:
        label = dep.title or dep.file_name
        href = dep.document_hint
        if href:
            rows.append(f'<li><a href="{_escape_html(href)}">{_escape_html(label)}</a></li>')
        else:
            rows.append(f"<li>{_escape_html(label)}</li>")
    return "<ul>" + "".join(rows) + "</ul>"


def _extract_change_token(item: dict[str, Any]) -> str | None:
    version = item.get("version")
    if isinstance(version, dict):
        when = version.get("when")
        if isinstance(when, str) and when:
            return when
        number = version.get("number")
        if isinstance(number, int):
            return str(number)
    return None


def _safe_filename(raw: str) -> str:
    collapsed = _FILENAME_SANITIZE_RE.sub("-", raw.strip())
    collapsed = collapsed.strip("-.")
    return collapsed or "file"


def _wrap_html_document(title: str, html: str) -> str:
    return (
        "<!doctype html>"
        "<html>"
        "<head>"
        '<meta charset="utf-8"/>'
        f"<title>{_escape_html(title)}</title>"
        "</head>"
        "<body>"
        f"{html}"
        "</body>"
        "</html>"
    )


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
