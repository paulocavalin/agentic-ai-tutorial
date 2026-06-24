import json
from typing import Any, Dict, List, Optional

import requests

from core.models import (
    ChatCompletionResponse,
    Choice,
    FunctionCall,
    Message,
    ToolCall,
)


class _ChatCompletions:
    def __init__(self, outer: "OllamaClient") -> None:
        self.outer = outer

    def create(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> ChatCompletionResponse:
        payload: Dict[str, Any] = {
            "model": self.outer.model,
            "messages": messages,
        }
        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        resp = requests.post(
            f"{self.outer.base_url}/chat/completions",
            json=payload,
            timeout=self.outer.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        raw_message = data["choices"][0]["message"]
        raw_tool_calls = raw_message.get("tool_calls") or []

        tool_calls: List[ToolCall] = []
        for item in raw_tool_calls:
            fn = item.get("function") or {}
            args = fn.get("arguments", "{}")
            if isinstance(args, dict):
                args = json.dumps(args)
            tool_calls.append(
                ToolCall(
                    id=str(item.get("id", "")),
                    type=str(item.get("type", "function")),
                    function=FunctionCall(
                        name=str(fn.get("name", "")),
                        arguments=str(args),
                    ),
                )
            )

        reasoning = (
            raw_message.get("reasoning")
            or raw_message.get("reasoning_content")
            or raw_message.get("thinking")
            or ""
        )

        message = Message(
            role=str(raw_message.get("role", "assistant")),
            content=str(raw_message.get("content", "")),
            tool_calls=tool_calls or None,
            reasoning=str(reasoning) if reasoning else None,
        )
        return ChatCompletionResponse(choices=[Choice(message=message)])


class _Chat:
    def __init__(self, outer: "OllamaClient") -> None:
        self.completions = _ChatCompletions(outer)


class OllamaClient:
    def __init__(
        self,
        model: str = "gemma4:12b",
        base_url: str = "http://localhost:11434/v1",
        timeout: int = 120,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.chat = _Chat(self)
