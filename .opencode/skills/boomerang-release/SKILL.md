---
name: boomerang-release
description: Multi-target release discipline — version bumps, drift detection, git tags, PyPI/NPM publishing, GitHub release tracking. Backed by the bumpversion CLI.
---

# Boomerang Release

## Description

End-to-end release discipline for any package in the MCP-Servers workspace.
Covers version bumps (PyPI, NPM, GitHub), changelog updates, git tags, and
post-release verification across **all** release targets. Backed by the
**`bumpversion`** CLI at `boomerang-v3/scripts/bumpversion` (also symlinked
as `bumpversion.py` for testability).

## When To Use This Skill

Use this skill when:
- Preparing a release (any target: PyPI, NPM, GitHub)
- Bumping a version number
- Updating a changelog
- Creating or pushing a git tag
- Publishing a package
- Investigating "why is X not on PyPI yet?" / "why is the tag missing?"

**Trigger phrases**: "release", "bump version", "ship", "publish",
"new version", "tag and push", "cut a release", "what's the version of X?"

## The Tool: `bumpversion`

**Location**: `boomerang-v3/scripts/bumpversion` (executable Python CLI,
no external deps; stdlib only).

**The single most important rule**: when bumping a version, **always use
`bumpversion --apply`**, never hand-edit `package.json` / `pyproject.toml`
/ `__version__.py`. The script handles:
- Auto-detecting which repo you're in (10 known repos)
- Reading the version from every tracking file
- Drift detection (refuses to bump if files disagree)
- Listing every release target that will publish (PyPI, NPM, GitHub)
- Dry-run by default; --apply to write
- Auditing local vs git tag vs PyPI vs NPM (with `--audit`)

### Commands

```bash
# Show what would change (dry-run)
bumpversion --patch

# Bump and write
bumpversion --patch --apply

# Drift check (exit 0 if all files agree)
bumpversion --check

# List files + release targets for the current repo
bumpversion --list

# Deep audit: local vs tag vs PyPI vs NPM
bumpversion --audit
bumpversion --audit --no-network   # offline mode

# Run from inside a sub-repo (e.g. memini-ai-dev/) ...
cd memini-ai-dev && bumpversion --patch
# ... or from the workspace root
bumpversion --repo memini-ai-dev --patch
```

### Repos Known (auto-detected)

| Repo | Subdir | Targets |
|------|--------|---------|
| memini-ai-dev | `memini-ai-dev/` | PyPI + GitHub |
| boomerang-queue | `boomerang-queue/` | PyPI |
| boomerang-proxy | `boomerang-proxy/` | PyPI |
| doc2png | `doc2png/` | PyPI |
| @veedubin/boomerang-v3 | `boomerang-v3/` | NPM + GitHub |
| @veedubin/neuralgentics | `neuralgentics/` | NPM + GitHub |
| super-memory-ts | `Super-Memory-TS/` | NPM |
| @fangjunjie/ssh-mcp-server | `ssh-mcp-server/` | NPM + GitHub |

To add a new repo, append a `RepoConfig` to the `REPOS` list in
`scripts/bumpversion`.

## Instructions

You are the **Boomerang Release** specialist. Your role:

1. **Audit first** — Always start with `bumpversion --audit` to see
   the current state across all targets
2. **Version Bump** — Use `bumpversion --{patch,minor,major} --apply`
   to increment
3. **Changelog** — Update `CHANGELOG.md` with release notes
4. **Git Tags** — Commit, tag, and push (bumpversion prints the exact
   commands after a successful --apply)
5. **Verify** — After CI fires, re-run `bumpversion --audit` to confirm
   the new version is live on all targets

## Release Workflow

### Step 1: Pre-flight Audit

```bash
bumpversion --audit --no-network
```

If drift is detected, fix it FIRST (do not bump on top of drift).
Re-run until clean.

### Step 2: Bump the Version

```bash
# Dry-run first to see the plan
bumpversion --patch

# Then apply
bumpversion --patch --apply
```

`bumpversion` will print the exact commit/tag/push commands to run next.

### Step 3: Update Changelog

Edit `CHANGELOG.md` (or per-project `CHANGELOG.md`) and add a section
for the new version. Use categories: Added, Changed, Deprecated, Removed,
Fixed, Security.

