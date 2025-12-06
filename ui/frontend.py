from src.models.llm import available_models
from rich.console import Console, Group
from rich import box
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.formatted_text import FormattedText
from ui.completer import TerminusCompleter
from rich.align import Align

class TerminalDisplay:
    """Handles all UI rendering and display logic"""
    
    def __init__(self):
        self.console = Console()
        self.colors = {
            "accent": "#8B5CF6",
            "accent_alt": "#22D3EE",
            "muted": "#9CA3AF",
            "success": "#34D399",
            "warning": "#F59E0B",
            "danger": "#F43F5E",
        }
        
        # Initialize prompt_toolkit session with completer
        self.completer = TerminusCompleter()
        
        # Define prompt style for prompt_toolkit
        self.prompt_style = PTStyle.from_dict({
            'prompt': f"{self.colors['accent']} bold",
            'brackets': self.colors['accent_alt'],
            'path': self.colors['muted'],
        })
        
        self.prompt_session = PromptSession(
            completer=self.completer,
            style=self.prompt_style,
            complete_while_typing=True,
            enable_history_search=True,
        )
    
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
        
        banner_text = Text(banner, style=f"bold {self.colors['accent']}")
        
        # Create welcome header
        header = Text(justify="center")
        header.append("Welcome to ", style=f"bold {self.colors['muted']}")
        header.append("TERMINUS CLI", style=f"bold {self.colors['accent']}")
        header.append("\n", style=self.colors["muted"])
        header.append("Calmer terminal UI for focused building.\n", style=f"dim {self.colors['muted']}")
        header.append("\nQuick Commands\n", style=f"bold {self.colors['accent_alt']}")

        # Commands table
        commands = [
            ("/help", "Display help information"),
            ("/plan <task>", "Create detailed implementation plan"),
            ("/context", "View conversation context"),
            ("/history", "View session history"),
            ("/reset", "Reset session history"),
            ("/context_size", "Display context size"),
            ("/clear", "Clear console screen"),
            ("/switch <model>", "Switch to a different AI model"),
            ("/list_models", "List available models"),
            ("/model", "Show current model"),
            ("/exit", "Exit the program"),
        ]

        table = Table(
            show_header=False,
            box=box.SIMPLE_HEAD,
            pad_edge=False,
            expand=False,
            padding=(0, 1),
        )
        table.add_column("Command", style=self.colors["accent"], no_wrap=True)
        table.add_column("Description", style="white")
        table.row_styles = [f"dim {self.colors['muted']}", "white"]

        for cmd, desc in commands:
            table.add_row(cmd, desc)

        self.console.print(
            Panel(
                Group(Align.center(banner_text), header, table),
                border_style=self.colors["accent"],
                padding=(1, 2),
                expand=False,
                subtitle="[dim]Type @ then Tab for file suggestions",
                subtitle_align="right",
            ),
            justify="center"
        )
    
    def get_user_input(self):
        """Get user input with enhanced prompt styling and autocomplete"""
        prompt_text = Text()
        prompt_text.append("╭─ ", style=self.colors["accent"])
        prompt_text.append("TERMINUS", style=f"bold {self.colors['accent_alt']}")
        prompt_text.append("  ready", style=f"dim {self.colors['muted']}")
        self.console.print(prompt_text)
        
        # Use prompt_toolkit for input with autocomplete
        # Format: └─> 
        try:
            prompt_message = FormattedText([
                ("class:brackets", "╰─"),
                ("class:prompt", "› "),
            ])
            user_input = self.prompt_session.prompt(prompt_message)
            return user_input
        except (KeyboardInterrupt, EOFError):
            raise KeyboardInterrupt()
    
    def create_progress_bar(self, context_percent: float, bar_width: int = 25):
        """Create a colored progress bar based on context usage"""
        filled = int((context_percent / 100) * bar_width)
        bar = "█" * filled + "·" * (bar_width - filled)
        
        # Color based on usage
        if context_percent < 50:
            color = self.colors["success"]
        elif context_percent < 80:
            color = self.colors["warning"]
        else:
            color = self.colors["danger"]
        
        return bar, color
    
    def render_footer(self, cwd: str, model: str, context_size: int, model_context_size: int):
        """Render the footer with CWD, model info, and context bar"""
        context_percent = (context_size / model_context_size) * 100
        bar, color = self.create_progress_bar(context_percent, bar_width=25)
        
        # Left side - CWD
        left_text = Text()
        left_text.append("cwd ", style=f"dim {self.colors['muted']}")
        left_text.append(cwd, style=self.colors["accent_alt"])
        
        # Right side - Model and Context
        right_text = Text()
        right_text.append("model ", style=f"dim {self.colors['muted']}")
        right_text.append(model, style=f"bold {self.colors['accent']}")
        right_text.append("   ", style=f"dim {self.colors['muted']}")
        right_text.append("context ", style=f"dim {self.colors['muted']}")
        right_text.append("[", style=f"dim {self.colors['muted']}")
        right_text.append(bar, style=color)
        right_text.append("] ", style=f"dim {self.colors['muted']}")
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
                title=f"[bold {self.colors['accent']}]Response[/bold {self.colors['accent']}]",
                border_style=self.colors["accent"],
                padding=(1, 2)
            )
        )
    
    def render_error(self, error_message: str):
        """Render an error message"""
        self.console.print(
            Panel(
                f"[bold {self.colors['danger']}]Error:[/bold {self.colors['danger']}]\n[white]{error_message}[/white]",
                title=f"[bold {self.colors['danger']}]Error[/bold {self.colors['danger']}]",
                border_style=self.colors["danger"],
                padding=(1, 2)
            )
        )
    
    def render_success_message(self, message: str):
        """Render a success message"""
        self.console.print(f"[{self.colors['success']}]✓[/] {message}", style=f"dim {self.colors['muted']}")
    
    def render_history(self, history_lines: list):
        """Render session history"""
        self.console.print(
            Panel(
                "\n\n".join(history_lines),
                title=f"[bold {self.colors['accent']}]Session History (last 10 messages)[/bold {self.colors['accent']}]",
                border_style=self.colors["accent"],
                padding=(1, 2)
            )
        )
    
    def render_help(self):
        """Render help panel"""
        help_text = Text()
        help_text.append("TERMINUS CLI\n\n", style=f"bold {self.colors['accent']}")
        
        help_text.append("Available Commands:\n\n", style=f"bold {self.colors['accent_alt']}")
        
        help_text.append("  /help         ", style=self.colors["accent"])
        help_text.append(" - Display this help information\n", style="white")
        help_text.append("  /plan <task>  ", style=self.colors["accent"])
        help_text.append(" - Create a detailed implementation plan for a feature\n", style="white")
        help_text.append("  /context      ", style=self.colors["accent"])
        help_text.append(" - View current conversation context\n", style="white")
        help_text.append("  /history      ", style=self.colors["accent"])
        help_text.append(" - View recent session history (last 10 messages)\n", style="white")
        help_text.append("  /reset        ", style=self.colors["accent"])
        help_text.append(" - Reset session history\n", style="white")
        help_text.append("  /context_size ", style=self.colors["accent"])
        help_text.append(" - Display context size\n", style="white")
        help_text.append("  /clear        ", style=self.colors["accent"])
        help_text.append(" - Clear the console screen\n", style="white")
        help_text.append("  /exit         ", style=self.colors["accent"])
        help_text.append(" - Exit the program (also: exit, quit, q)\n\n", style="white")
        
        help_text.append("Usage:\n\n", style=f"bold {self.colors['accent_alt']}")
        help_text.append("  Simply type your query or question and press Enter.\n", style="white")
        help_text.append("  The AI assistant will process your request and provide a response.\n", style="white")
        help_text.append("  Use ", style="white")
        help_text.append("/plan <description>", style=self.colors["accent"])
        help_text.append(" to create detailed implementation plans.\n\n", style="white")
        
        help_text.append("Planning Mode:\n\n", style=f"bold {self.colors['accent_alt']}")
        help_text.append("  Use ", style="white")
        help_text.append("/plan", style=self.colors["accent"])
        help_text.append(" to switch to planning mode for detailed feature planning.\n", style="white")
        help_text.append("  The planner will:\n", style="dim white")
        help_text.append("    • Analyze your codebase structure and patterns\n", style="dim white")
        help_text.append("    • Create a detailed implementation plan as a .md file\n", style="dim white")
        help_text.append("    • Break down tasks into manageable steps\n", style="dim white")
        help_text.append("    • Identify risks and technical considerations\n", style="dim white")
        help_text.append("  Example: ", style="dim white")
        help_text.append("/plan build a user authentication system\n\n", style="bright_red")
        
        help_text.append("File References:\n\n", style=f"bold {self.colors['accent_alt']}")
        help_text.append("  Use ", style="white")
        help_text.append("@filename", style=self.colors["accent_alt"])
        help_text.append(" to reference files in your messages.\n", style="white")
        help_text.append("  Type ", style="dim white")
        help_text.append("@", style=self.colors["accent_alt"])
        help_text.append(" and press ", style="dim white")
        help_text.append("Tab", style="bright_yellow")
        help_text.append(" for autocomplete suggestions.\n", style="dim white")
        help_text.append("  Examples:\n", style="dim white")
        help_text.append("    • ", style="dim white")
        help_text.append("@main.py explain this file", style="bright_cyan")
        help_text.append("\n", style="white")
        help_text.append("    • ", style="dim white")
        help_text.append("compare @file1.py and @file2.py", style="bright_cyan")
        help_text.append("\n\n", style="white")
        
        help_text.append("Tips:\n\n", style=f"bold {self.colors['accent_alt']}")
        help_text.append("  • Use ", style="white")
        help_text.append("Ctrl+C", style="bright_yellow")
        help_text.append(" to cancel a running operation\n", style="white")
        help_text.append("  • Context usage is displayed after each response\n", style="white")
        help_text.append("  • The assistant can help with coding, debugging, and development tasks\n", style="white")
        help_text.append("  • Reference multiple files with @ to provide more context\n", style="white")
        
        self.console.print(
            Panel(
                help_text,
                title=f"[bold {self.colors['accent']}]═══ HELP ═══[/bold {self.colors['accent']}]",
                border_style=self.colors["accent"],
                padding=(1, 2)
            )
        )
    

    def render_table(self):
        table = Table(title="Available Models", box=box.ROUNDED, expand=False)

        table.add_column("Model Name", justify="right", style=self.colors["accent_alt"], no_wrap=True)
        table.add_column("Provider", style=self.colors["accent"])
        table.add_column("Context Size", style=self.colors["warning"], justify="right")
        table.add_column("Input Tokens Pricing", justify="right", style=self.colors["success"])
        table.add_column("Output Tokens Pricing", justify="right", style=self.colors["success"])

        for model in available_models:

            inst = model() if isinstance(model, type) else model

            name = str(inst.name)
            provider = str(inst.provider)
            context_size = f"{int(inst.context_size):,}"           
            input_price = f"${float(inst.input_tokens_pricing):.4g}" 
            output_price = f"${float(inst.output_tokens_pricing):.4g}"

            table.add_row(name, provider, context_size, input_price, output_price)

        self.console.print(Align.center(table))

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
        return StreamingHandler(self.console, self.colors)
    
    def render_todo_panel(self, todos: list, handler=None):
        """Render the todo list panel with status indicators
        
        Args:
            todos: List of todo items to display
            handler: Optional StreamingHandler to use for live display updates
        """
        if not todos:
            return
        
        # If handler is provided, delegate to its live display
        if handler is not None:
            handler.update_todo_display(todos)
            return
        
        # Otherwise, print static panel (backwards compatibility)
        # Filter out completed todos for display (optional - show all for now)
        # active_todos = [t for t in todos if t.get('status') != 'completed']
        # if not active_todos:
        #     return
        
        # Create todo list text with proper alignment
        todo_lines = []
        
        for todo in todos:
            status = todo.get('status', 'pending')
            task = todo.get('task', '')
            
            # Status indicators
            if status == 'completed':
                indicator = "✓"
                style = self.colors["success"]
            elif status == 'in_progress':
                indicator = "⏳"
                style = self.colors["warning"]
            else:  # pending
                indicator = "○"
                style = f"dim {self.colors['muted']}"
            
            line = Text()
            line.append(f"{indicator}  ", style=style)
            line.append(task, style="white")
            todo_lines.append(line)
        
        # Combine all lines
        todo_text = Text("\n").join(todo_lines)
        
        # Render panel with minimal padding, centered and square-shaped
        self.console.print(
            Panel(
                todo_text,
                title=f"[bold {self.colors['accent_alt']}]Todos[/bold {self.colors['accent_alt']}]",
                border_style=self.colors["accent_alt"],
                padding=(1, 2),
                expand=False
            ),
            justify="center"
        )


