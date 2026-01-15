"""Core orchestration loop."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Tuple

import anyio

from .conversation import ConversationState
from .llm_client import OllamaClient
from .tool_registry import ALLOWED_TOOLS, REGENERATE_OVERRIDE_KEYS, ValidationResult, validate_toolcall


SYSTEM_PROMPT = """You control a ComfyUI toolset via tool calls.
You must output either:
1) A strict JSON object: {"tool":"...","args":{...}}
2) A final natural-language response with no JSON.
Never invent tools. Allowed tools: get_defaults, set_defaults, generate_image, regenerate.
Use set_defaults for persistent changes. Use generate_image for one-offs.
Use regenerate for iterations when an asset_id exists.
If a request is ambiguous, ask one clarifying question.
get_defaults takes no arguments.
Keep responses short and deterministic."""


@dataclass(frozen=True)
class RuntimeConfig:
    max_tool_calls: int
    max_invalid_calls: int
    max_messages: int


class McpClient(Protocol):
    async def call_tool(self, name: str, arguments: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        ...


class Orchestrator:
    def __init__(
        self,
        config: RuntimeConfig,
        llm_client: OllamaClient,
        mcp_client: McpClient | None,
    ) -> None:
        self.config = config
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.state = ConversationState()

    async def ensure_defaults(self) -> None:
        if self.state.defaults_cache:
            return
        if not self.mcp_client:
            raise RuntimeError("MCP client not initialized")
        defaults = await self.mcp_client.call_tool("get_defaults", {})
        self.state.defaults_cache = defaults
        self._append_tool_result("get_defaults", defaults)

    async def handle_user_turn(self, user_text: str) -> str:
        await self.ensure_defaults()
        if not self.mcp_client:
            raise RuntimeError("MCP client not initialized")

        self.state.append("user", user_text)
        self.state.tool_calls_this_turn = 0
        self.state.invalid_tool_retries = 0
        self.state.last_turn_events = []
        self.state.last_prompt_messages = None
        empty_retries = 0
        require_toolcall = _requires_regen_toolcall(user_text, self.state.last_asset_id)
        require_defaults = _requires_defaults_toolcall(user_text)

        while self.state.tool_calls_this_turn < self.config.max_tool_calls:
            messages = self._build_messages()
            self.state.last_prompt_messages = messages
            start_time = time.perf_counter()
            model_text = await anyio.to_thread.run_sync(
                self.llm_client.chat, messages
            )
            llm_ms = (time.perf_counter() - start_time) * 1000.0
            self.state.last_model_output = model_text
            self.state.last_llm_ms = llm_ms
            self.state.last_turn_events.append(
                {"type": "llm_output", "content": model_text, "duration_ms": llm_ms}
            )

            if not model_text.strip():
                empty_retries += 1
                if (require_toolcall or require_defaults) and empty_retries >= 1:
                    synthesized = _synthesize_toolcall(
                        user_text,
                        self.state.last_asset_id,
                    )
                    if synthesized:
                        model_text = json.dumps(synthesized, ensure_ascii=True)
                    elif empty_retries > 1:
                        fallback = _fallback_final_text(self.state.last_asset_id)
                        self.state.append("assistant", fallback)
                        self.state.truncate(self.config.max_messages)
                        return fallback
                else:
                    if empty_retries > 1:
                        fallback = _fallback_final_text(self.state.last_asset_id)
                        self.state.append("assistant", fallback)
                        self.state.truncate(self.config.max_messages)
                        return fallback
                    self._append_tool_error(
                        ValidationResult(
                            False,
                            "Model returned an empty response. Respond with a tool call or a short final reply.",
                        )
                    )
                    continue

            toolcall = _parse_toolcall(model_text)
            if toolcall is None:
                if require_toolcall or require_defaults:
                    self.state.invalid_tool_retries += 1
                    self._append_tool_error(
                        ValidationResult(
                            False,
                            "Tool call required for this request. Use set_defaults or regenerate.",
                        )
                    )
                    if self.state.invalid_tool_retries > self.config.max_invalid_calls:
                        return "I need a tool call to proceed. What should I change?"
                    continue
                self.state.last_turn_events.append(
                    {"type": "final_text", "content": model_text}
                )
                self.state.append("assistant", model_text)
                self.state.truncate(self.config.max_messages)
                return model_text

            tool, args = toolcall
            if tool == "regenerate" and "asset_id" not in args:
                if self.state.last_asset_id:
                    args = dict(args)
                    args["asset_id"] = self.state.last_asset_id
            if tool == "regenerate":
                args = _normalize_regenerate_args(args)

            validation = validate_toolcall(tool, args)
            if not validation.ok:
                self.state.invalid_tool_retries += 1
                self._append_tool_error(validation)
                self.state.last_turn_events.append(
                    {"type": "validation_error", "tool": tool, "error": validation.error}
                )
                if self.state.invalid_tool_retries > self.config.max_invalid_calls:
                    return "I couldn't make a valid tool call. What should I change next?"
                continue

            start_time = time.perf_counter()
            raw_result = await self.mcp_client.call_tool(tool, args)
            tool_ms = (time.perf_counter() - start_time) * 1000.0
            canonical = canonicalize_tool_result(tool, raw_result)
            self.state.last_turn_events.append(
                {
                    "type": "tool_call",
                    "tool": tool,
                    "args": args,
                    "duration_ms": tool_ms,
                }
            )
            self.state.last_turn_events.append(
                {
                    "type": "tool_result",
                    "tool": tool,
                    "payload": canonical,
                }
            )

            if tool == "set_defaults" and canonical["ok"]:
                updated = _extract_updated_defaults(raw_result.get("updated", {}))
                if isinstance(updated, dict):
                    # Merge updated defaults into cache
                    for key, value in updated.items():
                        if isinstance(value, dict):
                            current = self.state.defaults_cache.get(key, {})
                            if isinstance(current, dict):
                                current.update(value)
                                self.state.defaults_cache[key] = current
                            else:
                                self.state.defaults_cache[key] = value
            if tool in {"generate_image", "regenerate"} and canonical["ok"]:
                asset_id = canonical.get("data", {}).get("asset_id")
                if isinstance(asset_id, str):
                    self.state.last_asset_id = asset_id

            self._append_tool_result(tool, canonical)
            self.state.tool_calls_this_turn += 1

        return "I hit the tool-call limit. Tell me what to adjust next."

    def _build_messages(self) -> List[Dict[str, str]]:
        defaults_summary = json.dumps(
            _clean_defaults_for_prompt(self.state.defaults_cache),
            ensure_ascii=True,
        )
        summary_msg = f"Current defaults: {defaults_summary}"
        last_asset_msg = ""
        if self.state.last_asset_id:
            last_asset_msg = f"Last asset_id: {self.state.last_asset_id}"
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.append({"role": "assistant", "content": summary_msg})
        if last_asset_msg:
            messages.append({"role": "assistant", "content": last_asset_msg})
        messages.extend(self.state.messages)
        return messages

    def _append_tool_result(self, tool: str, payload: Dict[str, object]) -> None:
        content = json.dumps({"tool_result": {"tool": tool, "payload": payload}}, ensure_ascii=True)
        self.state.append("assistant", content)
        self.state.truncate(self.config.max_messages)

    def _append_tool_error(self, validation: ValidationResult) -> None:
        content = json.dumps(
            {"tool_error": {"error": validation.error}}, ensure_ascii=True
        )
        self.state.append("assistant", content)
        self.state.truncate(self.config.max_messages)


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    return cleaned


def _parse_toolcall(text: str) -> Optional[Tuple[str, Dict[str, object]]]:
    cleaned = _strip_fences(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    tool = payload.get("tool")
    args = payload.get("args", {})
    if not isinstance(tool, str):
        return None
    if not isinstance(args, dict):
        return None
    return tool, args


def _requires_regen_toolcall(user_text: str, last_asset_id: Optional[str]) -> bool:
    if not last_asset_id:
        return False
    lowered = user_text.lower()
    triggers = [
        "regenerate",
        "regen",
        "again",
        "retry",
        "keep composition",
        "less noisy",
        "more cinematic",
        "increase contrast",
        "tweak",
        "adjust",
        "refine",
        "variation",
    ]
    return any(token in lowered for token in triggers)


def _requires_defaults_toolcall(user_text: str) -> bool:
    lowered = user_text.lower()
    triggers = [
        "set default",
        "set defaults",
        "by default",
        "from now on",
        "make default",
        "use default",
    ]
    return any(token in lowered for token in triggers)


def _normalize_regenerate_args(args: Dict[str, object]) -> Dict[str, object]:
    normalized = dict(args)
    overrides = normalized.get("param_overrides")
    if overrides is None or not isinstance(overrides, dict):
        overrides = {}
    for key in REGENERATE_OVERRIDE_KEYS:
        if key in normalized:
            overrides[key] = normalized.pop(key)
    if overrides:
        normalized["param_overrides"] = overrides
    return normalized


def _extract_updated_defaults(updated: object) -> Dict[str, object]:
    if not isinstance(updated, dict):
        return {}
    cleaned: Dict[str, object] = {}
    for namespace, value in updated.items():
        if isinstance(value, dict) and "updated" in value:
            cleaned_value = value.get("updated")
            if isinstance(cleaned_value, dict):
                cleaned[namespace] = cleaned_value
        elif isinstance(value, dict):
            cleaned[namespace] = value
    return cleaned


def _clean_defaults_for_prompt(defaults: Dict[str, object]) -> Dict[str, object]:
    cleaned: Dict[str, object] = {}
    for namespace, value in defaults.items():
        if isinstance(value, dict):
            filtered = {
                key: val
                for key, val in value.items()
                if key not in {"success", "updated"}
            }
            cleaned[namespace] = filtered
        else:
            cleaned[namespace] = value
    return cleaned


def _synthesize_toolcall(user_text: str, last_asset_id: Optional[str]) -> Optional[Dict[str, object]]:
    defaults_args = _parse_defaults_intent(user_text)
    if defaults_args:
        return {"tool": "set_defaults", "args": {"image": defaults_args}}
    if last_asset_id:
        overrides = _parse_overrides_from_text(user_text)
        args: Dict[str, object] = {"asset_id": last_asset_id}
        if overrides:
            args["param_overrides"] = overrides
        return {"tool": "regenerate", "args": args}
    return None


def _parse_defaults_intent(user_text: str) -> Dict[str, object]:
    if not _requires_defaults_toolcall(user_text):
        return {}
    overrides = _parse_overrides_from_text(user_text)
    return overrides


def _parse_overrides_from_text(user_text: str) -> Dict[str, object]:
    import re

    overrides: Dict[str, object] = {}
    size_match = re.search(r"(\\d{3,4})\\s*[xX]\\s*(\\d{3,4})", user_text)
    if size_match:
        overrides["width"] = int(size_match.group(1))
        overrides["height"] = int(size_match.group(2))
    steps_match = re.search(r"(\\d{1,3})\\s*steps?", user_text, re.IGNORECASE)
    if steps_match:
        overrides["steps"] = int(steps_match.group(1))
    cfg_match = re.search(r"cfg\\s*(\\d+(?:\\.\\d+)?)", user_text, re.IGNORECASE)
    if cfg_match:
        overrides["cfg"] = float(cfg_match.group(1))
    return overrides


def _fallback_final_text(last_asset_id: Optional[str]) -> str:
    if last_asset_id:
        return f"Done. Last asset_id: {last_asset_id}. What should we tweak next?"
    return "Done. What should we tweak next?"


def canonicalize_tool_result(tool: str, raw: Dict[str, object]) -> Dict[str, object]:
    if "error" in raw:
        data = {"error": raw.get("error")}
        if "detail" in raw:
            data["detail"] = raw.get("detail")
        return {"ok": False, "tool": tool, "data": data}

    if raw.get("success") is False:
        errors = raw.get("errors")
        return {"ok": False, "tool": tool, "data": {"errors": errors}}

    if tool in {"generate_image", "regenerate"}:
        data = {
            "asset_id": raw.get("asset_id"),
            "asset_url": raw.get("asset_url"),
            "width": raw.get("width"),
            "height": raw.get("height"),
            "mime_type": raw.get("mime_type"),
        }
        return {"ok": True, "tool": tool, "data": data}

    if tool == "set_defaults":
        return {"ok": True, "tool": tool, "data": {"updated": raw.get("updated", {})}}

    if tool == "get_defaults":
        return {"ok": True, "tool": tool, "data": raw}

    return {"ok": True, "tool": tool, "data": raw}

