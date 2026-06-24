import json
from typing import Any, Callable, Dict, List, Optional

from core.client import OllamaClient


class Agent:
    def __init__(
        self,
        client: OllamaClient,
        system: str = "",
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_registry: Optional[Dict[str, Callable[..., Any]]] = None,
        max_iterations: int = 8,
        trace: bool = False,
    ) -> None:
        self.client = client
        self.system = system
        self.messages: List[Dict[str, Any]] = []
        self.tools = tools if tools is not None else []
        self.tool_registry = tool_registry if tool_registry is not None else {}
        self.max_iterations = max_iterations
        self.trace = trace
        if self.system:
            self.messages.append({"role": "system", "content": system})

    def __call__(self, message: str = "") -> str:
        return self.execute(message)

    def _trace_print(self, label: str, payload: Any) -> None:
        if not self.trace:
            return
        if isinstance(payload, (dict, list)):
            text = json.dumps(payload, ensure_ascii=True, indent=2)
        else:
            text = str(payload)
        print(f"\n[TRACE] {label}\n{text}")

    def execute(self, message: str = "") -> str:
        if message:
            self.messages.append({"role": "user", "content": message})
            self._trace_print("user", {"content": message})

        for iteration in range(1, self.max_iterations + 1):
            self._trace_print("iteration", {"index": iteration})

            completion = self.client.chat.completions.create(
                messages=self.messages,
                tools=self.tools,
                tool_choice="auto",
            )

            response_message = completion.choices[0].message
            self._trace_print("assistant_raw", response_message.to_dict())

            if response_message.reasoning:
                self._trace_print("assistant_reasoning", response_message.reasoning)

            if response_message.tool_calls and response_message.content.strip():
                self._trace_print("assistant_plan", response_message.content.strip())

            if response_message.tool_calls:
                self.messages.append(response_message.to_dict())

                tool_outputs: List[Dict[str, Any]] = []
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    try:
                        function_args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        function_args = {}

                    function_to_call = self.tool_registry.get(function_name)
                    if function_to_call is None:
                        tool_output = {"error": f"Tool '{function_name}' not found."}
                    else:
                        try:
                            tool_output = function_to_call(**function_args)
                        except Exception as err:  # pragma: no cover
                            tool_output = {"error": f"Tool execution failed: {err}"}

                    self._trace_print(
                        "tool_execution",
                        {
                            "name": function_name,
                            "args": function_args,
                            "output": tool_output,
                        },
                    )

                    tool_outputs.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps(tool_output, ensure_ascii=True),
                        }
                    )

                self.messages.extend(tool_outputs)
                continue

            final_assistant_content = response_message.content
            if final_assistant_content:
                self.messages.append({"role": "assistant", "content": final_assistant_content})
            self._trace_print("final_response", final_assistant_content)
            return final_assistant_content

        fallback = "Nao consegui concluir em tempo habil. Tente novamente com um prompt mais especifico."
        self.messages.append({"role": "assistant", "content": fallback})
        self._trace_print("fallback", fallback)
        return fallback
