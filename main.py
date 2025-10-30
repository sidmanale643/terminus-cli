from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from agent import Agent
import sys
import os
import json

class TerminusCLI:
    def __init__(self):
        self.console = Console()
        self.agent = Agent()
        self.context_size = (self.agent.context_size / self.agent.model_context_size) * 100
        
    def display_banner(self):
        """Display the ASCII art banner with enhanced styling"""
        banner = """
████████╗███████╗██████╗ ███╗   ███╗██╗███╗   ██╗██╗   ██╗███████╗
╚══██╔══╝██╔════╝██╔══██╗████╗ ████║██║████╗  ██║██║   ██║██╔════╝
   ██║   █████╗  ██████╔╝██╔████╔██║██║██╔██╗ ██║██║   ██║███████╗
   ██║   ██╔══╝  ██╔══██╗██║╚██╔╝██║██║██║╚██╗██║██║   ██║╚════██║
   ██║   ███████╗██║  ██║██║ ╚═╝ ██║██║██║ ╚████║╚██████╔╝███████║
   ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝
"""
        
        self.console.print(banner, style="bold bright_red on black", justify="center")
        
        from rich.table import Table

        # Create welcome header
        header = Text(justify="center")
        header.append("Welcome to ", style="white")
        header.append("TERMINUS CLI", style="bold bright_red")
        header.append("\n\nQuick Commands:\n", style="bold white")

        # Commands table (perfect alignment)
        commands = [
            ("/help", "Display help information"),
            ("/context", "View conversation context"),
            ("/history", "View session history"),
            ("/reset", "Reset session history"),
            ("/context_size", "Display context size"),
            ("/clear", "Clear console screen"),
            ("/exit", "Exit the program"),
        ]

        table = Table(show_header=False, box=None, pad_edge=False)
        table.add_column("Command", style="bright_red", no_wrap=True)
        table.add_column("Description", style="white")

        for cmd, desc in commands:
            table.add_row(cmd, desc)

        self.console.print(
            Panel(
                Group(header, table),
                border_style="bright_red on black",
                padding=(1, 2),
                expand=False
            ),
            justify="center"
        )

    
    def get_user_input(self):
        """Get user input with enhanced prompt styling"""
        prompt_text = Text()
        prompt_text.append("┌─[", style="bright_red")
        prompt_text.append("TERMINUS", style="bold bright_red")
        prompt_text.append("]", style="bright_red")
        prompt_text.append("\n└─> ", style="bright_red")
        
        return Prompt.ask(prompt_text)
    
    def display_context_bar(self):
        """Display context usage bar"""
        context_percent = (self.agent.context_size / self.agent.model_context_size) * 100
        
        # Create progress bar
        bar_width = 30
        filled = int((context_percent / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # Color based on usage
        if context_percent < 50:
            color = "green"
        elif context_percent < 80:
            color = "yellow"
        else:
            color = "red"
        
        context_text = Text()
        context_text.append("Context: [", style="dim white")
        context_text.append(bar, style=color)
        context_text.append(f"] {context_percent:.1f}%", style="dim white")
        
        self.console.print(context_text, justify="right")
    
    def process_query(self, user_input: str):
        """Process user query and display response"""
        try:
            from rich.live import Live
            
            # Show loading status with dynamic updates
            streaming_content = []
            live_display = None
            
            with self.console.status(
                status="[bold bright_red]Processing your request...",
                spinner="dots12",
                spinner_style="bright_red"
            ) as status:
                # Define callback to update status message and display it
                def update_status(message: str, is_thinking: bool = False):
                    nonlocal live_display
                    
                    # Stop live display if active
                    if live_display is not None:
                        live_display.stop()
                        live_display = None
                    
                    status.update(f"[bold bright_red]{message}...")
                    # Stop status temporarily to print the message
                    status.stop()
                    if is_thinking:
                        # Display thinking message with different styling
                        self.console.print(f"  [dim #F4AF2D][/] [italic #F4AF2D]{message}[/]")
                    else:
                        # Display tool message
                        self.console.print(f"  [dim bright_yellow]→[/] [bright_yellow]{message}[/]")
                    status.start()
                
                # Define callback to handle streaming content
                def handle_streaming(content_chunk: str):
                    nonlocal live_display, streaming_content
                    
                    streaming_content.append(content_chunk)
                    accumulated = "".join(streaming_content)
                    
                    # Stop the status spinner when streaming starts
                    if live_display is None:
                        status.stop()
                        live_display = Live(
                            Panel(
                                Markdown(accumulated),
                                title="[bold bright_red on black]Response[/bold bright_red on black]",
                                border_style="bright_red on black",
                                padding=(1, 2)
                            ),
                            console=self.console,
                            refresh_per_second=10
                        )
                        live_display.start()
                    else:
                        # Update live display with accumulated content
                        live_display.update(
                            Panel(
                                Markdown(accumulated),
                                title="[bold bright_red on black]Response[/bold bright_red on black]",
                                border_style="bright_red on black",
                                padding=(1, 2)
                            )
                        )
                
                response = self.agent.run(
                    user_input, 
                    status_callback=update_status,
                    streaming_callback=handle_streaming
                )
                
                # Stop live display if it's still running
                if live_display is not None:
                    live_display.stop()
            
            # If no streaming occurred, display the full response
            if not streaming_content:
                md = Markdown(response)
                self.console.print(
                    Panel(
                        md,
                        title="[bold bright_red on black]Response[/bold bright_red on black]",
                        border_style="bright_red on black",
                        padding=(1, 2)
                    )
                )
            
            # Display footer with CWD on left, model and context on right
            model = self.agent.model
            context_percent = (self.agent.context_size / self.agent.model_context_size) * 100
            
            # Create progress bar
            bar_width = 25
            filled = int((context_percent / 100) * bar_width)
            bar = "█" * filled + "░" * (bar_width - filled)
            
            # Color based on usage
            if context_percent < 50:
                color = "bright_green"
            elif context_percent < 80:
                color = "bright_yellow"
            else:
                color = "bright_red"
            
            # Left side - CWD
            left_text = Text()
            left_text.append(os.getcwd(), style="bright_cyan")
            
            # Right side - Model and Context
            right_text = Text()
            right_text.append(model, style="bright_magenta")
            right_text.append(" | ", style="dim white")
            right_text.append("Context: ", style="bold blue")
            right_text.append("[", style="dim white")
            right_text.append(bar, style=color)
            right_text.append("] ", style="dim white")
            right_text.append(f"{context_percent:.1f}%", style=color)
            
            # Create a combined layout
            console_width = self.console.width
            right_text_len = len(right_text.plain)
            padding = " " * max(0, console_width - len(left_text.plain) - right_text_len)
            
            combined = Text.assemble(left_text, padding, right_text)
            self.console.print(combined)
            
        except KeyboardInterrupt:
            self.console.print("\n[bold bright_red]Operation cancelled by user[/bold bright_red]")
            raise
        except Exception as e:
            self.console.print(
                Panel(
                    f"[bold bright_red]Error:[/bold bright_red]\n[white]{str(e)}[/white]",
                    title="[bold red on black]ERROR[/bold red on black]",
                    border_style="red on black",
                    padding=(1, 2)
                )
            )
    
    def run_interactive(self):
        """Run interactive mode with conversation loop"""
        self.display_banner()
        
        try:
            while True:
                user_input = self.get_user_input()
                
                # Handle commands
                if user_input.lower() in ['exit', 'quit', '/exit', '/quit', 'q']:
                    goodbye_text = Text()
                    goodbye_text.append("Shutting down TERMINUS...", style="bold white")
                    self.console.print(goodbye_text, justify="center")
                    break
                    
                if user_input.lower() in ['/reset']:
                    self.agent.clear_session()
                    self.console.print("[bright_yellow]✓[/] Session reset successfully", style="dim")
                    continue
                
                if user_input.lower() in ['/clear', 'clear']:
                    self.console.clear()
                    self.display_banner()
                    continue
                
                if user_input.lower() in ['/context_size']:
                    self.console.print(f"Context Size: {self.agent.context_size}")
                    continue

                if user_input.lower() in ['/history']:
                    # Display session history
                    history = self.agent.get_session_history(limit=5)
                    if history:
                        history_lines = []
                        for idx, msg in enumerate(history, 1):
                            # Parse JSON content
                            try:
                                msg_data = json.loads(msg['content'])
                                role = msg_data.get('role', 'unknown')
                                content = msg_data.get('content', '')
                                
                                # Truncate long messages
                                if len(content) > 150:
                                    display_content = content[:150] + "..."
                                else:
                                    display_content = content
                                
                                # Format with colors
                                color = self._get_role_color(role)
                                line = f"{idx}. [bold {color}]{role.upper()}:[/] {display_content}"
                                history_lines.append(line)
                                
                            except json.JSONDecodeError:
                                # Fallback for non-JSON messages
                                role = msg['role']
                                content = msg['content'][:150]
                                color = self._get_role_color(role)
                                line = f"{idx}. [bold {color}]{role.upper()}:[/] {content}"
                                history_lines.append(line)
                        
                        self.console.print(
                            Panel(
                                "\n\n".join(history_lines),
                                title="[bold bright_red on black]Session History (last 10 messages)[/bold bright_red on black]",
                                border_style="bright_red on black",
                                padding=(1, 2)
                            )
                        )
                    else:
                        self.console.print("[yellow]No session history available.[/yellow]")
                    continue

                if user_input.lower() in ['/help', '/context', '/clear', '/exit']:
                    self.console.print(self.slash_commands(user_input))
                    continue
                

                if not user_input.strip():
                    continue
                
                self.process_query(user_input)
                self.console.print()  
                
        except KeyboardInterrupt:
            self.console.print("\n[bright_red]Exiting TERMINUS...[/bright_red]")
            sys.exit(0)
    
    def run_single_query(self, query: str):
        """Run a single query (useful for non-interactive mode)"""
        self.display_banner()
        self.process_query(query)

    def _get_role_color(self, role: str) -> str:
        """Get color for different message roles"""
        role_colors = {
            "system": "cyan",
            "user": "green",
            "assistant": "magenta",
            "tool": "yellow"
        }
        return role_colors.get(role.lower(), "white")

    def slash_commands(self, command: str):
        if command == "/help":
            help_text = Text()
            help_text.append("TERMINUS CLI\n\n", style="bold bright_red")
            
            help_text.append("Available Commands:\n\n", style="bold white")
            
            help_text.append("  /help         ", style="bright_red")
            help_text.append(" - Display this help information\n", style="white")
            help_text.append("  /context      ", style="bright_red")
            help_text.append(" - View current conversation context\n", style="white")
            help_text.append("  /history      ", style="bright_red")
            help_text.append(" - View recent session history (last 10 messages)\n", style="white")
            help_text.append("  /reset        ", style="bright_red")
            help_text.append(" - Reset session history\n", style="white")
            help_text.append("  /context_size ", style="bright_red")
            help_text.append(" - Display context size\n", style="white")
            help_text.append("  /clear        ", style="bright_red")
            help_text.append(" - Clear the console screen\n", style="white")
            help_text.append("  /exit         ", style="bright_red")
            help_text.append(" - Exit the program (also: exit, quit, q)\n\n", style="white")
            
            help_text.append("Usage:\n\n", style="bold white")
            help_text.append("  Simply type your query or question and press Enter.\n", style="white")
            help_text.append("  The AI assistant will process your request and provide a response.\n\n", style="white")
            
            help_text.append("Tips:\n\n", style="bold white")
            help_text.append("  • Use ", style="white")
            help_text.append("Ctrl+C", style="bright_yellow")
            help_text.append(" to cancel a running operation\n", style="white")
            help_text.append("  • Context usage is displayed after each response\n", style="white")
            help_text.append("  • The assistant can help with coding, debugging, and development tasks\n", style="white")
            
            return Panel(
                help_text,
                title="[bold bright_red on black]═══ HELP ═══[/bold bright_red on black]",
                border_style="bright_red on black",
                padding=(1, 2)
            )
        elif command == "/context":
            return self.agent.context
        elif command == "/clear":
            return "Clear"
        elif command == "/exit":
            return "Exit"
        else:
            return "Invalid command"


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