from typing import List, Dict, Optional
from src.models.llm import Response
from groq import Groq, AsyncGroq
from src.utils import parse_tool_calls
from src.llm_service.base_class import LlmProvider


class GroqProvider(LlmProvider):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def _sync_client(self):
        api_key = self._get_api_key("GROQ_API_KEY")
        return Groq(api_key=api_key)

    def _async_client(self):
        api_key = self._get_api_key("GROQ_API_KEY")
        return AsyncGroq(api_key=api_key)

    def _build_params(self, messages, tools, tool_choice, model_name, temperature):
        return {
            "model": model_name,
            "messages": messages,
            "tools": tools or [],
            "tool_choice": tool_choice,
            "temperature": temperature,
        }

    def _parse_choice(self, choice, temperature):
        content = getattr(choice, "content", "") or ""
        reasoning_text = getattr(choice, "reasoning", None)
        tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))
        stop_reason = "tool_use" if tool_calls else "end_turn"
        return content, reasoning_text, tool_calls, stop_reason

    def generate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "moonshotai/kimi-k2-instruct-0905", 
        temperature: float = 0.3,
        trace=None,
    ) -> Response:
        """
        Makes a request to Groq API with optional reasoning capabilities.
        """
        generation = None
        if trace:
            generation = trace.generation(
                name="groq-completion",
                model=model_name,
                input=messages,
                metadata={"provider": "groq", "temperature": temperature},
            )
        
        try:
            request_params = self._build_params(messages, tools, tool_choice, model_name, temperature)
            response = self._sync_client().chat.completions.create(**request_params)

            choice = response.choices[0].message
            content, reasoning_text, tool_calls, stop_reason = self._parse_choice(choice, temperature)

            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            completion_tokens = getattr(usage, "completion_tokens", None) if usage else None

            if generation:
                generation.end(
                    output=content,
                    usage={
                        "input": prompt_tokens or 0,
                        "output": completion_tokens or 0,
                        "total": getattr(usage, "total_tokens", 0) if usage else 0,
                    } if usage else None,
                )

            return Response(
                content=content,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                reasoning=reasoning_text,
                prompt_tokens=prompt_tokens,
                response_tokens=completion_tokens,
            )

        except Exception as e:
            if generation:
                generation.end(level="ERROR", status_message=str(e))
            raise Exception(f"Error in GroqProvider: {type(e).__name__}: {e}")

    async def agenerate(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "moonshotai/kimi-k2-instruct-0905", 
        temperature: float = 0.3,
        trace=None,
    ) -> Response:
        """Async generate using AsyncGroq."""
        generation = None
        if trace:
            generation = trace.generation(
                name="groq-completion-async",
                model=model_name,
                input=messages,
                metadata={"provider": "groq", "temperature": temperature},
            )
        
        try:
            request_params = self._build_params(messages, tools, tool_choice, model_name, temperature)
            response = await self._async_client().chat.completions.create(**request_params)

            choice = response.choices[0].message
            content, reasoning_text, tool_calls, stop_reason = self._parse_choice(choice, temperature)

            usage = getattr(response, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            completion_tokens = getattr(usage, "completion_tokens", None) if usage else None

            if generation:
                generation.end(
                    output=content,
                    usage={
                        "input": prompt_tokens or 0,
                        "output": completion_tokens or 0,
                        "total": getattr(usage, "total_tokens", 0) if usage else 0,
                    } if usage else None,
                )

            return Response(
                content=content,
                tool_calls=tool_calls,
                stop_reason=stop_reason,
                reasoning=reasoning_text,
                prompt_tokens=prompt_tokens,
                response_tokens=completion_tokens,
            )

        except Exception as e:
            if generation:
                generation.end(level="ERROR", status_message=str(e))
            raise Exception(f"Error in GroqProvider async: {type(e).__name__}: {e}")
    
    def stream(
        self, 
        messages: List[Dict], 
        tools: Optional[List[Dict]] = None, 
        tool_choice: str = "auto", 
        model_name: str = "moonshotai/kimi-k2-instruct-0905", 
        temperature: float = 0.3,
        stream : bool = True
    ):
        """
        Stream a response from Groq.
        """
        api_key = self._get_api_key("GROQ_API_KEY")
        groq_client = Groq(api_key=api_key)
        
        try:
            request_params = {
                "model": model_name,
                "messages": messages,
                "tools": tools or [],
                "tool_choice": tool_choice,
                "temperature": temperature,
                "stream" : True,
            }

            stream = groq_client.chat.completions.create(**request_params)

            for chunk in stream:
                choice = chunk.choices[0].delta 
                content = getattr(choice, "content", "") or ""
                reasoning_text = getattr(choice, "reasoning", None)
                
                tool_calls = parse_tool_calls(getattr(choice, "tool_calls", None))

                if content or (tool_calls and len(tool_calls) > 0) or reasoning_text:
                    stop_reason = "tool_use" if (tool_calls and len(tool_calls) > 0) else "end_turn"
                    
                    yield Response(
                        content=content,
                        tool_calls=tool_calls if len(tool_calls) > 0 else None,
                        stop_reason=stop_reason,
                        reasoning=reasoning_text
                    )

        except Exception:
            yield Response(content="", tool_calls=None, stop_reason="error", reasoning=None)
