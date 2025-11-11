from src.prompts.planner_prompt import get_planner_prompt
from src.prompts.system_prompt import get_system_prompt

class PromptManager:
    def __init__(self, cwd=None):

        self.system_prompt = get_system_prompt(cwd)
        self.planner_prompt = get_planner_prompt()
        self.prompts = {}
        
    def add_prompt(self, name : str, prompt : str):
        self.prompts[name] = prompt
    
    def get_system_prompt(self):
        return self.system_prompt

    def get_planner_prompt(self):
        return self.planner_prompt