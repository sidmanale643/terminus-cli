from textwrap import dedent
from typing import Any
from terminus.tools.base import ToolSchema


class AskQuestion(ToolSchema):
    def __init__(self):
        self.name = "ask_question"

    def description(self):
        return dedent("""
        Ask clarifying questions to the user to gain more insight into their requirements and needs.
        Ask a question whenever you are at a crossroads or want clarification.
        Each question must include exactly three viable options. Set allow_multiple
        to true only when the user may reasonably select more than one option.
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
                        "questions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {
                                        "type": "string",
                                        "description": "Question text for the user",
                                    },
                                    "options": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "minItems": 3,
                                        "maxItems": 3,
                                        "description": "Exactly three viable options the user can select from",
                                    },
                                    "allow_multiple": {
                                        "type": "boolean",
                                        "description": "Whether the user may select multiple options",
                                        "default": False,
                                    },
                                },
                                "required": ["text", "options"],
                            },
                            "description": "Structured questions for the user.",
                        }
                    },
                    "required": ["questions"],
                },
            },
        }

    def run(self, questions: list[dict[str, Any]]) -> str:
        if not isinstance(questions, list):
            return "Error: questions must be a list."
        if not questions:
            return "No questions to ask."

        normalized_questions = []
        for question in questions:
            if not isinstance(question, dict):
                return "Error: each question must be an object."
            text = question.get("text")
            options = question.get("options")
            if not isinstance(text, str) or not text.strip():
                return "Error: each question must include non-empty text."
            if (
                not isinstance(options, list)
                or len(options) != 3
                or any(
                    not isinstance(option, str) or not option.strip()
                    for option in options
                )
            ):
                return (
                    "Error: each question must include exactly three non-empty options."
                )
            normalized_questions.append(
                {
                    "text": text.strip(),
                    "options": [option.strip() for option in options],
                    "allow_multiple": bool(question.get("allow_multiple", False)),
                }
            )

        lines = ["I have some clarifying questions:", ""]
        for i, question in enumerate(normalized_questions, start=1):
            mode = "select one or more" if question["allow_multiple"] else "select one"
            lines.append(f"{i}. {question['text']} ({mode})")
            for option_index, option in enumerate(question["options"], start=1):
                lines.append(f"   {option_index}. {option}")

        return "\n".join(lines)
