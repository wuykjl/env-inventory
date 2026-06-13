---
name: env-inventory
description: When designing new software, making tech choices, or planning architecture — automatically loads the local environment inventory and recommends reusing already-installed tools/SDKs/frameworks/project patterns instead of introducing new things. Triggers BEFORE acting: 设计软件、新项目、技术选型、架构设计、搭建、开发一个、build a、create a、design a、安装工具、装一个、pip install、npm install、已装了什么、what's already installed、already have、环境扫描、env scan. Note: dependency CONFLICTS (依赖冲突, version conflict) are post-hoc — rulehook's redundant-dependency rule handles pre-install prevention.
---

# Environment Inventory Skill

## Purpose

Load the local environment inventory so I can recommend reusing already-installed tools, SDKs, frameworks, and existing project patterns — **before** suggesting anything new.

## When this triggers (expanded 2026-06-13)

**Design/planning mode** (original):
- 设计一个新软件 / 项目 / 系统
- 技术选型 · 搭建一个 XXX · 开发一个 XXX
- 架构设计 · I want to build / create / design a new ...

**Dependency/conflict mode** (NEW):
- "装一个 XXX" · "pip install" · "npm install"
- "这个库能用吗" · "有没有 XXX 的替代"
- "dependency conflict" · "version mismatch"
- "我已经有 XXX 了吗" · "已装了什么"
- "what's already installed" · "already have"

## How to Use

### Step 1: Refresh (smart — skips if < 24h old)

```bash
python "C:\Users\wuyu\.claude\tools\scan-env.py"
```

The scanner auto-skips if inventory is less than 24 hours old. Force refresh: delete `C:\Users\wuyu\.claude\env-inventory.md` first.

### Step 2: Read and cross-reference

Read `C:\Users\wuyu\.claude\env-inventory.md`. Use it to:

1. **Check what's already installed** before suggesting new tools
2. **Prefer existing over new** — if FastAPI is installed, don't suggest Express; if PyMuPDF is installed, don't suggest a new PDF library
3. **Cross-reference with known projects** — if the user wants PDF OCR, point to `pdf_ocr_renamer` patterns; for pipeline processing, point to `jicai/pipeline`
4. **Identify gaps** — only suggest new tools when nothing in inventory fits
5. **Detect dependency conflicts** — use the full pip dump section to spot version mismatches before they cause problems

### Step 3: Reuse-first recommendations

```
🏗️ Already available (install-free):
  - Backend: FastAPI 0.135 + Django 6.0
  - LLM: DeepSeek via Anthropic SDK proxy
  - PDF: PyMuPDF 1.27 + RapidOCR 3.8
  - Feishu: lark-cli + 24+ skills

📦 Available but may need updates:
  - ...

🆕 Suggested additions (not in inventory):
  - ...
```

### Step 4: Rulehook integration

When suggesting a new pip/npm install, **rulehook** (https://github.com/wuykjl/rulehook) checks:
- "Did you check env-inventory before installing?"
- "Is an equivalent already available?"

If violated: systemMessage reminder.

## Inventory Categories

| Section | Content |
|---------|---------|
| AI/LLM APIs | Configured endpoints, SDKs, models |
| Frameworks | Major web/data/OCR/CV/media/automation packages |
| CLI Tools | Installed command-line tools |
| Global npm | Node.js global packages |
| Claude Extensions | Skills, MCP servers, custom agents, plugins |
| Known Projects | All codebases with tech stacks + freshness dates |
| Full pip Reference | Unfiltered dump for dependency conflict checks |

## Anti-Patterns

- ❌ Suggesting a new library when an equivalent is already installed
- ❌ Ignoring existing projects that overlap with the new design
- ❌ Recommending a framework the user doesn't use when they have an existing stack
- ❌ Forgetting about lark-cli and Feishu skills for integrations
- ❌ Proposing scrapers without checking compliance tier (see x-crawl skill)

## Freshness (2026-06-13)

- Scanner auto-skips if inventory < 24h old
- Each project shows `(active: YYYY-MM-DD)` from git log or newest file
- Full pip dump enables dependency conflict detection without re-running pip

## Related

- `superpowers:brainstorming` — use env-inventory during brainstorming
- [`rulehook`](https://github.com/wuykjl/rulehook) — enforces "check inventory before installing" rule
- [`everything-cli-anything`](https://github.com/wuykjl/everything-cli-anything) — find project files by name across all disks
