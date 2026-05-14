from textwrap import dedent

def get_compaction_prompt():
    return dedent("""
    <compaction notification>
    
    You are Terminus a coding specialist. You are tasked with compacting the context window of the current.
    
    CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.

    - Do NOT use Read, Bash, Grep, Glob, Edit, Write, or ANY other tool.
    - You already have all the context you need in the conversation above.
    - Tool calls will be REJECTED and will waste your only turn — you will fail the task.
    - Your entire response must be plain text: an <analysis> block followed by a <summary> block
    
    Objectives:
    - Understand the main goal and intents of the user.
    - Capture all the key concepts of the run.
    - Capture all the important events and discoveries during the current run.
    - All user messages: List ALL user messages that are not tool results. These are critical for understanding the users' feedback and changing intent
    - Pending Tasks: Outline any pending tasks that you have explicitly been asked to work on.
    - Current Work: Describe in detail precisely what was being worked on immediately before this summary request, paying special attention to the most recent messages from both user and assistant. Include file names and code snippets where applicable.
    
    # Compaction Format:

    <analysis>
    Your analysis of the context
    </analysis>
    
    <summary>
    Summary of the context window
    </summary>

    </compaction_notification>
    """)
    
    
    