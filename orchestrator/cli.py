"""Command-line entrypoint for the orchestrator."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Optional

import anyio

from .config import load_config
from .harness import default_test_suite, evaluate_case, extract_tool_events_from_turn, format_summary
from .llm_client import OllamaClient
from .mcp_client import McpHttpClient, McpHttpConfig, McpServerConfig, McpStdioClient
from .orchestrator import Orchestrator, RuntimeConfig


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="orchestrator", description="Local LLM orchestrator for ComfyUI MCP tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Start a chat REPL")
    chat_parser.add_argument("--ollama-url", default=None)
    chat_parser.add_argument("--ollama-model", default=None)
    chat_parser.add_argument("--ollama-timeout-s", type=int, default=None)
    chat_parser.add_argument("--mcp-transport", default=None)
    chat_parser.add_argument("--mcp-url", default=None)
    chat_parser.add_argument("--mcp-cmd", default=None)
    chat_parser.add_argument("--mcp-cwd", default=None)
    chat_parser.add_argument(
        "--trace-out",
        default=None,
        help="Write JSONL trace events to a file during chat.",
    )

    eval_parser = subparsers.add_parser("eval", help="Run a basic eval suite")
    eval_parser.add_argument("--ollama-url", default=None)
    eval_parser.add_argument("--ollama-model", default=None)
    eval_parser.add_argument("--ollama-timeout-s", type=int, default=None)
    eval_parser.add_argument("--mcp-transport", default=None)
    eval_parser.add_argument("--mcp-url", default=None)
    eval_parser.add_argument("--mcp-cmd", default=None)
    eval_parser.add_argument("--mcp-cwd", default=None)
    eval_parser.add_argument("--verbose", action="store_true")
    eval_parser.add_argument("--trace", action="store_true")
    eval_parser.add_argument(
        "--trace-level",
        choices=["basic", "full"],
        default=None,
        help="Emit JSONL trace events (basic or full).",
    )
    eval_parser.add_argument(
        "--trace-out",
        default=None,
        help="Write JSONL trace events to a file instead of stdout.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "chat":
        return anyio.run(_run_chat, args)
    if args.command == "eval":
        return anyio.run(_run_eval, args)
    return 0


async def _run_chat(args: argparse.Namespace) -> int:
    config = load_config(
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout_s=args.ollama_timeout_s,
        mcp_transport=args.mcp_transport,
        mcp_url=args.mcp_url,
        mcp_cmd=args.mcp_cmd,
        mcp_cwd=args.mcp_cwd,
    )

    llm = OllamaClient(
        config.ollama_url,
        config.ollama_model,
        timeout_s=config.ollama_timeout_s,
    )
    orch = Orchestrator(
        RuntimeConfig(
            max_tool_calls=config.max_tool_calls,
            max_invalid_calls=config.max_invalid_calls,
            max_messages=config.max_messages,
        ),
        llm,
        mcp_client=None,  # set after session starts
    )

    trace_sink = _open_trace_sink(args.trace_out) if args.trace_out else None
    run_id = _new_run_id() if trace_sink else None
    if trace_sink:
        _emit_trace_event({"event": "run_start", "run_id": run_id}, trace_sink)

    async with _open_mcp_client(config) as mcp:
        orch.mcp_client = mcp
        await _repl(orch, trace_sink=trace_sink, run_id=run_id)

    if trace_sink:
        _emit_trace_event({"event": "run_end", "run_id": run_id}, trace_sink)
        trace_sink.close()
    return 0


async def _run_eval(args: argparse.Namespace) -> int:
    config = load_config(
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout_s=args.ollama_timeout_s,
        mcp_transport=args.mcp_transport,
        mcp_url=args.mcp_url,
        mcp_cmd=args.mcp_cmd,
        mcp_cwd=args.mcp_cwd,
    )

    llm = OllamaClient(
        config.ollama_url,
        config.ollama_model,
        timeout_s=config.ollama_timeout_s,
    )
    orch = Orchestrator(
        RuntimeConfig(
            max_tool_calls=config.max_tool_calls,
            max_invalid_calls=config.max_invalid_calls,
            max_messages=config.max_messages,
        ),
        llm,
        mcp_client=None,
    )

    results = []
    trace_level = args.trace_level or ("basic" if args.trace else None)
    trace_sink = _open_trace_sink(args.trace_out) if trace_level else None
    run_id = _new_run_id() if trace_level else None
    tests = default_test_suite()
    async with _open_mcp_client(config) as mcp:
        orch.mcp_client = mcp
        if trace_level:
            _emit_trace_event({"event": "run_start", "run_id": run_id}, trace_sink)
        for idx, case in enumerate(tests, start=1):
            if trace_level:
                _emit_trace_event(
                    {
                        "event": "case_start",
                        "case_index": idx,
                        "prompt": case.prompt,
                        "run_id": run_id,
                    },
                    trace_sink,
                )
            before_len = len(orch.state.messages)
            _ = await orch.handle_user_turn(case.prompt)
            new_messages = orch.state.messages[before_len:]
            tool_results, tool_errors = extract_tool_events_from_turn(orch.state.last_turn_events)
            result = evaluate_case(
                case,
                tool_results,
                tool_errors,
                orch.state.tool_calls_this_turn,
                orch.state.invalid_tool_retries,
            )
            results.append(result)
            if args.verbose:
                print(json.dumps(result, indent=2, ensure_ascii=True))
                if tool_results:
                    print(json.dumps({"tool_results": tool_results}, indent=2, ensure_ascii=True))
                if tool_errors:
                    print(json.dumps({"tool_errors": tool_errors}, indent=2, ensure_ascii=True))
            if trace_level:
                _emit_turn_trace(
                    idx,
                    case.prompt,
                    orch,
                    new_messages,
                    trace_level,
                    trace_sink,
                    run_id,
                )
                _emit_trace_event(
                    {
                        "event": "case_end",
                        "case_index": idx,
                        "prompt": case.prompt,
                        "result": result,
                        "run_id": run_id,
                    },
                    trace_sink,
                )

        if trace_level:
            _emit_trace_event({"event": "run_end", "run_id": run_id}, trace_sink)

    if trace_sink:
        trace_sink.close()
    print(format_summary(results))
    return 0


def _open_mcp_client(config):
    if config.mcp_transport == "stdio":
        if not config.mcp_command:
            raise ValueError("MCP command is required for stdio transport")
        mcp_config = McpServerConfig(
            command=config.mcp_command,
            args=config.mcp_args,
            env=config.mcp_env,
            cwd=config.mcp_cwd,
        )
        return McpStdioClient(mcp_config)
    if not config.mcp_url:
        raise ValueError("MCP_URL is required for streamable-http transport")
    return McpHttpClient(McpHttpConfig(url=config.mcp_url))


def _open_trace_sink(path: str):
    return open(path, "a", encoding="utf-8")


def _emit_trace_event(event: dict, sink) -> None:
    event = dict(event)
    event["ts"] = _utc_now_iso()
    payload = json.dumps(event, ensure_ascii=True)
    if sink:
        sink.write(payload + "\n")
        sink.flush()
    else:
        print(payload)


def _emit_turn_trace(
    case_index: int,
    prompt: str,
    orch: Orchestrator,
    new_messages: list[dict],
    trace_level: str,
    sink,
    run_id: str | None,
) -> None:
    base = {"case_index": case_index, "prompt": prompt, "run_id": run_id}
    for event in orch.state.last_turn_events:
        payload = _format_trace_event(event, trace_level)
        if payload:
            _emit_trace_event({**base, **payload}, sink)
    if trace_level == "full":
        _emit_trace_event(
            {
                **base,
                "event": "prompt_messages",
                "messages": orch.state.last_prompt_messages,
            },
            sink,
        )
        _emit_trace_event(
            {
                **base,
                "event": "new_messages",
                "messages": new_messages,
            },
            sink,
        )


def _format_trace_event(event: dict, trace_level: str) -> dict:
    event_type = event.get("type")
    if trace_level == "full":
        return {"event": event_type, **event}

    if event_type == "llm_output":
        content = event.get("content") or ""
        return {
            "event": "llm_output",
            "duration_ms": event.get("duration_ms"),
            "chars": len(content),
        }
    if event_type == "final_text":
        content = event.get("content") or ""
        return {"event": "final_text", "chars": len(content)}
    if event_type == "validation_error":
        return {"event": "validation_error", "tool": event.get("tool"), "error": event.get("error")}
    if event_type == "tool_call":
        return {
            "event": "tool_call",
            "tool": event.get("tool"),
            "duration_ms": event.get("duration_ms"),
        }
    if event_type == "tool_result":
        payload = event.get("payload", {})
        ok = payload.get("ok") if isinstance(payload, dict) else None
        return {"event": "tool_result", "tool": event.get("tool"), "ok": ok}
    return {"event": event_type}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


async def _repl(orch: Orchestrator, trace_sink=None, run_id: str | None = None) -> None:
    print("ComfyUI Orchestrator (type 'exit' to quit)")
    turn_index = 0
    while True:
        user_text = await anyio.to_thread.run_sync(lambda: input("> ").strip())
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            break
        turn_index += 1
        before_len = len(orch.state.messages)
        reply = await orch.handle_user_turn(user_text)
        if trace_sink:
            new_messages = orch.state.messages[before_len:]
            _emit_turn_trace(
                turn_index,
                user_text,
                orch,
                new_messages,
                "full",
                trace_sink,
                run_id,
            )
        last_asset = orch.state.last_asset_id
        if last_asset:
            print(f"{reply}\n(last_asset_id: {last_asset})")
        else:
            print(reply)

