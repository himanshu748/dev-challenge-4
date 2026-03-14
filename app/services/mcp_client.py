from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from typing import Any

from app.core.config import Settings


class MCPClientError(RuntimeError):
    pass


class NotionMCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.process: asyncio.subprocess.Process | None = None
        self._initialized = False
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._stderr_lines: deque[str] = deque(maxlen=60)
        self._stderr_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        if self.process is None:
            return

        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

        if self._stderr_task is not None:
            self._stderr_task.cancel()

        self.process = None
        self._initialized = False

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_initialized()

        async with self._lock:
            self._request_id += 1
            request_id = self._request_id
            await self._send_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )

            while True:
                message = await asyncio.wait_for(
                    self._read_message(),
                    timeout=self.settings.notion_mcp_startup_timeout_seconds,
                )
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise MCPClientError(self._format_error(message["error"]))
                return message.get("result", {})

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        if self.process is None or self.process.returncode is not None:
            await self._start_process()

        initialize_payload = {
            "protocolVersion": self.settings.notion_mcp_protocol_version,
            "capabilities": {},
            "clientInfo": {
                "name": "PRReviewIQ",
                "version": "0.1.0",
            },
        }

        async with self._lock:
            self._request_id += 1
            request_id = self._request_id
            await self._send_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "initialize",
                    "params": initialize_payload,
                }
            )

            while True:
                message = await asyncio.wait_for(
                    self._read_message(),
                    timeout=self.settings.notion_mcp_startup_timeout_seconds,
                )
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise MCPClientError(self._format_error(message["error"]))
                break

            await self._send_message(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                }
            )

        self._initialized = True

    async def _start_process(self) -> None:
        env = os.environ.copy()
        env["NOTION_TOKEN"] = self.settings.notion_token

        self.process = await asyncio.create_subprocess_exec(
            self.settings.notion_mcp_command,
            "-y",
            self.settings.notion_mcp_package,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        if self.process.stderr is not None:
            self._stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        if self.process is None or self.process.stderr is None:
            return

        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    return
                self._stderr_lines.append(line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            return

    async def _send_message(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise MCPClientError("Notion MCP process is not available.")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self.process.stdin.write(header + body)
        await self.process.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        if self.process is None or self.process.stdout is None:
            raise MCPClientError("Notion MCP process is not available.")

        headers: dict[str, str] = {}
        while True:
            line = await self.process.stdout.readline()
            if not line:
                stderr = "\n".join(self._stderr_lines)
                raise MCPClientError(
                    "Notion MCP process terminated before sending a response."
                    + (f"\nRecent stderr:\n{stderr}" if stderr else "")
                )

            decoded = line.decode("utf-8", errors="replace")
            if decoded in ("\r\n", "\n"):
                break

            if ":" not in decoded:
                continue
            name, value = decoded.split(":", 1)
            headers[name.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            raise MCPClientError("Notion MCP response was missing Content-Length.")
        raw_body = await self.process.stdout.readexactly(content_length)
        return json.loads(raw_body.decode("utf-8"))

    @staticmethod
    def _format_error(error: dict[str, Any]) -> str:
        message = error.get("message", "Unknown MCP error")
        code = error.get("code")
        if code is None:
            return message
        return f"{message} (code {code})"