class StreamingHandler:
    """Manages streaming response display with status updates"""
    
    def __init__(self, console: Console, colors=None):
        self.console = console
        self.colors = colors or {}
        self.streaming_content = []
        self.live_display = None
        self.thinking_started = False
        self.status = None
        self.todo_live_display = None
        self.current_todos = []
    
    def get_user_input(self, prompt: str) -> str:
       
        return self.console.input(prompt)
    
    def start(self):
        """Start the status spinner"""
        accent = self.colors.get("accent", "bright_red")
        self.status = self.console.status(
            status=f"[bold {accent}]Processing your request...",
            spinner="dots12",
            spinner_style=accent
        )
        self.status.__enter__()
        return self
    
    def stop(self):
        """Stop the streaming handler"""
        if self.live_display is not None:
            self.live_display.stop()
            self.live_display = None
        if self.todo_live_display is not None:
            self.todo_live_display.stop()
            self.todo_live_display = None
        if self.status is not None:
            self.status.__exit__(None, None, None)
            self.status = None
    
    def __enter__(self):
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    def update_status(self, message: str, is_thinking: bool = False, is_tool_output: bool = False, keep_stopped: bool = False):
      
        # Stop live display if active
        if self.live_display is not None:
            self.live_display.stop()
            self.live_display = None
        
        if is_tool_output:
            # Display tool output (like diffs) in a separate panel
            # No need to parse markdown, just display raw with ANSI codes
            from rich.text import Text as RichText
            tool_text = RichText.from_ansi(message)
            accent_alt = self.colors.get("accent_alt", "bright_cyan")
            self.status.stop()
            self.console.print(
                Panel(
                    tool_text,
                    title=f"[bold {accent_alt}]Changes[/bold {accent_alt}]",
                    border_style=accent_alt,
                    padding=(1, 2),
                    expand=False
                ),
                justify="center"
            )
            # Only restart status if not waiting for user input
            if not keep_stopped:
                self.status.start()
        elif is_thinking:
            # Only display thinking if there's actual content (not empty or whitespace)
            if message and message.strip():
                # Display thinking header only once
                if not self.thinking_started:
                    self.status.stop()
                    thinking = self.colors.get("warning", "#F4AF2D")
                    self.console.print(f"\n[dim {thinking}][/] [bold {thinking}]Thinking[/]")
                    self.thinking_started = True
                # Display thinking message token by token in tron orange
                text = Text(message, style=self.colors.get("warning", "#FF6C00"))
                self.console.print(text, end="")
        else:
            # End thinking line if it was active
            if self.thinking_started:
                self.console.print()  # New line
                self.thinking_started = False
            
            accent = self.colors.get("accent", "bright_red")
            muted = self.colors.get("muted", "dim white")
            self.status.update(f"[bold {accent}]{message}...")
            # Stop status temporarily to print the message
            self.status.stop()
            # Display tool message
            self.console.print(f"  [dim {muted}]→[/] [{accent}]{message}[/]")
            self.status.start()
    
    def handle_streaming(self, content_chunk: str):
        """Callback to handle streaming content"""
        self.streaming_content.append(content_chunk)
        accumulated = "".join(self.streaming_content)
        
        # Only create/update display if there's actual content (not just whitespace)
        if not accumulated.strip():
            return
        
        # Stop the status spinner and create live display when we have content
        if self.live_display is None:
            self.status.stop()
            accent = self.colors.get("accent", "bright_red")
            self.live_display = Live(
                Panel(
                    Markdown(accumulated),
                    title=f"[bold {accent}]Response[/bold {accent}]",
                    border_style=accent,
                    padding=(1, 2)
                ),
                console=self.console,
                refresh_per_second=10
            )
            self.live_display.start()
        else:
            # Update live display with accumulated content
            accent = self.colors.get("accent", "bright_red")
            self.live_display.update(
                Panel(
                    Markdown(accumulated),
                    title=f"[bold {accent}]Response[/bold {accent}]",
                    border_style=accent,
                    padding=(1, 2)
                )
            )
    
    def has_streamed_content(self):
        """Check if any content was streamed (with actual visible content)"""
        return bool(self.streaming_content) and bool("".join(self.streaming_content).strip())
    
    def update_todo_display(self, todos: list):
        """Update the live todo display with new todo data"""
        if not todos:
            return
        
        # Store current todos
        self.current_todos = todos
        
        # Create todo list text with proper alignment
        todo_lines = []
        
        for todo in todos:
            status = todo.get('status', 'pending')
            task = todo.get('task', '')
            
            # Status indicators
            if status == 'completed':
                indicator = "✓"
                style = self.colors.get("success", "bright_green")
            elif status == 'in_progress':
                indicator = "⏳"
                style = self.colors.get("warning", "bright_yellow")
            else:  # pending
                indicator = "○"
                style = f"dim {self.colors.get('muted', 'white')}"
            
            line = Text()
            line.append(f"{indicator}  ", style=style)
            line.append(task, style="white")
            todo_lines.append(line)
        
        # Combine all lines
        todo_text = Text("\n").join(todo_lines)
        
        # Create the panel
        accent_alt = self.colors.get("accent_alt", "bright_cyan")
        todo_panel = Panel(
            todo_text,
            title=f"[bold {accent_alt}]Todos[/bold {accent_alt}]",
            border_style=accent_alt,
            padding=(1, 2),
            expand=False
        )
        
        # Create or update live display
        if self.todo_live_display is None:
            # Stop current status if active to print the centered panel
            if self.status:
                self.status.stop()
            
            # Print the panel centered
            self.console.print(todo_panel, justify="center")
            
            # Restart status if it was active
            if self.status:
                self.status.start()
        else:
            # For updates, stop, print centered, and restart
            self.todo_live_display.stop()
            
            if self.status:
                self.status.stop()
            
            self.console.print(todo_panel, justify="center")
            
            if self.status:
                self.status.start()
            
            # Note: Not restarting todo_live_display as we're just printing static updates
            self.todo_live_display = None
    
    def render_final_response(self, response: str):
        """Render the final response panel only if no streaming occurred"""
        # Only render if no streaming occurred, otherwise Live display already showed it
        if not self.has_streamed_content():
            md = Markdown(response)
            accent = self.colors.get("accent", "bright_red")
            self.console.print(
                Panel(
                    md,
                    title=f"[bold {accent}]Response[/bold {accent}]",
                    border_style=accent,
                    padding=(1, 2)
                )
            )
