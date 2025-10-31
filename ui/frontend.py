from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.live import Live
from rich.table import Table


class TerminalDisplay:
    """Handles all UI rendering and display logic"""
    
    def __init__(self):
        self.console = Console()
    
    def render_banner(self):
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
        
        # Create welcome header
        header = Text(justify="center")
        header.append("Welcome to ", style="white")
        header.append("TERMINUS CLI", style="bold bright_red")
        header.append("\n\nQuick Commands:\n", style="bold white")

        # Commands table
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
    
    def create_progress_bar(self, context_percent: float, bar_width: int = 25):
        """Create a colored progress bar based on context usage"""
        filled = int((context_percent / 100) * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # Color based on usage
        if context_percent < 50:
            color = "bright_green"
        elif context_percent < 80:
            color = "bright_yellow"
        else:
            color = "bright_red"
        
        return bar, color
    
    def render_footer(self, cwd: str, model: str, context_size: int, model_context_size: int):
        """Render the footer with CWD, model info, and context bar"""
        context_percent = (context_size / model_context_size) * 100
        bar, color = self.create_progress_bar(context_percent, bar_width=25)
        
        # Left side - CWD
        left_text = Text()
        left_text.append(cwd, style="bright_cyan")
        
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
    
    def render_response(self, content: str):
        """Render a response in a styled panel"""
        md = Markdown(content)
        self.console.print(
            Panel(
                md,
                title="[bold bright_red on black]Response[/bold bright_red on black]",
                border_style="bright_red on black",
                padding=(1, 2)
            )
        )
    
    def render_error(self, error_message: str):
        """Render an error message"""
        self.console.print(
            Panel(
                f"[bold bright_red]Error:[/bold bright_red]\n[white]{error_message}[/white]",
                title="[bold red on black]ERROR[/bold red on black]",
                border_style="red on black",
                padding=(1, 2)
            )
        )
    
    def render_success_message(self, message: str):
        """Render a success message"""
        self.console.print(f"[bright_yellow]✓[/] {message}", style="dim")
    
    def render_history(self, history_lines: list):
        """Render session history"""
        self.console.print(
            Panel(
                "\n\n".join(history_lines),
                title="[bold bright_red on black]Session History (last 10 messages)[/bold bright_red on black]",
                border_style="bright_red on black",
                padding=(1, 2)
            )
        )
    
    def render_help(self):
        """Render help panel"""
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
        
        self.console.print(
            Panel(
                help_text,
                title="[bold bright_red on black]═══ HELP ═══[/bold bright_red on black]",
                border_style="bright_red on black",
                padding=(1, 2)
            )
        )
    
    def clear_screen(self):
        """Clear the console"""
        self.console.clear()
    
    def print_message(self, message: str, style: str = ""):
        """Print a simple message"""
        self.console.print(message, style=style)
    
    def print_centered(self, message: str, style: str = ""):
        """Print a centered message"""
        self.console.print(message, style=style, justify="center")
    
    def print_newline(self):
        """Print a newline"""
        self.console.print()
    
    def get_role_color(self, role: str) -> str:
        """Get color for different message roles"""
        role_colors = {
            "system": "cyan",
            "user": "green",
            "assistant": "magenta",
            "tool": "yellow"
        }
        return role_colors.get(role.lower(), "white")
    
    def create_streaming_handler(self):
        """Create a streaming response handler with callbacks"""
        return StreamingHandler(self.console)


class StreamingHandler:
    """Manages streaming response display with status updates"""
    
    def __init__(self, console: Console):
        self.console = console
        self.streaming_content = []
        self.live_display = None
        self.thinking_started = False
        self.status = None
    
    def start(self):
        """Start the status spinner"""
        self.status = self.console.status(
            status="[bold bright_red]Processing your request...",
            spinner="dots12",
            spinner_style="bright_red"
        )
        self.status.__enter__()
        return self
    
    def stop(self):
        """Stop the streaming handler"""
        if self.live_display is not None:
            self.live_display.stop()
            self.live_display = None
        if self.status is not None:
            self.status.__exit__(None, None, None)
            self.status = None
    
    def __enter__(self):
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    def update_status(self, message: str, is_thinking: bool = False):
        """Callback to update status message"""
        # Stop live display if active
        if self.live_display is not None:
            self.live_display.stop()
            self.live_display = None
        
        if is_thinking:
            # Only display thinking if there's actual content (not empty or whitespace)
            if message and message.strip():
                # Display thinking header only once
                if not self.thinking_started:
                    self.status.stop()
                    self.console.print("\n  [dim #F4AF2D][/] [bold #FF6C00]Thinking[/] ", end="")
                    self.thinking_started = True
                # Display thinking message token by token in tron orange
                text = Text(message, style="#FF6C00")
                self.console.print(text, end="")
        else:
            # End thinking line if it was active
            if self.thinking_started:
                self.console.print()  # New line
                self.thinking_started = False
            
            self.status.update(f"[bold bright_red]{message}...")
            # Stop status temporarily to print the message
            self.status.stop()
            # Display tool message
            self.console.print(f"  [dim bright_yellow]→[/] [bright_yellow]{message}[/]")
            self.status.start()
    
    def handle_streaming(self, content_chunk: str):
        """Callback to handle streaming content"""
        self.streaming_content.append(content_chunk)
        accumulated = "".join(self.streaming_content)
        
        # Stop the status spinner when streaming starts
        if self.live_display is None:
            self.status.stop()
            self.live_display = Live(
                Panel(
                    Markdown(accumulated),
                    title="[bold bright_red on black]Response[/bold bright_red on black]",
                    border_style="bright_red on black",
                    padding=(1, 2)
                ),
                console=self.console,
                refresh_per_second=10
            )
            self.live_display.start()
        else:
            # Update live display with accumulated content
            self.live_display.update(
                Panel(
                    Markdown(accumulated),
                    title="[bold bright_red on black]Response[/bold bright_red on black]",
                    border_style="bright_red on black",
                    padding=(1, 2)
                )
            )
    
    def has_streamed_content(self):
        """Check if any content was streamed"""
        return bool(self.streaming_content)
    
    def render_final_response(self, response: str):
        """Render the final response panel only if no streaming occurred"""
        # Only render if no streaming occurred, otherwise Live display already showed it
        if not self.has_streamed_content():
            md = Markdown(response)
            self.console.print(
                Panel(
                    md,
                    title="[bold bright_red on black]Response[/bold bright_red on black]",
                    border_style="bright_red on black",
                    padding=(1, 2)
                )
            )
