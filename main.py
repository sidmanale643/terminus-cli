from agent import Agent
from ui.frontend import TerminalDisplay
import sys
import os
import json

class TerminusCLI:
    """Main CLI application - handles business logic and orchestration"""
    
    def __init__(self):
        self.agent = Agent()
        self.display = TerminalDisplay()
        
    def process_query(self, user_input: str):
        """Process user query and coordinate with agent and display"""
        try:
            # Create streaming handler
            handler = self.display.create_streaming_handler()
            
            with handler:
                # Run agent with streaming callbacks
                response = self.agent.run(
                    user_input, 
                    status_callback=handler.update_status,
                    streaming_callback=handler.handle_streaming
                )
            
            # Render final response after live display stops to keep content visible
            handler.render_final_response(response)
            
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
                
                # Check if it's a command
                if user_input.startswith('/') or user_input.lower() in ['exit', 'quit', 'q', 'clear']:
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
    """Main entry point"""
    cli = TerminusCLI()
    
    # Check if a query was passed as command line argument
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        cli.run_single_query(query)
    else:
        cli.run_interactive()


if __name__ == "__main__":
    main()
