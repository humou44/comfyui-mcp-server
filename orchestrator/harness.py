"""Basic evaluation harness for the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class TestCase:
    prompt: str
    expected_tools: Optional[Sequence[str]] = None
    require_tool: bool = True


def default_test_suite() -> List[TestCase]:
    return [
        TestCase("set default to 1024x1024 and 30 steps", ["set_defaults"]),
        TestCase("generate: a neon-lit rainy street, bladerunner vibe", ["generate_image"]),
        TestCase("make it less noisy, keep composition, regenerate", ["regenerate"]),
        TestCase("just this once make it 768x768", ["generate_image"]),
        TestCase("regenerate with a different seed", ["regenerate"]),
        TestCase("make it more cinematic, increase contrast slightly", ["regenerate"]),
        TestCase("ambiguous: make it better", None, require_tool=False),
    ]


def extract_tool_events(messages: Iterable[Dict[str, str]]) -> Tuple[List[Dict[str, object]], List[str]]:
    tool_results: List[Dict[str, object]] = []
    tool_errors: List[str] = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "tool_result" in payload:
            tool_results.append(payload["tool_result"])
        if isinstance(payload, dict) and "tool_error" in payload:
            error = payload["tool_error"].get("error")
            if isinstance(error, str):
                tool_errors.append(error)
    return tool_results, tool_errors


def extract_tool_events_from_turn(turn_events: Iterable[Dict[str, object]]) -> Tuple[List[Dict[str, object]], List[str]]:
    tool_results: List[Dict[str, object]] = []
    tool_errors: List[str] = []
    for event in turn_events:
        if event.get("type") == "tool_result":
            payload = event.get("payload")
            if isinstance(payload, dict):
                tool_results.append({"tool": event.get("tool"), **payload})
        if event.get("type") == "validation_error":
            error = event.get("error")
            if isinstance(error, str):
                tool_errors.append(error)
    return tool_results, tool_errors


def evaluate_case(
    case: TestCase,
    tool_results: Sequence[Dict[str, object]],
    tool_errors: Sequence[str],
    tool_call_count: int,
    invalid_retries: int,
) -> Dict[str, object]:
    used_tools = [r.get("tool") for r in tool_results]
    used_tools_str = [t for t in used_tools if isinstance(t, str)]
    used_any = bool(used_tools_str)

    expected_ok = True
    if case.expected_tools:
        expected_ok = any(tool in case.expected_tools for tool in used_tools_str)

    tool_ok = used_any if case.require_tool else True
    errors_ok = len(tool_errors) == 0

    return {
        "prompt": case.prompt,
        "used_tools": used_tools_str,
        "tool_calls": tool_call_count,
        "invalid_retries": invalid_retries,
        "expected_ok": expected_ok,
        "tool_used_ok": tool_ok,
        "tool_errors": tool_errors,
        "passed": expected_ok and tool_ok and errors_ok,
    }


def format_summary(results: Sequence[Dict[str, object]]) -> str:
    lines = []
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    lines.append(f"Summary: {passed}/{total} passing")
    for idx, result in enumerate(results, start=1):
        status = "PASS" if result.get("passed") else "FAIL"
        tools = ", ".join(result.get("used_tools") or [])
        calls = result.get("tool_calls", 0)
        retries = result.get("invalid_retries", 0)
        line = f"{idx:02d}. {status} | tools=[{tools}] | calls={calls} retries={retries} | {result.get('prompt')}"
        lines.append(line)
    return "\n".join(lines)
