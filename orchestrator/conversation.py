"""Conversation state and truncation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ConversationState:
    messages: List[Dict[str, str]] = field(default_factory=list)
    defaults_cache: Dict[str, object] = field(default_factory=dict)
    last_asset_id: str | None = None
    last_model_output: str | None = None
    last_llm_ms: float | None = None
    last_prompt_messages: List[Dict[str, str]] | None = None
    last_turn_events: List[Dict[str, object]] = field(default_factory=list)
    tool_calls_this_turn: int = 0
    invalid_tool_retries: int = 0

    def append(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def truncate(self, max_messages: int) -> None:
        if max_messages <= 0:
            return
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

