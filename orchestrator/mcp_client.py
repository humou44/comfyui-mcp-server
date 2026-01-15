"""MCP client wrappers (stdio and streamable-http)."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sys
from typing import Any, Dict, Optional

import requests

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent


@dataclass(frozen=True)
class McpServerConfig:
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: Optional[str] = None


@dataclass(frozen=True)
class McpHttpConfig:
    url: str
    timeout_s: int = 300


class McpStdioClient:
    def __init__(self, config: McpServerConfig):
        self._config = config
        self._session: Optional[ClientSession] = None
        self._streams = None

    async def __aenter__(self) -> "McpStdioClient":
        params = StdioServerParameters(
            command=self._config.command,
            args=self._config.args,
            env=self._config.env,
            cwd=self._config.cwd,
        )
        self._streams = stdio_client(params, errlog=sys.stderr)
        read_stream, write_stream = await self._streams.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.aclose()
        if self._streams:
            await self._streams.__aexit__(exc_type, exc, tb)
        self._session = None
        self._streams = None

    async def list_tools(self) -> list[str]:
        if not self._session:
            raise RuntimeError("MCP session not initialized")
        result = await self._session.list_tools()
        return [tool.name for tool in result.tools]

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._session:
            raise RuntimeError("MCP session not initialized")
        result = await self._session.call_tool(name=name, arguments=arguments or {})
        return _extract_tool_payload(result)


class McpHttpClient:
    def __init__(self, config: McpHttpConfig):
        self._config = config

    async def __aenter__(self) -> "McpHttpClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def list_tools(self) -> list[str]:
        result = await self._request("tools/list", {})
        tools = result.get("tools", [])
        return [tool.get("name") for tool in tools if isinstance(tool, dict)]

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        result = await self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
        )
        return _extract_http_tool_payload(result)

    async def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return await anyio.to_thread.run_sync(self._request_sync, method, params)

    def _request_sync(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        response = requests.post(
            self._config.url,
            json=request,
            headers=headers,
            timeout=self._config.timeout_s,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            payload = _parse_sse_response(response.text)
        else:
            payload = response.json()
        if "error" in payload:
            return {"error": "JSON-RPC error", "detail": payload["error"]}
        result = payload.get("result")
        if isinstance(result, dict):
            return result
        return {"result": result}


def _extract_tool_payload(result: CallToolResult) -> Dict[str, Any]:
    if result.isError:
        return {"error": "Tool returned error", "detail": _content_to_text(result)}

    if result.structuredContent is not None:
        return dict(result.structuredContent)

    text = _content_to_text(result)
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    return {}


def _content_to_text(result: CallToolResult) -> str:
    parts = []
    for block in result.content:
        if isinstance(block, TextContent):
            parts.append(block.text)
        elif hasattr(block, "text"):
            parts.append(str(block.text))
    return "\n".join(parts).strip()


def _parse_sse_response(response_text: str) -> dict:
    lines = response_text.replace("\r\n", "\n").split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("data: "):
            json_str = line[6:]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    raise ValueError("No valid JSON data found in SSE response")


def _extract_http_tool_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    if "content" in result and isinstance(result["content"], list):
        for content_item in result["content"]:
            if isinstance(content_item, dict) and "text" in content_item:
                text_content = content_item["text"]
                try:
                    parsed = json.loads(text_content)
                    content_item["text"] = parsed
                except (json.JSONDecodeError, TypeError):
                    content_item["text"] = str(text_content).strip()
        first_content = result["content"][0] if result["content"] else None
        if isinstance(first_content, dict) and "text" in first_content:
            if isinstance(first_content["text"], dict):
                return first_content["text"]
            try:
                parsed_text = json.loads(first_content["text"])
                return parsed_text
            except (json.JSONDecodeError, TypeError):
                return {"text": first_content["text"]}
    return result