### Step 4: Git Operations

```bash
git add -A
git commit -m "chore(release): bump to X.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z: <description>"
git push origin main vX.Y.Z
```

> **NEVER force-push a tag.** Once a tag is pushed to origin AND a
> release is published, it is IMMUTABLE. Bump the patch number instead.

### Step 5: CI Publishes

`.github/workflows/*.yml` triggers on `v*.*.*` tag pushes:
- **PyPI** for Python repos (memini-ai-dev, boomerang-queue, etc.)
- **NPM** for NPM repos (boomerang-v3, neuralgentics, ssh-mcp-server)
- **GitHub release** for repos with a release workflow

### Step 6: Post-flight Audit

```bash
# Wait ~60s for CI to finish, then:
bumpversion --audit
```

Expected output: `Local version`, `Git tag`, `PyPI`/`NPM` all show
the new version, all marked with `✓`.

## Guidelines

- **Never** hand-edit `package.json` or `pyproject.toml` for a version
  bump. Use `bumpversion`. The script catches drift you might miss.
- **Never** force-push tags. Bump the patch number instead.
- **Always** run `bumpversion --audit` before AND after a release.
- **Default = dry-run.** `bumpversion` won't write without `--apply`.
- **Refuses dirty trees.** Commit or stash before bumping
  (or pass `--force-dirty`).
- **Refuses drift.** Fix drift first (or pass `--force-drift`).
- **Cross-target consistency.** `bumpversion` knows which targets
  apply per repo and prints the publish plan.

## Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `local version differs from git tag` | Tag wasn't pushed | `git push origin vX.Y.Z` |
| `local differs from PyPI/NPM` | CI didn't run / failed | Check Actions tab; re-trigger |
| `version files disagree` (drift) | Someone hand-edited a file | Run `bumpversion --check`, fix the offender |
| `working tree not clean` | Uncommitted changes | `git stash` or commit first |
| Tag was wrong / wrong commit | Tried to retag | DON'T. Bump patch, tag new commit. |

## Output Format (Return to Orchestrator)

```markdown
## Release: v[Version]

### Bump
- Type: [major/minor/patch]
- Files: [list, e.g. "package.json, pyproject.toml"]
- Tool: `bumpversion --{patch,minor,major} --apply`

### Audit (post-publish)
- Local: vX.Y.Z
- Git tag: vX.Y.Z ✓
- PyPI: X.Y.Z ✓ (or pending)
- NPM: X.Y.Z ✓ (or pending)
- GitHub release: created ✓ (or pending)

### CI Status
- [workflow name] (run #): [status]

### Memory Reference
Release details saved to memini-ai.
```

## memini-ai Protocol

### Required Actions

1. **Query at start** — Query memini-ai for:
   - Previous release procedures for this repo
   - Version history
   - Known release issues / CI failures

2. **Save at end** — Save to memini-ai:
   - Release version and date
   - Changes included
   - CI workflow run ID
   - Issues encountered
   - Lessons learned (e.g. "had to re-tag because tag was on wrong commit")

## Escalation Triggers

| Situation | Escalate To | Reason |
|-----------|-------------|--------|
| Breaking changes | `boomerang-architect` | Review impact |
| CI publish failure | `boomerang-coder` | May need fix in workflow |
| Version conflicts / drift | `boomerang-git` | Git resolution |
| Need to yank a release | User | Tokens are user-only; cannot be done by agent |
| Need to add a new repo to the registry | `boomerang-coder` | One-line change to `scripts/bumpversion` |

## When NOT to Use This Skill

- Tag-only / no-version-change commits (use `boomerang-git` directly)
- Just creating a branch or PR (use `boomerang-git`)
- Modifying release workflows (use `boomerang-coder` + `boomerang-architect`)
- For a hotfix to a published release, follow the
  "Never Retag a Public Release" rule in `AGENTS.md` instead.

## Related

- **AGENTS.md → "Never Retag a Public Release"** (CRITICAL rule)
- **AGENTS.md → "Container Deletion Policy"** (no podman rm during releases)
- **`boomerang-v3/scripts/bumpversion`** — the canonical tool
- **`boomerang-v3/scripts/install-boomerang.js`** — bootstrapper
- **`boomerang-git` agent** — does the actual commit/tag/push
