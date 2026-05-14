import os
from src.models.tool import ToolSchema
from textwrap import dedent
import json

class SendNotification(ToolSchema):
    def __init__(self):
        self.name = "send_notification"

    def description(self):
        return dedent("""
        Send a notification to the co-ordinator agent notifying it abput the status of the task etce etc.
        The contents of the notification will only be seen by the co ordinator and not the user.
        
        Notify the co ordinator on major discovieries, findings, steps or anything the co ordinator must know.

        Usage:
        - Send status of task
        - Summary of the steps taken and discoveries
        - Send final result
        """)

    def json_schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description(),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "the id of the worker sending the notification",
                        },
                        "status": {
                            "type": "string",
                            "description": "the status of the task could be Ongoing| Completed| Killed",
                        },
                         "summary": {
                            "type": "string",
                            "description": "the summary of the agents work",
                        },
                        "final_response": {
                            "type": "string",
                            "description": "the final response of the worker",
                        },
                        
                    },
                    "required": ["status", "summary", "final_response"],
                },
            },
        }

    def run(self, id, status, summary, final_response):
        try:
            notification= {
                "id": id,
                "status": status,
                "summary": summary,
                "final_response": final_response
            }
            return json.dumps(notification)
        
        except Exception as e:
            return f"Error reading file: {e}"
