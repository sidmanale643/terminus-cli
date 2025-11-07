import os
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class TerminusCompleter(Completer):
    def __init__(self):
        self.commands = [
            '/help', '/context', '/history', '/reset', 
            '/context_size', '/clear', '/exit', '/quit', 'q',
            'exit', 'quit'
        ]
        
        self.tool_commands = [
            'ls', 'cd', 'cat', 'grep', 'find', 'mkdir', 'touch',
            'rm', 'cp', 'mv', 'chmod', 'git', 'python', 'node',
            'npm', 'pip', 'uv', 'docker', 'kubectl'
        ]
        
        self.file_extensions = [
            '.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.txt',
            '.json', '.yaml', '.yml', '.toml', '.cfg', '.ini',
            '.sh', '.bash', '.zsh', '.env', '.gitignore'
        ]

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        current_word = words[-1] if words else ""
        
        # Check for @ file reference completion
        if current_word.startswith('@'):
            yield from self._complete_file_references(document, current_word)
            return
        
        # Complete commands if at start or after space
        if len(words) <= 1 or (len(words) > 1 and text.endswith(' ')):
            # Complete slash commands
            if current_word.startswith('/'):
                for cmd in self.commands:
                    if cmd.startswith(current_word):
                        yield Completion(
                            cmd,
                            start_position=-len(current_word),
                            display=cmd,
                            display_meta="Command"
                        )
            # Complete tool commands
            else:
                for cmd in self.tool_commands:
                    if cmd.startswith(current_word):
                        yield Completion(
                            cmd,
                            start_position=-len(current_word),
                            display=cmd,
                            display_meta="Tool"
                        )
        
        # Complete file paths
        if not current_word.startswith('/') and any(char in text for char in [' ', './', '../', '/']):
            yield from self._complete_files(document, current_word)
    
    def _complete_file_references(self, document: Document, current_word: str):
        """Complete @file references for file inclusion"""
        # Remove the @ symbol for path processing
        path_part = current_word[1:]  # Remove @
        
        # Determine directory and prefix
        if not path_part:
            current_dir = '.'
            prefix = ''
        elif '/' in path_part:
            current_dir = os.path.dirname(path_part) or '.'
            prefix = os.path.dirname(path_part) + '/' if os.path.dirname(path_part) else ''
        else:
            current_dir = '.'
            prefix = ''
        
        try:
            if os.path.isdir(current_dir):
                items = []
                for item in os.listdir(current_dir):
                    # Skip hidden files and directories
                    if item.startswith('.'):
                        continue
                    
                    full_path = os.path.join(current_dir, item)
                    if os.path.isdir(full_path):
                        # For directories, add trailing slash
                        items.append((item + '/', 'Directory', full_path))
                    else:
                        # Only suggest files with relevant extensions
                        ext = os.path.splitext(item)[1]
                        if ext in self.file_extensions:
                            items.append((item, f'File ({ext})', full_path))
                
                # Filter by current path part
                search_term = os.path.basename(path_part)
                for item, meta, full_path in items:
                    if item.startswith(search_term) or not search_term:
                        completion_text = '@' + prefix + item
                        yield Completion(
                            completion_text,
                            start_position=-len(current_word),
                            display=item,
                            display_meta=meta
                        )
        except (OSError, PermissionError):
            pass
    
    def _complete_files(self, document: Document, current_word: str):
        """Complete file and directory paths"""
        if not current_word:
            # Complete files in current directory
            current_dir = '.'
        else:
            # Handle relative paths
            if current_word.startswith('./'):
                current_dir = current_word[:-2] or '.'
                prefix = './'
            elif current_word.startswith('../'):
                parts = current_word.split('../')
                current_dir = '../' * (len(parts) - 1) + (parts[-1] if parts[-1] else '.')
                prefix = '../' * (len(parts) - 1)
            elif current_word.startswith('/'):
                current_dir = os.path.dirname(current_word) or '/'
                prefix = os.path.dirname(current_word) + '/' if os.path.dirname(current_word) else '/'
            else:
                current_dir = os.path.dirname(current_word) or '.'
                prefix = os.path.dirname(current_word) + '/' if os.path.dirname(current_word) else ''
        
        try:
            # Get directory contents
            if os.path.isdir(current_dir):
                items = []
                for item in os.listdir(current_dir):
                    full_path = os.path.join(current_dir, item)
                    if os.path.isdir(full_path):
                        items.append((item + '/', 'Directory'))
                    else:
                        ext = os.path.splitext(item)[1]
                        if ext in self.file_extensions or not ext:
                            items.append((item, 'File'))
                
                # Filter by current word (excluding path prefix)
                search_term = os.path.basename(current_word)
                for item, meta in items:
                    if item.startswith(search_term):
                        display_item = prefix + item if prefix else item
                        yield Completion(
                            display_item,
                            start_position=-len(current_word),
                            display=item,
                            display_meta=meta
                        )
        except (OSError, PermissionError):
            pass


class SmartCompleter(TerminusCompleter):
    """Enhanced completer with context awareness"""
    
    def __init__(self, agent=None):
        super().__init__()
        self.agent = agent
        
    def get_completions(self, document: Document, complete_event):
        # Get base completions
        yield from super().get_completions(document, complete_event)
        
        # Add context-aware completions if agent is available
        if self.agent:
            yield from self._get_context_completions(document)
    
    def _get_context_completions(self, document: Document):
        """Get completions based on conversation context"""
        text = document.text_before_cursor
        current_word = text.split()[-1] if text.split() else ""
        
        # Complete recent file paths from conversation
        if self.agent and hasattr(self.agent, 'context'):
            recent_files = self._extract_recent_files()
            for file_path in recent_files:
                if file_path.endswith(current_word) or current_word in file_path:
                    yield Completion(
                        file_path,
                        start_position=-len(current_word),
                        display=os.path.basename(file_path),
                        display_meta="Recent File"
                    )
    
    def _extract_recent_files(self):
        """Extract file paths from recent conversation history"""
        files = set()
        if self.agent and hasattr(self.agent, 'context'):
            for message in self.agent.context[-10:]:  # Last 10 messages
                content = message.get('content', '')
                # Simple pattern matching for file paths
                import re
                file_patterns = re.findall(r'[\w\-./]+\.(py|js|ts|jsx|tsx|md|txt|json|yaml|yml|toml|env)', content)
                files.update(file_patterns)
        return list(files)[:20]  # Limit to 20 most recent