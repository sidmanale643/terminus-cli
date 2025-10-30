from tools.tool_registry import ToolRegistry
from utils import groq
import json
from prompts import PromptManager
from dotenv import load_dotenv
from session_manager import SessionHistory

load_dotenv()

MAX_ITERATIONS = 50

class Agent:
    def __init__(self):
        print("[INIT] Initializing Agent...")

        self.name = "terminus-cli"
        self.description = ""
        self.context = []
        self.context_size = 0
        self.model_context_size = 128000
        self.iteration = 0
        self.max_iterations = MAX_ITERATIONS
        self.prompt_manager = PromptManager()
        self.system_prompt = self.prompt_manager.get_system_prompt()
        self.llm_service = None 
        self.tool_registry = ToolRegistry()
        self.model = "kimi-k2-instruct-0905"
        
        # Initialize session manager
        self.session_manager = SessionHistory()
        print("[INIT] Session manager initialized.")

        print("[INIT] Agent initialized successfully.")

    def add_system_message(self):
        message = {"role": "system", "content": self.system_prompt}
        self.context.append(message)
        # Store complete message structure as JSON
        self.session_manager.insert_to_session_history("system", json.dumps(message))
    
    def add_user_message(self, content):
        message = {"role": "user", "content": content}
        self.context.append(message)
        # Store complete message structure as JSON
        self.session_manager.insert_to_session_history("user", json.dumps(message))
    
    def add_assistant_message(self, content, tool_calls=None):

        message = {"role": "assistant", "content": content}
        if tool_calls:
           
            message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in (tool_calls if isinstance(tool_calls, list) else [tool_calls])
            ]
        self.context.append(message)
        # Store complete message structure as JSON (including tool_calls if present)
        self.session_manager.insert_to_session_history("assistant", json.dumps(message))

    def add_tool_message(self, tool_call, tool_output):
        message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.function.name,
            "content": tool_output
        }
        self.context.append(message)
        # Store complete message structure as JSON
        self.session_manager.insert_to_session_history("tool", json.dumps(message))
    
    def update_context_size(self):
        self.message_context_size = [len(message["content"]) for message in self.context]
        self.context_size = sum(self.message_context_size)
        print(f"[CONTEXT] Updated context size: {self.context_size}")

    def get_session_history(self, limit=None):
        """Retrieve current session history"""
        return self.session_manager.retrieve_session_history(limit)
    
    def get_chat_history(self, name=None, chat_id=None, limit=None):
        """Retrieve persistent chat history"""
        return self.session_manager.retrieve_chat_history(name, chat_id, limit)
    
    def save_session(self, name):
        """Save current session to persistent chat history"""
        # Get session history and parse JSON messages
        session_messages = self.session_manager.retrieve_session_history()
        # Parse the JSON content back to message objects
        parsed_messages = []
        for msg in session_messages:
            try:
                parsed_messages.append(json.loads(msg["content"]))
            except json.JSONDecodeError:
                # If it's not JSON, store as-is (backward compatibility)
                parsed_messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Save to chat history
        return self.session_manager.insert_to_chat_history(name, parsed_messages)
    
    def clear_session(self):
        """Clear current session history"""
        self.session_manager.clear_session_history()
        self.context = []
        self.iteration = 0  # Reset iteration counter as well
    
    def load_session(self, name):
        """Load a saved session into current session"""
        chat_history = self.session_manager.retrieve_chat_history(name=name, limit=1)
        if chat_history:
            # Clear current session first
            self.clear_session()
            # Load the saved chat history
            for message in chat_history[0]["chat_history"]:
                self.context.append(message)
                # Store back to session history as JSON
                self.session_manager.insert_to_session_history(message["role"], json.dumps(message))
            print(f"[SESSION] Loaded session '{name}' with {len(self.context)} messages.")
            return True
        print(f"[SESSION] No session found with name '{name}'.")
        return False

    def run(self, user_message):
        print(f"[RUN] Starting agent run with user message: '{user_message}'")

        # Add system prompt if context is empty (first run)
        if not self.context:
            self.add_system_message()
            print("[INIT] System prompt added to context.")

        self.add_user_message(user_message)

        while self.iteration < self.max_iterations:
            print(f"[ITERATION] Iteration {self.iteration + 1}/{self.max_iterations}")

            try:
                output = groq(messages=self.context)
                print("[LLM] LLM response received.")
            except Exception as e:
                print(f"[ERROR] Failed to call LLM: {e}")
                return f"Error occurred while calling LLM due to {e}"

            if output is None:
                print("[ERROR] LLM returned None.")
                return "Error: LLM did not return a valid response."

            if hasattr(output, "tool_calls") and output.tool_calls:
                tool_call = output.tool_calls[0]
                print(f"[TOOL] Detected tool call: {tool_call.function.name}")

                content = getattr(output, "content", "") or ""
                # reasoning = getattr(output, "reasoning", "")  # Removed unused variable

                try:
                    tool_args = json.loads(tool_call.function.arguments)
                    print(f"[TOOL] Parsed tool arguments: {tool_args}")
                except json.JSONDecodeError as e:
                    print(f"[ERROR] Failed to parse tool arguments as JSON: {e}")
                    return "Error: Invalid tool arguments format."

                try:
                    tool_output = self.tool_registry.run_tool(tool_call.function.name, **tool_args)
                    print(f"[TOOL] Tool '{tool_call.function.name}' executed successfully.")
                except Exception as e:
                    print(f"[ERROR] Tool execution failed: {e}")
                    tool_error = f"Error executing tool: {str(e)}"
                    # Add error as tool response so the model can recover
                    self.add_assistant_message(content="", tool_calls=[tool_call])
                    self.add_tool_message(tool_call, tool_error)
                    self.update_context_size()
                    self.iteration += 1
                    continue

                self.add_assistant_message(content=content, tool_calls=[tool_call])
                self.add_tool_message(tool_call, tool_output)
                self.update_context_size()
                self.iteration += 1

            else:
                print("[LLM] No tool calls detected. Returning final response.")
                final_output = getattr(output, "content", "")
                print(f"[OUTPUT] Final content: {final_output[:200]}{'...' if len(final_output) > 200 else ''}")
                self.add_assistant_message(final_output)
                self.update_context_size()
                return final_output

        print("[STOP] Max iterations reached. Terminating process.")
        return "Max iterations reached. Process terminated."

    def __del__(self):
        """Cleanup when agent is destroyed"""
        if hasattr(self, 'session_manager'):
            self.session_manager.close()

if __name__ == "__main__":
    agent = Agent()
    result = agent.run("in which file is the main agent logic defined")
    print(f"\n[FINAL RESULT] {result}")