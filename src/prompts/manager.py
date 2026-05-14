from src.prompts.planner_prompt import get_planner_prompt
from src.prompts.system_prompt import get_system_prompt
from src.prompts.init_prompt import get_init_prompt
from src.prompts.coordinator_prompt import get_coordinator_prompt
from src.prompts.compaction_prompt import get_compaction_prompt

class PromptManager:
    def __init__(self, cwd=None):

        self.system_prompt = get_system_prompt(cwd)
        self.planner_prompt = get_planner_prompt()
        self.init_prompt= get_init_prompt()
        self.coordinator_prompt= get_coordinator_prompt()
        
        self.prompts = {}
        
    def add_prompt(self, name : str, prompt : str):
        self.prompts[name] = prompt
    
    def get_system_prompt(self):
        return self.system_prompt

    def get_planner_prompt(self):
        return self.planner_prompt
    
    def get_init_prompt(self):
        return self.init_prompt
    
    def get_coordinator_prompt(self):
        return self.coordinator_prompt
    
    def get_compaction_prompt(self):
        return self.get_compaction_prompt
    