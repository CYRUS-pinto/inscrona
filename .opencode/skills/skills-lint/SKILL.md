---
name: skills-lint
description: Validate OpenCode skill structure (SKILL.md frontmatter, naming, description triggers). Use when adding or editing skills, when a skill doesn't load, or when asked to lint skills.
---

# Skills Lint

Project-local linter for OpenCode agent skills. Validates every skill against
the OpenCode skill spec (mirrors the global `skill-check` skill, scoped to this repo).

## When to load

- Adding or editing anything under `.opencode/skills/`, `.claude/skills/`, or `.agents/skills/`
- A skill doesn't show up in OpenCode (`skill` tool listing)
- User asks to "lint skills", "check skills", "validate skills"

## When NOT to load

- General Python linting — use `/lint` (ruff) instead
- Security scanning of skill scripts — out of scope, flag manually

## Core rules

1. Every skill is `<root>/<skill-name>/SKILL.md` (exact caps).
2. Frontmatter must include `name` and `description`.
3. `name` must match the directory name and `^[a-z0-9]+(-[a-z0-9]+)*$`
   (lowercase alphanumeric, single-hyphen separators, 1–64 chars).
4. `description` must be 1–1024 chars and state WHEN to use the skill
   (contains "when", "use for", or "trigger").
5. Body should have load guidance and concrete steps, not vague advice.

## Minimal examples

```bash
# Lint all project skills
python scripts/skills_lint.py

# Lint one skill
python scripts/skills_lint.py .opencode/skills/skills-lint
```

Exit code 0 = all pass, 1 = errors, 2 = warnings only.

## Anti-patterns

- Skill folder nested an extra level deep (`skills/foo/SKILL.md/SKILL.md`)
- Frontmatter with unquoted colons breaking YAML parse
- Description that summarizes contents instead of giving a trigger condition
- Absolute hardcoded paths in the body (breaks portability)

## Checklist

- [ ] `SKILL.md` spelled in all caps, frontmatter has `name` + `description`
- [ ] Name matches directory and the regex
- [ ] Description has a WHEN/trigger clause
- [ ] `python scripts/skills_lint.py` exits 0
