from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.config import Settings

log = logging.getLogger("prreviewiq.mcp")

NOTION_API = "https://api.notion.com/v1"
NOTION_VER = "2022-06-28"


class MCPClientError(RuntimeError):
    pass


# ─── HTTP fallback (used when MCP stdio is unavailable) ─────────────────────


class NotionHTTPFallback:
    """Direct Notion REST client — used when MCP stdio is unavailable."""

    def __init__(self, settings: Settings) -> None:
        self._token = settings.notion_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VER,
            "Content-Type": "application/json",
        }

    async def call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as c:
            if tool == "API-post-page":
                r = await c.post(f"{NOTION_API}/pages", headers=self._headers(), json=args)
            elif tool == "API-post-search":
                r = await c.post(f"{NOTION_API}/search", headers=self._headers(), json=args)
            elif tool == "API-post-database":
                r = await c.post(f"{NOTION_API}/databases", headers=self._headers(), json=args)
            elif tool == "API-post-database-query":
                db_id = args.pop("database_id")
                r = await c.post(
                    f"{NOTION_API}/databases/{db_id}/query",
                    headers=self._headers(),
                    json=args,
                )
            elif tool == "API-get-block-children":
                bid = args.pop("block_id")
                r = await c.get(
                    f"{NOTION_API}/blocks/{bid}/children",
                    headers=self._headers(),
                    params=args,
                )
            elif tool == "API-get-self":
                r = await c.get(f"{NOTION_API}/users/me", headers=self._headers())
            elif tool == "API-patch-page":
                pid = args.pop("page_id")
                r = await c.patch(
                    f"{NOTION_API}/pages/{pid}",
                    headers=self._headers(),
                    json=args,
                )
            elif tool == "API-retrieve-a-page":
                pid = args.pop("page_id")
                r = await c.get(f"{NOTION_API}/pages/{pid}", headers=self._headers())
            else:
                return {"error": f"Unknown tool: {tool}"}
            return r.json()


# ─── MCP context managers ────────────────────────────────────────────────────


@asynccontextmanager
async def notion_mcp(settings: Settings):
    """Spin up Notion MCP stdio server and yield a ClientSession."""
    params = StdioServerParameters(
        command=settings.notion_mcp_command,
        args=["-y", settings.notion_mcp_package],
        env={**os.environ, "NOTION_TOKEN": settings.notion_token},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def notion_session(settings: Settings):
    return notion_mcp(settings)


# ─── MCP call helper ─────────────────────────────────────────────────────────


async def mcp_call(session: Any, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call an MCP tool and return parsed JSON result."""
    if isinstance(session, NotionHTTPFallback):
        return await session.call_tool(tool, args)
    try:
        result = await session.call_tool(tool, args)
        text = result.content[0].text if result.content else "{}"
        return json.loads(text)
    except Exception as exc:
        raise MCPClientError(f"MCP tool {tool} failed: {exc}") from exc


# ─── Notion block builders ──────────────────────────────────────────────────


def _rt(content: str) -> list[dict[str, Any]]:
    """Rich-text array helper."""
    return [{"text": {"content": content[:2000]}}]


def _heading(text: str, level: int = 2) -> dict[str, Any]:
    key = f"heading_{level}"
    return {"object": "block", "type": key, key: {"rich_text": _rt(text)}}


def _para(text: str) -> dict[str, Any]:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rt(text)}}


def _bullet(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rt(text)},
    }


# ─── High-level MCP helpers ─────────────────────────────────────────────────


async def mcp_create_page(
    session: Any,
    parent_id: str,
    title: str,
    children: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a Notion page via MCP."""
    return await mcp_call(
        session,
        "API-post-page",
        {
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": _rt(title)}},
            "children": children[:100],
        },
    )


async def mcp_create_db_page(
    session: Any,
    database_id: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Create a page entry in a Notion database via MCP."""
    return await mcp_call(
        session,
        "API-post-page",
        {
            "parent": {"database_id": database_id},
            "properties": properties,
        },
    )


async def mcp_create_database(
    session: Any,
    parent_id: str,
    title: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Create a Notion database via MCP."""
    return await mcp_call(
        session,
        "API-post-database",
        {
            "parent": {"page_id": parent_id},
            "title": _rt(title),
            "properties": properties,
        },
    )


async def mcp_search(session: Any, query: str = "") -> list[dict[str, Any]]:
    """Search Notion via MCP."""
    result = await mcp_call(session, "API-post-search", {"query": query, "page_size": 50})
    return result.get("results", [])


async def mcp_get_children(session: Any, block_id: str) -> list[dict[str, Any]]:
    """Get block children via MCP."""
    result = await mcp_call(
        session,
        "API-get-block-children",
        {"block_id": block_id, "page_size": 100},
    )
    return result.get("results", [])


async def mcp_query_database(
    session: Any,
    database_id: str,
    filter_obj: dict[str, Any] | None = None,
    sorts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Query a Notion database via MCP."""
    payload: dict[str, Any] = {"database_id": database_id}
    if filter_obj:
        payload["filter"] = filter_obj
    if sorts:
        payload["sorts"] = sorts
    result = await mcp_call(session, "API-post-database-query", payload)
    return result.get("results", [])


async def mcp_patch_page(
    session: Any,
    page_id: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """Update a Notion page's properties via MCP."""
    return await mcp_call(
        session,
        "API-patch-page",
        {"page_id": page_id, "properties": properties},
    )


# ─── Notion URL / property utilities ────────────────────────────────────────


def extract_id_from_url(url: str) -> str:
    """Extract a Notion page/database ID from a URL and return as UUID with dashes."""
    clean = url.split("?")[0].split("#")[0]
    # The last path segment contains the ID (last 32 hex chars, possibly with dashes)
    last_segment = clean.rstrip("/").rsplit("/", 1)[-1]
    hex_only = re.sub(r"[^0-9a-f]", "", last_segment.lower())
    if len(hex_only) >= 32:
        raw = hex_only[-32:]
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    raise ValueError(f"Could not extract Notion ID from URL: {url}")


def extract_title(prop: dict[str, Any]) -> str:
    """Extract plain text from a Notion title property."""
    return "".join(item.get("plain_text", "") for item in prop.get("title", []))


def extract_rich_text(prop: dict[str, Any]) -> str:
    """Extract plain text from a Notion rich_text property."""
    return "".join(item.get("plain_text", "") for item in prop.get("rich_text", []))


def extract_select(prop: dict[str, Any]) -> str:
    """Extract name from a Notion select property."""
    select = prop.get("select")
    return select.get("name", "") if select else ""


def extract_checkbox(prop: dict[str, Any]) -> bool:
    """Extract value from a Notion checkbox property."""
    return prop.get("checkbox", False)


def extract_number(prop: dict[str, Any]) -> int:
    """Extract value from a Notion number property."""
    val = prop.get("number")
    return int(val) if isinstance(val, (int, float)) and val is not None else 0


def extract_date(prop: dict[str, Any]) -> str | None:
    """Extract start date from a Notion date property."""
    d = prop.get("date")
    return d.get("start") if d else None


def find_by_title(results: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    """Find a page or database in search results by exact title match."""
    for item in results:
        if item.get("object") == "database":
            title_parts = item.get("title", [])
            title = "".join(t.get("plain_text", "") for t in title_parts)
            if title == target:
                return item
        elif item.get("object") == "page":
            for prop in item.get("properties", {}).values():
                if prop.get("type") == "title":
                    title = "".join(t.get("plain_text", "") for t in prop.get("title", []))
                    if title == target:
                        return item
    return None
