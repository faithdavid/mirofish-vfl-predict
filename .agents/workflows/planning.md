---
description: Always create a plan.md before executing any non-trivial task
---

# Planning Workflow

Before executing ANY non-trivial task (code changes, new features, refactors, bug fixes beyond a single line):

1. **Research Phase**: Use web search, file exploration, and codebase analysis to understand the full scope.
2. **Create `implementation_plan.md`**: Write a detailed plan artifact covering:
   - Goal description & background context
   - Proposed changes (grouped by component/file)
   - Open questions for the user
   - Verification plan
3. **Request User Review**: Always set `request_feedback = true`. Do NOT proceed until the user explicitly approves.
4. **Execute**: Only after approval, begin implementation. Track progress in `task.md`.
5. **Verify**: Run tests, check the browser, confirm behavior.
6. **Walkthrough**: Summarize what was done in `walkthrough.md`.

> This workflow applies to ALL conversations, not just the mirofish project.
