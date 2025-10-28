from tools.tool_registry import ToolRegistry
from utils import call_llm
import json
from prompt_manager.system_prompt import system_prompt

MAX_ITERATIONS = 50

class Agent:
    def __init__(self):
        self.name = "terminus-cli"
        self.description = ""
        self.context = []
        self.iteration = 0
        self.max_iterations = MAX_ITERATIONS
        self.system_prompt = system_prompt
        self.llm_service = None 
        self.tool_registry = ToolRegistry()  

        print("[INIT] Agent initialized successfully.")
        print(f"[INIT] Name: {self.name}")
        print(f"[INIT] Max iterations: {self.max_iterations}")

    def add_system_message(self):
        print("[CONTEXT] Adding system message.")
        self.context.append({"role": "system", "content": self.system_prompt})
    
    def add_user_message(self, content):
        print(f"[CONTEXT] Adding user message: {content}")
        self.context.append({"role": "user", "content": content})
    
    def add_assistant_message(self, content):
        print("[CONTEXT] Adding assistant message.")
        self.context.append({"role": "assistant", "content": content})

    def add_tool_message(self, tool_call, tool_output):
        print(f"[CONTEXT] Adding tool message for tool: {tool_call.function.name}")
        self.context.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.function.name,
            "content": tool_output
        })

    def run(self, user_message):
        print(f"[RUN] Starting agent run with user message: '{user_message}'")
        self.add_system_message()
        self.add_user_message(user_message)

        while self.iteration < self.max_iterations:
            print(f"\n[ITERATION] Iteration {self.iteration + 1}/{self.max_iterations}")
            print("[LLM] Calling LLM with current context...")
            
            try:
                output = call_llm(self.context)
            except Exception as e:
                print(f"[ERROR] Failed to call LLM: {e}")
                return "Error occurred while calling LLM."

            if output is None:
                print("[ERROR] LLM returned None.")
                return "Error: LLM did not return a valid response."

            if hasattr(output, "tool_calls") and output.tool_calls:
                print("[LLM] Tool call detected.")
                content = getattr(output, "content", "")
                tool_call = output.tool_calls[0]  # Get first tool call
                reasoning = getattr(output, "reasoning", "")

                print(f"[TOOL] Tool name: {tool_call.function.name}")
                print(f"[TOOL] Tool arguments (raw): {tool_call.function.arguments}")

                try:
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"[TOOL] Parsed tool arguments: {tool_args}")
                except json.JSONDecodeError:
                    print("[ERROR] Failed to parse tool arguments as JSON.")
                    return "Error: Invalid tool arguments format."

                try:
                    tool_output = self.tool_registry.run_tool(tool_call.function.name, **tool_args)
                    print(f"[TOOL] Tool output: {tool_output}")
                except Exception as e:
                    print(f"[ERROR] Tool execution failed: {e}")
                    return f"Error: Tool execution failed for {tool_call.function.name}"

                self.add_assistant_message(content=content)
                self.add_tool_message(tool_call, tool_output)
                self.iteration += 1
            else:
                print("[LLM] No tool calls detected. Returning final response.")
                print(f"[OUTPUT] Final content: {getattr(output, 'content', '')}")
                return getattr(output, "content", "")

        print("[STOP] Max iterations reached. Terminating process.")
        return "Max iterations reached. Process terminated."

if __name__ == "__main__":
    agent = Agent()
    result = agent.run("what is the name of the project")
    print(f"\n[FINAL RESULT] {result}")
