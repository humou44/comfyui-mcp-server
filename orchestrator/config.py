"""Configuration helpers for the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
from typing import Dict, List, Optional


@dataclass(frozen=True)
class OrchestratorConfig:
    ollama_url: str
    ollama_model: str
    ollama_timeout_s: int
    mcp_transport: str
    mcp_url: Optional[str]
    mcp_command: Optional[str]
    mcp_args: List[str]
    mcp_cwd: Optional[str]
    mcp_env: Dict[str, str]
    max_tool_calls: int = 4
    max_invalid_calls: int = 2
    max_messages: int = 12


def _parse_mcp_cmd(raw: str) -> tuple[str, List[str]]:
    parts = shlex.split(raw)
    if not parts:
        raise ValueError("MCP_CMD is empty")
    return parts[0], parts[1:]


def _normalize_transport(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned == "http":
        return "streamable-http"
    return cleaned


def load_config(
    ollama_url: Optional[str] = None,
    ollama_model: Optional[str] = None,
    ollama_timeout_s: Optional[int] = None,
    mcp_transport: Optional[str] = None,
    mcp_url: Optional[str] = None,
    mcp_cmd: Optional[str] = None,
    mcp_cwd: Optional[str] = None,
) -> OrchestratorConfig:
    env_ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    env_ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    env_ollama_timeout = int(os.getenv("OLLAMA_TIMEOUT_S", "120"))
    env_mcp_transport = _normalize_transport(os.getenv("MCP_TRANSPORT", "streamable-http"))
    env_mcp_url = os.getenv("MCP_URL", "http://127.0.0.1:9000/mcp")
    env_mcp_cmd = os.getenv("MCP_CMD", "python server.py --stdio")
    env_mcp_cwd = os.getenv("MCP_CWD")

    transport = _normalize_transport(mcp_transport or env_mcp_transport)
    command = None
    args: List[str] = []
    if transport == "stdio":
        command, args = _parse_mcp_cmd(mcp_cmd or env_mcp_cmd)

    # Pass through COMFYUI_URL if set, since server.py reads it.
    mcp_env: Dict[str, str] = {}
    comfyui_url = os.getenv("COMFYUI_URL")
    if comfyui_url:
        mcp_env["COMFYUI_URL"] = comfyui_url

    return OrchestratorConfig(
        ollama_url=ollama_url or env_ollama_url,
        ollama_model=ollama_model or env_ollama_model,
        ollama_timeout_s=ollama_timeout_s or env_ollama_timeout,
        mcp_transport=transport,
        mcp_url=mcp_url or env_mcp_url,
        mcp_command=command,
        mcp_args=args,
        mcp_cwd=mcp_cwd or env_mcp_cwd,
        mcp_env=mcp_env,
    )

