from textwrap import dedent
from typing import Any, List
from src.models.tool import ToolSchema

FALLBACK_OPTIONS = [
    "Use the recommended default",
    "Let me decide manually",
    "Skip this for now",
]


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
                        "num_questions": {
                            "type": "integer",
                            "description": "The total number of questions"
                        },
                        "questions": {
                            "type": "array",
                            "items": {
                                "oneOf": [
                                    {"type": "string"},
                                    {
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
                                            },
                                        },
                                        "required": ["text", "options", "allow_multiple"],
                                    },
                                ],
                            },
                            "description": "Structured questions for the user. String questions are accepted only for backward compatibility."
                        }
                    },
                    "required": ["num_questions", "questions"]
                }
            }
        }

    def normalize_questions(self, questions: List[Any]) -> List[dict[str, Any]]:
        if not questions:
            return []
        return [self._normalize_question(question) for question in questions]

    def _normalize_question(self, question: Any) -> dict[str, Any]:
        if isinstance(question, dict):
            text = str(question.get("text") or question.get("question") or "").strip()
            options = self._normalize_options(question.get("options"))
            allow_multiple = bool(question.get("allow_multiple", question.get("allowMultiple", False)))
            return {
                "text": text or "Please clarify your preference.",
                "options": options,
                "allow_multiple": allow_multiple,
            }
        return {
            "text": str(question).strip() or "Please clarify your preference.",
            "options": FALLBACK_OPTIONS.copy(),
            "allow_multiple": False,
        }

    def _normalize_options(self, options: Any) -> List[str]:
        if not isinstance(options, list):
            return FALLBACK_OPTIONS.copy()

        normalized = [str(option).strip() for option in options if str(option).strip()]
        return (normalized + FALLBACK_OPTIONS)[:3]

    def run(self, num_questions: int, questions: List[Any]) -> str:
        """
        Format and return clarifying questions for the user.

        Args:
            num_questions: The total number of questions being asked.
            questions: A list of structured questions to present to the user.

        Returns:
            A formatted string containing the questions.
        """
        normalized_questions = self.normalize_questions(questions)
        if not normalized_questions:
            return "No questions to ask."

        lines = ["I have some clarifying questions:", ""]
        for i, question in enumerate(normalized_questions, start=1):
            mode = "select one or more" if question["allow_multiple"] else "select one"
            lines.append(f"{i}. {question['text']} ({mode})")
            for option_index, option in enumerate(question["options"], start=1):
                lines.append(f"   {option_index}. {option}")

        return "\n".join(lines)
