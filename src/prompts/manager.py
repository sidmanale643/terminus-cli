from src.prompts.system_prompt import SYSTEM_PROMPT

class PromptManager:
    def __init__(self):

        self.system_prompt = SYSTEM_PROMPT
        self.prompts = {}
        
    def add_prompt(self, name : str, prompt : str):
        self.prompts[name] = prompt
    
    def get_system_prompt(self):
        return self.system_prompt
