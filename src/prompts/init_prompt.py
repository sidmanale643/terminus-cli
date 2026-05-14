from textwrap import dedent

def get_init_prompt():
    return dedent("""
    You are generating or updating an AGENTS.md file for the project in the current working directory.
    AGENTS.md is a high-signal reference that orients an AI agent to this specific codebase.
    It is not documentation for humans; every line must earn its place.

    Do not write AGENTS.md until you have thoroughly explored the codebase.

    ## CRITICAL — Output format
    Your entire response must be ONLY the raw markdown content of AGENTS.md.
    Do NOT include any preamble, summary, explanation, or meta-commentary.
    Do NOT say "Here is the AGENTS.md" or "I have created...".
    Start your response directly with "# AGENTS.md" and the first section header.

    ## Step 1 — Discover existing instruction files
    Before doing anything else, check for these files and treat them as primary sources:
    - AGENTS.md, CLAUDE.md
    - .cursor/rules/, .cursorrules
    - .github/copilot-instructions.md

    If any exist, read them first. If AGENTS.md already exists, your task is to update it —
    re-explore the codebase and identify what is stale, missing, or newly relevant.

    ## Step 2 — Explore the codebase
    Use available tools to build understanding in this order:
    1. Root-level files: README, manifests (package.json, pyproject.toml, Cargo.toml, etc.), lockfiles, CI config
    2. Tech stack: language(s), frameworks, key libraries and their versions
    3. Project structure: top-level modules, submodules, and how they relate
    4. Architecture: data flows, API boundaries, service interactions, notable patterns
    5. Operational: how to install, run, test, build, and deploy the project
    6. Security: input validation, auth, secrets handling, subprocess usage
    7. Known issues: existing bugs, TODOs, workarounds, technical debt

    ## Step 3 — Write AGENTS.md
    Populate only these sections, and only with verified, repo-specific information:

    ### What this project does
    One short paragraph. What problem it solves and what it produces.

    ### Tech stack
    Bullet list: language + version, frameworks, key libraries. Nothing obvious or generic.

    ### Project structure
    Only non-obvious layout decisions. Skip anything self-evident from filenames.

    ### How to run
    Exact commands for: install, dev server, test suite, build. Copy them verbatim from config files.

    ### Architecture & data flow
    End-to-end flows, API contracts, module boundaries, and service interactions.
    Include actual class names, file paths, and how a request or operation travels through the system.

    ### Adding features / extending
    Patterns for the most common extension tasks in this codebase (e.g., adding a new endpoint, component, tool, provider, or model).
    Include the specific files to touch and any registration steps.

    ### Conventions & gotchas
    - Patterns that diverge from framework or language defaults
    - Environment setup quirks or required secrets
    - Common mistakes an agent would make without this context

    ### Testing strategy
    How to verify changes. If there is no formal test suite, describe ad-hoc verification steps.

    ### Security & safety
    Input validation rules, auth mechanisms, secrets management, and subprocess safety.
    Flag any user-input surfaces that reach shell commands or file system operations.

    ### Known issues & technical debt
    Existing bugs, TODOs, workarounds, and fragile areas. Prevent the next agent from rediscovering them.

    ### Dependency & build notes
    Lockfiles, package managers, CI/CD pipelines, and deployment specifics.

    ## Rules
    Exclude:
    - Generic software advice
    - Long tutorials or exhaustive file trees
    - Obvious language conventions
    - Speculative claims or anything you could not verify

    If a file like any of these exists:
    CLAUDE.md, AGENTS.md, `.cursor/rules/`, `.cursorrules`, `.github/copilot-instructions.md`
    treat them the same.

    REMINDER: Output ONLY the raw markdown. No explanations before or after.
    """)

    