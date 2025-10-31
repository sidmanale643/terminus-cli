from tools.tool_registry import ToolRegistry
import json
from prompts import PromptManager
from dotenv import load_dotenv
from session_manager import SessionHistory
from llm_service.service import LLMService
from constants import DEFAULT_PROVIDER, DEFAULT_MODEL

load_dotenv()

MAX_ITERATIONS = 50

class Agent:
    def __init__(self):
        # print("[INIT] Initializing Agent...")

        self.name = "terminus-cli"
        self.description = ""
        self.context = []
        self.context_size = 0
        self.model_context_size = 128000
        self.iteration = 0
        self.max_iterations = MAX_ITERATIONS
        self.prompt_manager = PromptManager()
        self.system_prompt = self.prompt_manager.get_system_prompt()
        
        # Initialize LLM Service
        self.llm_service = LLMService()
        self.llm_service.set_active_provider(DEFAULT_PROVIDER)
        
        self.tool_registry = ToolRegistry()
        self.model = DEFAULT_MODEL
        
        self.session_manager = SessionHistory()
        # print("[INIT] Session manager initialized.")

        # print("[INIT] Agent initialized successfully.")
    
    def reset(self):
        self.context = []
        self.session_manager.clear_session_history()
        self.add_system_message()

    def add_system_message(self):
        message = {"role": "system", "content": self.system_prompt}
        self.context.append(message)
        self.session_manager.insert_to_session_history("system", json.dumps(message))
    
    def add_user_message(self, content):
        message = {"role": "user", "content": content}
        self.context.append(message)
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
        self.session_manager.insert_to_session_history("assistant", json.dumps(message))

    def add_tool_message(self, tool_call, tool_output):
        message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.function.name,
            "content": tool_output
        }
        self.context.append(message)
        self.session_manager.insert_to_session_history("tool", json.dumps(message))
    
    def update_context_size(self):
        self.message_context_size = [len(message["content"]) for message in self.context]
        self.context_size = sum(self.message_context_size)
        # print(f"[CONTEXT] Updated context size: {self.context_size}")

    def get_session_history(self, limit=None):
        return self.session_manager.retrieve_session_history(limit)
    
    def get_chat_history(self, name=None, chat_id=None, limit=None):
        return self.session_manager.retrieve_chat_history(name, chat_id, limit)
    
    def save_session(self, name):
        session_messages = self.session_manager.retrieve_session_history()
        parsed_messages = []
        for msg in session_messages:
            try:
                parsed_messages.append(json.loads(msg["content"]))
            except json.JSONDecodeError:
                parsed_messages.append({"role": msg["role"], "content": msg["content"]})
        
        return self.session_manager.insert_to_chat_history(name, parsed_messages)
    
    def clear_session(self):
        self.session_manager.clear_session_history()
        self.context = []
        self.iteration = 0
        self.add_system_message()
    
    def load_session(self, name):
        chat_history = self.session_manager.retrieve_chat_history(name=name, limit=1)
        if chat_history:
            self.clear_session()
            for message in chat_history[0]["chat_history"]:
                self.context.append(message)
                self.session_manager.insert_to_session_history(message["role"], json.dumps(message))
            # print(f"[SESSION] Loaded session '{name}' with {len(self.context)} messages.")
            return True
        # print(f"[SESSION] No session found with name '{name}'.")
        return False

    def display_tool(self, tool_name: str, tool_args: dict = None):
        """Generate a descriptive message for tool usage with specific arguments"""
        
        if tool_args is None:
            tool_args = {}
        
        # Generate specific messages based on tool and arguments
        if tool_name == "file_reader" and "file_path" in tool_args:
            filename = tool_args["file_path"].split('/')[-1]
            return f"reading {filename}"
        
        elif tool_name == "file_creator" and "file_path" in tool_args:
            filename = tool_args["file_path"].split('/')[-1]
            return f"creating {filename}"
        
        elif tool_name == "file_editor" and "file_path" in tool_args:
            filename = tool_args["file_path"].split('/')[-1]
            return f"editing {filename}"
        
        elif tool_name == "multiple_file_reader" and "file_paths" in tool_args:
            count = len(tool_args["file_paths"])
            return f"reading {count} file{'s' if count > 1 else ''}"
        
        elif tool_name == "grep_search" and "pattern" in tool_args:
            pattern = tool_args["pattern"][:30]  # Truncate long patterns
            return f"searching for '{pattern}'"
        
        elif tool_name == "command_executor" and "command" in tool_args:
            cmd = tool_args["command"].split()[0]  # Get first word of command
            return f"executing {cmd}"
        
        elif tool_name == "ls" and "directory" in tool_args:
            dir_name = tool_args["directory"].split('/')[-1] or "root"
            return f"listing {dir_name}"
        
        elif tool_name == "web_search" and "query" in tool_args:
            query = tool_args["query"][:30]  # Truncate long queries
            return f"searching web for '{query}'"
        
        # Fallback to generic messages
        tool_message = {
            "grep_search": "searching",
            "file_reader": "reading",
            "command_executor": "executing",
            "todo": "managing todos",
            "file_creator": "creating file",
            "file_editor": "editing file",
            "multiple_file_reader": "reading files",
            "ls": "listing directory",
            "sub_agent": "delegating to sub-agent",
            "lint": "linting code",
            "web_search": "searching the web",
        }
        
        return tool_message.get(tool_name, "calling tool")

    def run(self, user_message, status_callback=None, streaming_callback=None):
        """
        Run the agent with a user message
        
        Args:
            user_message: The user's input message
            status_callback: Optional callback function to update status (e.g., status_callback("reading file.txt"))
            streaming_callback: Optional callback function to receive streaming content chunks
        """
        # print(f"[RUN] Starting agent run with user message: '{user_message}'")

        if not self.context:
            self.add_system_message()
            # print("[INIT] System prompt added to context.")

        self.add_user_message(user_message)

        while self.iteration < self.max_iterations:
            # print(f"[ITERATION] Iteration {self.iteration + 1}/{self.max_iterations}")

            try:
                # Get tool schemas for LLM
                tool_schemas = self.tool_registry.tool_schemas
                
                # Stream response from LLM
                accumulated_content = ""
                accumulated_reasoning = ""
                final_tool_calls = None
                
                for chunk in self.llm_service.stream(
                    messages=self.context,
                    tools=tool_schemas,
                    tool_choice="auto",
                    model_name=self.model,
                    temperature=0.3
                ):
                    if chunk.reasoning:
                        accumulated_reasoning += chunk.reasoning
                        
                        # Only call callback if there's actual content (not just whitespace)
                        if status_callback and chunk.reasoning.strip():
                            status_callback(chunk.reasoning, is_thinking=True)
                    
                    # Accumulate content
                    if chunk.content:
                        accumulated_content += chunk.content
       
                        if streaming_callback:
                            streaming_callback(chunk.content)
                    
           
                    # Capture tool calls (usually come in final chunk)
                    if chunk.tool_calls:
                        final_tool_calls = chunk.tool_calls

                # print("[LLM] LLM response received.")
            except Exception as e:
                # print(f"[ERROR] Failed to call LLM: {e}")
                return f"Error occurred while calling LLM due to {e}"

            # Check if we have tool calls
            if final_tool_calls and len(final_tool_calls) > 0:
                tool_call = final_tool_calls[0]
                # print(f"[TOOL] Detected tool call: {tool_call.function.name}")

                try:
                    tool_args = json.loads(tool_call.function.arguments)
                    # print(f"[TOOL] Parsed tool arguments: {tool_args}")
                except json.JSONDecodeError:
                    # print("[ERROR] Failed to parse tool arguments as JSON")
                    return "Error: Invalid tool arguments format."

                # Update status with specific tool message
                if status_callback:
                    status_message = self.display_tool(tool_call.function.name, tool_args)
                    status_callback(status_message, is_thinking=False)

                try:
                    tool_output = self.tool_registry.run_tool(tool_call.function.name, **tool_args)
                    # print(f"[TOOL] Tool '{tool_call.function.name}' executed successfully.")
                except Exception as e:
                    # print(f"[ERROR] Tool execution failed: {e}")
                    tool_error = f"Error executing tool: {str(e)}"
                    self.add_assistant_message(content=accumulated_content, tool_calls=[tool_call])
                    self.add_tool_message(tool_call, tool_error)
                    self.update_context_size()
                    self.iteration += 1
                    continue

                self.add_assistant_message(content=accumulated_content, tool_calls=[tool_call])
                self.add_tool_message(tool_call, tool_output)
                self.update_context_size()
                self.iteration += 1

            else:
                # print("[LLM] No tool calls detected. Returning final response.")
                # print(f"[OUTPUT] Final content: {accumulated_content[:200]}{'...' if len(accumulated_content) > 200 else ''}")
                self.add_assistant_message(accumulated_content)
                self.update_context_size()
                return accumulated_content

        # print("[STOP] Max iterations reached. Terminating process.")
        return "Max iterations reached. Process terminated."

    def __del__(self):
        if hasattr(self, 'session_manager'):
            self.session_manager.close()

if __name__ == "__main__":
    agent = Agent()
    result = agent.run("in which file is the main agent logic defined")
    #print(f"\n[FINAL RESULT] {result}")