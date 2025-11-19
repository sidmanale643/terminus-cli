from src.agent import Agent
from ui.frontend import TerminalDisplay
from src.utils import process_file_references
import sys
import os
import json
from src.models.llm import available_models



class TerminusCLI:

    def __init__(self, cwd=None):

        if cwd:
            os.chdir(cwd)
        
        self.agent = Agent(cwd=cwd)
        self.display = TerminalDisplay()
    
    def display_available_models(self):
        self.display.render_table()

    # add at top of file (already imported earlier in your snippet)

    # helper to resolve a model by index or name (case-insensitive)
    def resolve_model(self, spec: str):
        """
        spec: either an integer index (1-based) or a substring/name of model.name/provider.
        Returns model instance or raises ValueError.
        """
        spec = spec.strip()
        # try index (1-based)
        if spec.isdigit():
            idx = int(spec) - 1
            if 0 <= idx < len(available_models):
                m = available_models[idx]
                return m() if isinstance(m, type) else m
            raise ValueError(f"Model index {spec} out of range (1..{len(available_models)})")

        # try exact name match (case-insensitive)
        lowered = spec.lower()
        matches = []
        for m in available_models:
            inst = m() if isinstance(m, type) else m
            if inst.name.lower() == lowered or inst.provider.lower() == lowered:
                return inst
            # partial match
            if lowered in inst.name.lower() or lowered in inst.provider.lower():
                matches.append(inst)

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join([f"{i+1}:{x.name}" for i,x in enumerate(matches)])
            raise ValueError(f"Multiple models match '{spec}': {names}")

        raise ValueError(f"No model found matching '{spec}'")

    # update TerminusCLI.switch_model signature (optional but clearer)
    def switch_model(self, model_spec: str):
        """
        model_spec: model name, provider, or 1-based index (string)
        """
        try:
            model_inst = self.resolve_model(model_spec)
            # call agent API (assumes agent.switch_model accepts an instance — adjust if it expects a name)
            self.agent.switch_model(model_inst)
            self.display.print_message(f"[green]Switched model to[/green] [bold]{model_inst.name}[/bold]")
        except Exception as e:
            self.display.print_message(f"[red]Failed to switch model:[/] {e}")

    
    def process_query(self, user_input: str):
        """Process user query and coordinate with agent and display"""
        try:
            # Process @ file references
            enriched_message, loaded_files, errors = process_file_references(user_input)
            
            # Display loaded files
            if loaded_files:
                files_list = ", ".join([f"[cyan]{f}[/cyan]" for f in loaded_files])
                self.display.print_message(f"[dim bright_yellow]Loaded files: {files_list}")
            
            # Display errors if any
            if errors:
                for error in errors:
                    self.display.print_message(f"[dim bright_red]Warning: {error}")
            
            # Create streaming handler
            handler = self.display.create_streaming_handler()
            
            with handler:
                # Run agent with streaming callbacks (use enriched message)
                # Pass handler to todo_display_callback via lambda
                response = self.agent.run(
                    enriched_message, 
                    status_callback=handler.update_status,
                    streaming_callback=handler.handle_streaming,
                    todo_display_callback=lambda todos: self.display.render_todo_panel(todos, handler=handler)
                )
            
            # Render final response after live display stops to keep content visible
            handler.render_final_response(response)
            
            # Display request cost if available
            if self.agent.last_request_cost is not None:
                cost_str = f"${self.agent.last_request_cost:.6f}"
                self.display.print_message(f"[dim bright_green]Request cost: {cost_str}[/dim bright_green]")
            
            # Display footer with context info
            self.display.render_footer(
                cwd=os.getcwd(),
                model=self.agent.model,
                context_size=self.agent.context_size,
                model_context_size=self.agent.model_context_size
            )
            
        except KeyboardInterrupt:
            self.display.print_message("\n[bold bright_red]Operation cancelled by user[/bold bright_red]")
            raise
        except Exception as e:
            self.display.render_error(str(e))
    
    def execute_command(self, command: str) -> bool:
        """Execute a slash command. Returns True if should continue loop, False if should exit"""
        
        # Exit commands
        if command.lower() in ['exit', 'quit', '/exit', '/quit', 'q']:
            self.display.print_centered("Shutting down TERMINUS...", style="bold white")
            return False
        
        # Reset session
        if command.lower() == '/reset':
            self.agent.clear_session()
            self.display.render_success_message("Session reset successfully")
            return True
        
        # Clear screen
        if command.lower() in ['/clear', 'clear']:
            self.display.clear_screen()
            self.display.render_banner()
            return True
        
        # Display context size
        if command.lower() == '/context_size':
            self.display.print_message(f"Context Size: {self.agent.context_size}")
            return True
        
        if command.lower() == '/list_models':
            self.display_available_models()
            return True

          # replace the /switch branch inside execute_command with this:
        import re

        if command.lower().startswith('/switch'):
            parts = command.split(maxsplit=1)

            # prefer normalized list if present
            models = getattr(self, "available_models", available_models)

            # immediate switch if an argument is provided with the command
            if len(parts) == 2:
                model_spec = parts[1]
                self.switch_model(model_spec)
                return True

            # no arg supplied — show usage and prompt inline
            self.display.print_message("[yellow]Usage:[/] /switch <model-name-or-index>")
            for i, m in enumerate(models, start=1):
                inst = m() if isinstance(m, type) else m
                self.display.print_message(f"  {i}. {inst.name} ({inst.provider})")

            try:
                self.display.print_message("[dim]Type the number or name of the model to switch, or press Enter to cancel.[/dim]")
                # IMPORTANT: call get_user_input() without 'prompt' keyword (your implementation doesn't accept it)
                selection = self.display.get_user_input().strip()

                # cancel if empty
                if not selection:
                    self.display.print_message("[dim]Switch cancelled.[/dim]")
                    return True

                # sanitize stray symbols but keep model-relevant chars like / : . _ -
                selection_clean = re.sub(r"[^0-9A-Za-z/_\:\.\-]", "", selection).strip()

                # if number -> index (1-based)
                if selection_clean.isdigit():
                    idx = int(selection_clean) - 1
                    if 0 <= idx < len(models):
                        m = models[idx]
                        inst = m() if isinstance(m, type) else m
                        self.agent.switch_model(inst)
                        self.display.print_message(f"[green]Switched model to[/green] [bold]{inst.name}[/bold]")
                        return True
                    else:
                        self.display.print_message(f"[red]Index {selection} out of range.[/red]")
                        return True

                # else try name/provider matches (case-insensitive, partial)
                sel_lower = selection_clean.lower()
                matches = []
                for m in models:
                    inst = m() if isinstance(m, type) else m
                    if inst.name.lower() == sel_lower or inst.provider.lower() == sel_lower:
                        matches = [inst]
                        break
                    if sel_lower in inst.name.lower() or sel_lower in inst.provider.lower():
                        matches.append(inst)

                if len(matches) == 1:
                    chosen = matches[0]
                    self.agent.switch_model(chosen)
                    self.display.print_message(f"[green]Switched model to[/green] [bold]{chosen.name}[/bold]")
                    return True
                elif len(matches) > 1:
                    self.display.print_message("[yellow]Multiple matches found:[/yellow]")
                    for i, inst in enumerate(matches, start=1):
                        self.display.print_message(f"  {i}. {inst.name} ({inst.provider})")
                    self.display.print_message("[dim]Try a more specific name or use the index.[/dim]")
                    return True
                else:
                    self.display.print_message(f"[red]No models matched '{selection}'.[/red]")
                    return True

            except KeyboardInterrupt:
                self.display.print_message("\n[bright_red]Switch cancelled by user[/bright_red]")
                return True
            except Exception as e:
                self.display.print_message(f"[red]Error while switching model:[/] {e}")
                return True

                # Display history
        if command.lower() == '/history':
            self._display_history()
            return True
                
                # Display help
        if command.lower() == '/help':
            self.display.render_help()
            return True
                
                # Display context
        if command.lower() == '/context':
            self.display.print_message(str(self.agent.context))
            return True
        
        if command.lower() == '/model':
            self.display.print_message(f"Current Model: {self.agent.model}")
            return True
                
        return True
    
    def _display_history(self):
        """Display session history"""
        history = self.agent.get_session_history(limit=5)
        
        if not history:
            self.display.print_message("[yellow]No session history available.[/yellow]")
            return
        
        history_lines = []
        for idx, msg in enumerate(history, 1):
            try:
                # Parse JSON content
                msg_data = json.loads(msg['content'])
                role = msg_data.get('role', 'unknown')
                content = msg_data.get('content', '')
                
                # Truncate long messages
                if len(content) > 150:
                    display_content = content[:150] + "..."
                else:
                    display_content = content
                
                # Format with colors
                color = self.display.get_role_color(role)
                line = f"{idx}. [bold {color}]{role.upper()}:[/] {display_content}"
                history_lines.append(line)
                
            except json.JSONDecodeError:
                # Fallback for non-JSON messages
                role = msg['role']
                content = msg['content'][:150]
                color = self.display.get_role_color(role)
                line = f"{idx}. [bold {color}]{role.upper()}:[/] {content}"
                history_lines.append(line)
        
        self.display.render_history(history_lines)
    
    def run_interactive(self):
        """Run interactive mode with conversation loop"""
        self.display.render_banner()
        
        try:
            while True:
                user_input = self.display.get_user_input()
                
                # Handle empty input
                if not user_input.strip():
                    continue
                
                # Check if it's a command (but not /plan which should be processed as a query)
                if (user_input.startswith('/') and not user_input.startswith('/plan')) or user_input.lower() in ['exit', 'quit', 'q', 'clear']:
                    should_continue = self.execute_command(user_input)
                    if not should_continue:
                        break
                    continue
                
                # Process as query
                self.process_query(user_input)
                self.display.print_newline()
                
        except KeyboardInterrupt:
            self.display.print_message("\n[bright_red]Exiting TERMINUS...[/bright_red]")
            sys.exit(0)
    
    def run_single_query(self, query: str):
        """Run a single query (useful for non-interactive mode)"""
        self.display.render_banner()
        self.process_query(query)


def main():
    """Main entry point for 'terminus' command"""
    # Always use the current working directory where the command is invoked
    invoked_dir = os.getcwd()
    cli = TerminusCLI(cwd=invoked_dir)
    
    # Check if a query was passed as command line argument
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        cli.run_single_query(query)
    else:
        cli.run_interactive()


if __name__ == "__main__":
    main()