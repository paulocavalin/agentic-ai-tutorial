import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FunctionCall:
    name: str
    arguments: str


@dataclass
class ToolCall:
    id: str
    type: str
    function: FunctionCall

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


@dataclass
class Message:
    role: str
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        if self.reasoning:
            payload["reasoning"] = self.reasoning
        return payload


@dataclass
class Choice:
    message: Message


@dataclass
class ChatCompletionResponse:
    choices: List[Choice]
