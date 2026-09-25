---
description: Run all linters (ruff for Python, skills-lint for OpenCode skills)
argument-hint: "[--fix]"
---

Run the project's linters:

1. Python: `ruff check .` (add `--fix` if the user passed it, else read-only)
2. Skills: `python scripts/skills_lint.py`
3. Report errors first, then warnings. Do not auto-fix without `--fix`.
