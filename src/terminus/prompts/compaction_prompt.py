from textwrap import dedent


def get_compaction_prompt() -> str:
    return dedent(
        """
        <compaction_task>
        You are creating the durable handoff context that will replace an older
        conversation in a coding agent's context window. The next agent response
        must be able to continue the work correctly using only your summary, the
        preserved system instructions, and any messages kept after the summary.

        Respond with plain text only. Do not call tools. Do not include analysis,
        preamble, XML tags, or commentary about the act of summarizing.

        Preserve concrete information over narrative. Be concise where possible,
        but completeness is more important than brevity. Never invent missing
        details. Mark uncertain or conflicting information explicitly. Do not
        reproduce secrets, credentials, tokens, or irrelevant large tool output.

        Produce the following sections in this exact order. Keep every section;
        write "None" when it has no content.

        1. Primary goal and success criteria
        - The user's current objective and what a completed result must do.
        - The latest intent takes precedence, but retain earlier requirements that
          still apply.

        2. User instructions and constraints
        - Every explicit user request, correction, preference, prohibition, and
          acceptance criterion that remains relevant.
        - Project or repository instructions surfaced in the conversation.
        - Quote exact wording only when precision is important.

        3. Environment and repository state
        - Working directory, relevant architecture, language/runtime, branch, and
          important configuration details.
        - Existing uncommitted changes or user-owned files that must be preserved.

        4. Work completed
        - Actions already taken, files created or changed, and the purpose of each.
        - Important implementation details, APIs, signatures, data shapes, and
          behavior now present.
        - Commands or migrations already executed when repeating them could be
          harmful or wasteful.

        5. Key findings and decisions
        - Root causes, discoveries, chosen approach, rejected approaches, and the
          reasoning or evidence that matters for future decisions.
        - Relevant tool results, errors, warnings, and their resolution.

        6. Verification performed
        - Exact checks, tests, builds, lint commands, or manual verification run,
          including outcomes and any failures that remain.

        7. Remaining work
        - Unfinished tasks in priority order, including blockers, dependencies,
          open questions, and clearly identified optional work.

        8. Current working state and next action
        - What was happening immediately before compaction.
        - The precise next safe action the agent should take.
        - Include relevant paths, symbols, commands, small code fragments, IDs, or
          error text needed to resume without rediscovery.

        9. Conversation record
        - A chronological, compact record of all user-authored messages and later
          corrections. Preserve distinct requests rather than blending them.
        - Include assistant commitments when the user may rely on them.

        Treat an existing compaction summary in the history as source material:
        carry forward every still-relevant fact from it and merge newer events.
        Distinguish completed work from proposed work. Do not claim that a change,
        test, commit, push, deployment, or external action happened unless the
        conversation contains evidence that it did.
        </compaction_task>
        """
    ).strip()
