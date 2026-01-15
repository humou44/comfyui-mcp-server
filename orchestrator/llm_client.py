"""Local LLM client (Ollama)."""

from __future__ import annotations

import json
from typing import Dict, List

import requests


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_s: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        top_p: float = 0.9,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
            },
        }
        try:
            response = requests.post(url, json=payload, timeout=self.timeout_s)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Ollama response was not JSON: {response.text[:200]}") from exc

        message = data.get("message", {})
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Ollama response missing content: {data}")
        return content.strip()

