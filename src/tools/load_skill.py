from src.models.tool import ToolSchema
from textwrap import dedent


class LoadSkill(ToolSchema):
    def __init__(self):
        self.name = "load_skill"

    def description(self):
        return dedent("""
        Loads a skill by name into the current conversation context.
        Skills are specialized instruction sets that provide domain-specific
        workflows, templates, and best practices.

        Use this tool when the user's task clearly matches an available skill
        that has not been loaded yet. Loading a skill gives you access to its
        full instructions and guidance.

        The skill name must match one of the available skills exactly.
        """).strip()

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The exact name of the skill to load",
                        }
                    },
                    "required": ["name"],
                },
            },
        }

    def run(self, name: str, **kwargs):
        from src.utils import discover_skills

        agent = kwargs.get("_agent")
        if agent is None:
            return "Error: load_skill must be called from an agent context."

        skills = discover_skills(agent.cwd)
        match = next((skill for skill in skills if skill["name"] == name), None)
        if match is None:
            available = ", ".join(skill["name"] for skill in skills) or "none"
            return f"Skill '{name}' not found. Available skills: {available}"

        loaded = agent.load_skill(match)
        if not loaded:
            return f"Skill '{name}' is already loaded."
        return f"Skill '{name}' loaded successfully."
