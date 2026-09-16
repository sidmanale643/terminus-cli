from dataclasses import dataclass
from threading import Event
from types import SimpleNamespace
from typing import Any, Callable


@dataclass(slots=True)
class ResponseResult:
    content: str
    tool_calls: list[Any]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _usage_payload(llm_service: Any, model_name: str | None, response: Any) -> dict:
    return {
        "provider": llm_service.active_provider_name,
        "requested_model": model_name,
        "response_model": _field(response, "model"),
        "prompt_tokens": _field(response, "prompt_tokens"),
        "response_tokens": _field(response, "response_tokens"),
    }


def request_llm_response(
    llm_service: Any,
    *,
    messages: list[dict],
    tools: list[dict] | None,
    model_name: str | None,
    use_streaming: bool,
    stop_event: Event | None = None,
    response_format: dict | None = None,
    status_callback: Callable[..., Any] | None = None,
    stream_callback: Callable[[str], Any] | None = None,
    usage_callback: Callable[[dict], Any] | None = None,
    tool_choice: str = "auto",
    temperature: float = 0.3,
) -> ResponseResult:
    stop_event = stop_event or Event()
    if stop_event.is_set():
        raise KeyboardInterrupt()

    request_kwargs = {
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
        "model_name": model_name,
        "temperature": temperature,
        "response_format": response_format,
    }

    if not use_streaming:
        response = llm_service.generate(**request_kwargs)
        if usage_callback:
            usage_callback(_usage_payload(llm_service, model_name, response))

        reasoning = _field(response, "reasoning")
        if reasoning and status_callback and reasoning.strip():
            status_callback(reasoning, is_thinking=True)

        if stop_event.is_set():
            raise KeyboardInterrupt()
        return ResponseResult(
            content=_field(response, "content", "") or "",
            tool_calls=list(_field(response, "tool_calls") or []),
        )

    accumulated_content = ""
    streamed_tool_calls: dict[Any, dict[str, str | None]] = {}
    for response_chunk in llm_service.stream(**request_kwargs):
        if stop_event.is_set():
            raise KeyboardInterrupt()

        chunk_error = _field(response_chunk, "error")
        if chunk_error:
            raise RuntimeError(f"LLM stream error: {chunk_error}")
        if _field(response_chunk, "stop_reason") == "error":
            raise RuntimeError("LLM stream ended with an error")

        if usage_callback and (
            _field(response_chunk, "prompt_tokens") is not None
            or _field(response_chunk, "response_tokens") is not None
        ):
            usage_callback(_usage_payload(llm_service, model_name, response_chunk))

        reasoning = _field(response_chunk, "reasoning")
        if reasoning and status_callback:
            status_callback(reasoning, is_thinking=True)

        content = _field(response_chunk, "content")
        if content:
            accumulated_content += content
            if stream_callback:
                stream_callback(content)

        for tool_call in _field(response_chunk, "tool_calls", []) or []:
            index = _field(tool_call, "index", 0)
            if index is None:
                index = 0
            current = streamed_tool_calls.setdefault(
                index,
                {
                    "id": _field(tool_call, "id"),
                    "name": "",
                    "arguments": "",
                },
            )
            current["id"] = _field(tool_call, "id") or current["id"]
            function = _field(tool_call, "function")
            if function:
                current["name"] += _field(function, "name") or ""
                current["arguments"] += _field(function, "arguments") or ""

    final_tool_calls = [
        SimpleNamespace(
            id=value["id"],
            function=SimpleNamespace(name=value["name"], arguments=value["arguments"]),
        )
        for _, value in sorted(streamed_tool_calls.items())
    ]
    if stop_event.is_set():
        raise KeyboardInterrupt()
    return ResponseResult(content=accumulated_content, tool_calls=final_tool_calls)
