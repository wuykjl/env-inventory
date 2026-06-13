# env-inventory — Design-time asset scanner for AI agents

> When Claude Code says "build a new project," this skill answers: "here's what you already have. Don't install anything you don't need."

## What

A Python scanner + Claude Code skill that inventories your entire development environment across 7 dimensions, then feeds it into the agent's design phase so it recommends **reuse** before **new installs**.

**7 dimensions scanned:**

| Dimension | What it finds |
|-----------|---------------|
| AI/LLM APIs | Configured SDKs, proxy endpoints, model names |
| CLI Tools | 12 categories (npm, pip, git, gh, ffmpeg, lark-cli, ...) |
| pip packages | 30 tracked + 331 full (unfiltered dump) |
| npm global | All `-g` packages with versions |
| Claude extensions | 58 skills, 12 plugins, 2 MCP servers, 21 agents |
| Known projects | 29 projects with tech stacks + active-since dates |
| OS | Windows 11 AMD64 |

## Why

**Existing tools scan one layer** (Claude Code plugins / MCP / skills). **None scan system-level (pip, npm, PATH) + project-level together**, and **none feed the result into the agent's design decision loop.**

env-inventory isn't a diagnostic tool — it's a **decision-support tool**. The agent loads the skill during "design a new project" / "install a new tool" and answers: *"Before I suggest X — do you already have it?"*

## Install

```bash
git clone https://github.com/wuykjl/env-inventory.git
mkdir -p ~/.claude/skills/env-inventory ~/.claude/tools
cp env-inventory/SKILL.md ~/.claude/skills/env-inventory/skill.md
cp env-inventory/scan-env.py ~/.claude/tools/scan-env.py
```

### Customize for your machine

Edit `scan-env.py` — change these lines to match your project roots:

```python
WORK_ROOTS = [
    Path("E:/qoder work"),
    Path("E:/codex work"),
    Path("E:/cursor work"),
    Path.home() / "Documents" / "trae_projects",
]
```

Then run once:

```bash
python ~/.claude/tools/scan-env.py
```

## Smart refresh

The scanner auto-skips if the inventory is less than 24 hours old. Force refresh: delete `~/.claude/env-inventory.md` first.

## Optimizations (2026-06-13)

| # | Optimization | Why |
|---|-------------|-----|
| 1 | **Expanded trigger surface** | Now activates on `pip install` / `dependency conflict` queries — not just "design new project" |
| 2 | **Full pip dump** | Unfiltered reference appended as `## Full pip Package Reference` — enables dependency conflict checks |
| 3 | **File scan cap** | Max 50 .py files per project (was unbounded — 500-file projects caused stalls) |
| 4 | **Freshness dates** | Each project shows `(active: YYYY-MM-DD)` from `git log` or newest file |
| 5 | **24h cooldown** | Skip refresh if inventory is < 24h old — saves 5s on high-frequency invocations |
| 6 | **Rulehook-ready** | Rulehook can add a `redundant-dependency` rule: "Did you check env-inventory before installing?" |

## Ecosystem

**[rulehook](https://github.com/wuykjl/rulehook)** — env-inventory's enforcement partner. When the agent runs `pip install X`, rulehook checks: "Was the inventory consulted first? Is X already available?"

Together: `env-inventory` tells the agent what it has. `rulehook` makes sure the agent reads it before acting.

## Limitations

- **Machine-specific paths** — work roots and tool paths are hardcoded for the author's Windows setup. Edit before use.
- **Non-Windows untested** — `scan_cli_tools()` calls `shutil.which()` which is cross-platform, but `WORK_ROOTS` are Windows paths.
- **Pip scan is pip-list based** — doesn't detect conda/brew/choco packages.

## License

MIT
