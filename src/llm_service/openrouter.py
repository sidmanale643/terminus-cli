from typing import List, Dict, Optional
from src.models.llm import Response
from openai import OpenAI, AsyncOpenAI
from src.utils import parse_tool_calls
from src.llm_service.base_class import LlmProvider

from dotenv import load_dotenv

load_dotenv()

class OpenRouterProvider(LlmProvider):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def _client(self):
        api_key = self._get_api_key("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY")
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def _async_client(self):
        api_key = self._get_api_key("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY")
        return AsyncOpenAI(
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
        provider_routing: Optional[List[str]] = None,
    ) -> Dict:
        request_params = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "extra_body": {"usage": {"include": True}}
        }
        if provider_routing:
            request_params["extra_body"]["provider"] = {"order": provider_routing}
        if tools and len(tools) > 0:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice
            request_params["parallel_tool_calls"] = True
        return request_params

    def _parse_response(self, response, temperature: float, trace_generation=None) -> Response:
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

        tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))
        stop_reason = "tool_use" if tool_calls else "end_turn"

        print(f"Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, "
              f"Total: {total_tokens}, Reasoning: {reasoning_tokens}")
        if cost is not None:
            print(f"Cost: {cost}")

        if trace_generation:
            end_kwargs = {
                "output": content,
                "usage": {
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": total_tokens,
                },
            }
            if cost is not None:
                end_kwargs["cost_details"] = {"total": cost}
            trace_generation.end(**end_kwargs)

        return Response(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            reasoning=reasoning_text,
            model=response.model,
            temperature=temperature,
            prompt_tokens=prompt_tokens,
            response_tokens=completion_tokens
        )

    def generate(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: str = "minimax/minimax-m2.5:free",
        temperature: float = 0.3,
        trace=None,
        provider_routing: Optional[List[str]] = None,
    ) -> Response:
        """
        Makes a request to OpenRouter API with optional reasoning capabilities.
        """
        generation = None
        if trace:
            generation = trace.generation(
                name="openrouter-completion",
                model=model_name,
                input=messages,
                metadata={"provider": "openrouter", "temperature": temperature},
            )
        try:
            client = self._client()
            request_params = self._build_request_params(
                messages, tools, tool_choice, model_name, temperature, provider_routing
            )
            response = client.chat.completions.create(**request_params)
            return self._parse_response(response, temperature, generation)
        except Exception as e:
            if generation:
                generation.end(level="ERROR", status_message=str(e))
            raise Exception(f"Error in OpenRouterProvider: {type(e).__name__}: {e}")

    async def agenerate(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: str = "minimax/minimax-m2.5:free",
        temperature: float = 0.3,
        trace=None,
        provider_routing: Optional[List[str]] = None,
    ) -> Response:
        """Async generate using AsyncOpenAI."""
        generation = None
        if trace:
            generation = trace.generation(
                name="openrouter-completion-async",
                model=model_name,
                input=messages,
                metadata={"provider": "openrouter", "temperature": temperature},
            )
        try:
            client = self._async_client()
            request_params = self._build_request_params(
                messages, tools, tool_choice, model_name, temperature, provider_routing
            )
            response = await client.chat.completions.create(**request_params)
            return self._parse_response(response, temperature, generation)
        except Exception as e:
            if generation:
                generation.end(level="ERROR", status_message=str(e))
            raise Exception(f"Error in OpenRouterProvider async: {type(e).__name__}: {e}")

    def stream(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        model_name: str = "minimax/minimax-m2.5:free",
        temperature: float = 0.3,
        stream: bool = True,
        provider_routing: Optional[List[str]] = None,
    ) -> Response:
        """
        Stream a response from OpenRouter.
        """
        api_key = self._get_api_key("OPEN_ROUTER_API_KEY", "OPENROUTER_API_KEY")

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        try:
            request_params = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
                "extra_body": {"usage": {"include": True},
                "reasoning" : {"enabled": True}}
            }

            if provider_routing:
                request_params["extra_body"]["provider"] = {"order": provider_routing}

            # Add tools if provided
            if tools and len(tools) > 0:
                request_params["tools"] = tools
                request_params["tool_choice"] = tool_choice
                request_params["parallel_tool_calls"] = True

            stream = client.chat.completions.create(**request_params)

            for chunk in stream:
                choice = chunk.choices[0].delta
                content = getattr(choice, "content", "") or ""
                reasoning_text = getattr(choice, "reasoning", None)

                tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))

                if content or (tool_calls and len(tool_calls) > 0) or reasoning_text:
                    stop_reason = "tool_use" if (tool_calls and len(tool_calls) > 0) else "end_turn"

                    # Extract usage from chunk if available (usually in the last chunk)
                    usage = getattr(chunk, "usage", None)
                    prompt_tokens = None
                    response_tokens = None
                    reasoning_tokens = 0
                    cost = None

                    if usage:
                        prompt_tokens = getattr(usage, "prompt_tokens", None)
                        response_tokens = getattr(usage, "completion_tokens", None)
                        cost = getattr(usage, "cost", None)

                        # Extract reasoning tokens if available
                        completion_details = getattr(usage, "completion_tokens_details", None)
                        if completion_details:
                            reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0)

                        # Print usage summary when available (final chunk)
                        if prompt_tokens is not None:
                            total_tokens = getattr(usage, "total_tokens", 0)
                            print(f"Stream Usage - Prompt: {prompt_tokens}, Completion: {response_tokens}, "
                                  f"Total: {total_tokens}, Reasoning: {reasoning_tokens}")
                            if cost is not None:
                                print(f"Stream Cost: {cost}")

                    yield Response(
                        content=content,
                        tool_calls=tool_calls if len(tool_calls) > 0 else None,
                        stop_reason=stop_reason,
                        reasoning=reasoning_text,
                        model=getattr(chunk, "model", None),
                        temperature=temperature,
                        prompt_tokens=prompt_tokens,
                        response_tokens=response_tokens
                    )

        except Exception as e:
            print(f"Error in OpenRouterProvider: {type(e).__name__}: {e}")
            yield Response(
                content="",
                tool_calls=None,
                stop_reason="error",
                reasoning=None,
                model=None,
                temperature=None,
                prompt_tokens=None,
                response_tokens=None
            )
