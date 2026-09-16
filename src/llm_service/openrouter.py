from typing import Dict, Iterator, List, Optional
from src.models.llm import Response
from src.constants import DEFAULT_MODEL
from openai import OpenAI

import os


class OpenRouterProvider:
    def __init__(self):
        self._api_key: str | None = None

    def set_api_key(self, key: str) -> None:
        self._api_key = key

    def _get_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        api_key = os.getenv("OPEN_ROUTER_API_KEY")
        if api_key:
            return api_key
        raise ValueError("OPEN_ROUTER_API_KEY environment variable not set")

    def _client(self):
        api_key = self._get_api_key()
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def _build_request_params(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]],
        tool_choice: str,
        model_name: str,
        temperature: float,
        response_format: Optional[Dict] = None,
    ) -> Dict:
        request_params = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "extra_body": {"usage": {"include": True}},
        }
        if response_format:
            request_params["response_format"] = response_format
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice
            request_params["parallel_tool_calls"] = True
        return request_params

    def _parse_response(self, response) -> Response:
        choice = response.choices[0].message
        content = getattr(choice, "content", "") or ""
        reasoning_text = getattr(choice, "reasoning", None)

        usage = response.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)
        total_tokens = getattr(usage, "total_tokens", 0)
        cost = getattr(usage, "cost", None)

        completion_details = getattr(usage, "completion_tokens_details", None)
        reasoning_tokens = 0
        if completion_details:
            reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0)

        tool_calls = getattr(choice, "tool_calls", None) or []

        print(
            f"Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, "
            f"Total: {total_tokens}, Reasoning: {reasoning_tokens}"
        )
        if cost is not None:
            print(f"Cost: {cost}")

        return Response(
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning_text,
            model=response.model,
            prompt_tokens=prompt_tokens,
            response_tokens=completion_tokens,
        )

    def generate(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: str = DEFAULT_MODEL,
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
    ) -> Response:
        try:
            client = self._client()
            request_params = self._build_request_params(
                messages,
                tools,
                tool_choice,
                model_name,
                temperature,
                response_format,
            )
            response = client.chat.completions.create(**request_params)
            return self._parse_response(response)
        except Exception as e:
            raise Exception(
                f"Error in OpenRouterProvider: {type(e).__name__}: {e}"
            ) from e

    def stream(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: str = DEFAULT_MODEL,
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
    ) -> Iterator[Response]:
        try:
            client = self._client()
            request_params = self._build_request_params(
                messages,
                tools,
                tool_choice,
                model_name,
                temperature,
                response_format,
            )
            request_params["stream"] = True
            request_params["extra_body"]["reasoning"] = {"enabled": True}
            response_stream = client.chat.completions.create(**request_params)

            for chunk in response_stream:
                choices = getattr(chunk, "choices", None) or []
                choice = choices[0].delta if choices else None
                content = getattr(choice, "content", "") or ""
                reasoning_text = getattr(choice, "reasoning", None)

                tool_calls = getattr(choice, "tool_calls", None) or []
                usage = getattr(chunk, "usage", None)

                if content or tool_calls or reasoning_text or usage:
                    prompt_tokens = None
                    response_tokens = None
                    reasoning_tokens = 0
                    cost = None

                    if usage:
                        prompt_tokens = getattr(usage, "prompt_tokens", None)
                        response_tokens = getattr(usage, "completion_tokens", None)
                        cost = getattr(usage, "cost", None)

                        completion_details = getattr(
                            usage, "completion_tokens_details", None
                        )
                        if completion_details:
                            reasoning_tokens = getattr(
                                completion_details, "reasoning_tokens", 0
                            )

                        if prompt_tokens is not None:
                            total_tokens = getattr(usage, "total_tokens", 0)
                            print(
                                f"Stream Usage - Prompt: {prompt_tokens}, Completion: {response_tokens}, "
                                f"Total: {total_tokens}, Reasoning: {reasoning_tokens}"
                            )
                            if cost is not None:
                                print(f"Stream Cost: {cost}")

                    yield Response(
                        content=content,
                        tool_calls=tool_calls if tool_calls else None,
                        reasoning=reasoning_text,
                        model=getattr(chunk, "model", None),
                        prompt_tokens=prompt_tokens,
                        response_tokens=response_tokens,
                    )

        except Exception as e:
            raise Exception(
                f"Error in OpenRouterProvider: {type(e).__name__}: {e}"
            ) from e
