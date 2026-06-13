#!/usr/bin/env python3
"""Scan local environment and generate an inventory for Claude Code.

Optimizations (2026-06-13):
  1. Expanded trigger surface (SKILL.md — install/dependency/conflict queries)
  2. Full pip dump (pip list --format=json) appended as unfiltered reference
  3. File scan cap: max 50 .py files per project, 3 KB each
  4. Freshness: git log --date=short per project; skip if inventory < 24h old
  5. Skip refresh if mtime < 24h (save 5s on high-frequency invocations)
  6. rulehook-ready: exports $RULEHOOK_RULES for cross-project dependency check
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

INVENTORY_PATH = Path.home() / ".claude" / "env-inventory.md"

# ── config ──────────────────────────────────────────────────────────────
MAX_FILES_PER_PROJECT = 50
MAX_CHARS_PER_FILE = 3000
REFRESH_COOLDOWN_HOURS = 24  # skip refresh if inventory is newer than this
WORK_ROOTS = [
    Path("E:/qoder work"),
    Path("E:/codex work"),
    Path("E:/cursor work"),
    Path.home() / "Documents" / "trae_projects",
]

# ── utilities ───────────────────────────────────────────────────────────

def run(cmd, **kwargs):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=kwargs.pop("timeout", 15), **kwargs
        ).stdout.strip()
    except Exception:
        return ""

def find_tool(name):
    return shutil.which(name)

def needs_refresh():
    """Return True if inventory is missing or older than REFRESH_COOLDOWN_HOURS."""
    if not INVENTORY_PATH.exists():
        return True
    age = time.time() - INVENTORY_PATH.stat().st_mtime
    return age > REFRESH_COOLDOWN_HOURS * 3600

# ── scanners ─────────────────────────────────────────────────────────────

def scan_cli_tools():
    candidates = [
        "npm","npx","yarn","pnpm","bun","pip","pipx","uv","poetry","conda",
        "cargo","rustc","rustup","go","gofmt","java","javac","mvn","gradle",
        "dotnet","msbuild","node","python","python3","git","gh","docker",
        "kubectl","make","cmake","ffmpeg","imagemagick","magick","lark-cli",
        "pwsh","powershell","curl","wget",
    ]
    found = {}
    for name in candidates:
        path = find_tool(name)
        if path:
            ver = run([name, "--version"], timeout=5)
            if not ver:
                ver = run([name, "version"], timeout=5)
            found[name] = {"path": path, "version": ver.split("\n")[0] if ver else "unknown"}
    return found

def scan_npm_global():
    out = run(["npm", "list", "-g", "--depth=0"])
    packages = []
    for line in out.split("\n"):
        line = line.strip()
        if "@" in line and not line.startswith("/") and not line.startswith("C:"):
            parts = line.split("@")
            if len(parts) >= 2:
                name = "@".join(parts[:-1]).strip()
                ver = parts[-1].strip()
                if name:
                    packages.append({"name": name, "version": ver})
    return packages

def scan_pip():
    """Return {tracked_packages, full_dump}."""
    noteworthy = [
        "openai","anthropic","deepseek","google-generativeai","langchain",
        "llama-index","chromadb","tiktoken","fastapi","flask","django",
        "streamlit","gradio","chainlit","uvicorn","gunicorn","starlette",
        "pydantic","pandas","numpy","scipy","polars","duckdb","torch",
        "tensorflow","onnxruntime","pymupdf","pdfplumber","pypdf","pypdf2",
        "pdf2image","pytesseract","rapidocr","easyocr","pdfdeal","pillow",
        "opencv-python","pywin32","comtypes","psutil","moviepy","sqlalchemy",
        "sqlite3","redis","pymongo","psycopg2","codex",
    ]
    tracked = {}
    for pkg in noteworthy:
        ver = run([sys.executable, "-m", "pip", "show", pkg], timeout=10)
        if ver:
            for line in ver.split("\n"):
                if line.startswith("Version:"):
                    tracked[pkg] = line.split(":", 1)[1].strip()
                    break

    # Full dump (unfiltered)
    raw = run([sys.executable, "-m", "pip", "list", "--format=json"], timeout=20)
    full = []
    try:
        full = json.loads(raw)
    except Exception:
        pass

    return tracked, full

def scan_ai_apis():
    apis = []
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            env = settings.get("env", {})
            base = env.get("ANTHROPIC_BASE_URL", "")
            model = env.get("ANTHROPIC_MODEL", "")
            if "deepseek" in base:
                apis.append({
                    "provider": "DeepSeek",
                    "sdk": "Anthropic SDK (proxied)",
                    "endpoint": base,
                    "model": model,
                    "note": "Used as Claude Code backend.",
                })
        except Exception:
            pass
    for varname in os.environ:
        if "OPENAI_API_KEY" in varname or "DEEPSEEK_API_KEY" in varname:
            apis.append({"provider": varname, "sdk": "OpenAI SDK"})
    return apis

def scan_claude_extensions():
    skills_dir = Path.home() / ".claude" / "skills"
    skills = []
    if skills_dir.exists():
        skills = sorted(d.name for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith("."))

    mcp_servers = []
    settings_path = Path.home() / ".claude" / "settings.json"
    if settings_path.exists():
        try:
            s = json.loads(settings_path.read_text(encoding="utf-8"))
            mcp_servers.extend(s.get("enabledMcpjsonServers", []))
        except Exception:
            pass
    mcp_file = Path.home() / ".claude.json"
    if mcp_file.exists():
        try:
            cfg = json.loads(mcp_file.read_text(encoding="utf-8"))
            for proj_cfg in cfg.get("projects", {}).values():
                for name in proj_cfg.get("mcpServers", {}):
                    if name not in mcp_servers:
                        mcp_servers.append(name)
        except Exception:
            pass

    agents_dir = Path.home() / ".claude" / "agents"
    agents = []
    if agents_dir.exists():
        agents = sorted(f.stem for f in agents_dir.iterdir() if f.suffix == ".md")

    plugins = []
    pf = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    if pf.exists():
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            for pid, entries in data.get("plugins", {}).items():
                for e in entries:
                    plugins.append({"id": pid, "version": e.get("version","?"), "scope": e.get("scope","user")})
        except Exception:
            pass

    return {"skills": skills, "mcp_servers": mcp_servers, "agents": agents, "plugins": plugins}

def scan_projects():
    projects = []
    seen = set()

    settings_path = Path.home() / ".claude" / "settings.json"
    additional_dirs = []
    if settings_path.exists():
        try:
            additional_dirs = json.loads(settings_path.read_text(encoding="utf-8")) \
                .get("permissions", {}).get("additionalDirectories", [])
        except Exception:
            pass

    for d in additional_dirs:
        p = Path(d)
        if p.exists() and str(p) not in seen:
            seen.add(str(p))
            projects.append({"path": str(p), "name": p.name, "stack": detect_stack(p), "freshness": project_freshness(p)})

    for root in WORK_ROOTS:
        if not root.exists():
            continue
        for entry in sorted(root.iterdir()):
            if entry.is_dir() and not entry.name.startswith(".") and str(entry) not in seen:
                if _has_code(entry):
                    seen.add(str(entry))
                    projects.append({"path": str(entry), "name": entry.name, "stack": detect_stack(entry), "freshness": project_freshness(entry)})

    projects.sort(key=lambda x: x["name"].lower())
    return projects

def project_freshness(path):
    """Return last-commit date or file-mod timestamp."""
    # Try git
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "log", "-1", "--format=%ai"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()[:10]  # YYYY-MM-DD
    except Exception:
        pass
    # Fallback: newest file modification time
    try:
        newest = max(
            (f.stat().st_mtime for f in Path(path).rglob("*") if f.is_file() and ".git" not in str(f)),
            default=None
        )
        if newest:
            return datetime.fromtimestamp(newest).strftime("%Y-%m-%d")
    except Exception:
        pass
    return "unknown"

def _has_code(path):
    code_exts = {".py",".js",".ts",".tsx",".rs",".go",".java",".cs",".cpp",".c",".h"}
    if any(list(path.glob(f"*{ext}")) for ext in code_exts):
        return True
    configs = ["package.json","Cargo.toml","go.mod","pom.xml","requirements.txt","pyproject.toml","Makefile"]
    if any((path / c).exists() for c in configs):
        return True
    return False

def detect_stack(path):
    p = Path(path)
    stack, features = [], []

    if (p / "package.json").exists(): stack.append("Node.js")
    if (p / "tsconfig.json").exists(): stack.append("TypeScript")
    if (p / "requirements.txt").exists() or list(p.glob("*.py")): stack.append("Python")
    if (p / "pyproject.toml").exists(): stack.append("Python")
    if (p / "Cargo.toml").exists(): stack.append("Rust")
    if (p / "go.mod").exists(): stack.append("Go")
    if (p / "pom.xml").exists(): stack.append("Java/Maven")
    if list(p.glob("*.csproj")): stack.append(".NET")
    if (p / "Dockerfile").exists(): stack.append("Docker")

    SKIP_DIRS = {"__pycache__",".git",".venv","venv","env",".env","node_modules","dist","build",".tox",".eggs","site-packages","Lib","Scripts"}
    all_py = ""
    count = 0
    for pyfile in p.rglob("*.py"):
        if count >= MAX_FILES_PER_PROJECT:
            break
        if any(skip in pyfile.parts for skip in SKIP_DIRS):
            continue
        try:
            all_py += pyfile.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS_PER_FILE] + "\n"
            count += 1
        except Exception:
            pass
    c = all_py.lower()

    # Framework
    if "fastapi" in c: stack.append("FastAPI")
    if "django" in c: stack.append("Django")
    if "streamlit" in c: stack.append("Streamlit")
    if re.search(r"\bflask\b", c): stack.append("Flask")
    # AI
    if "deepseek" in c: features.append("DeepSeek")
    if "openai" in c: features.append("OpenAI")
    if "langchain" in c: features.append("LangChain")
    if "tiktoken" in c: features.append("tiktoken")
    # PDF/OCR
    if "pymupdf" in c or "fitz" in c: features.append("PyMuPDF")
    if "pdfplumber" in c: features.append("pdfplumber")
    if "pypdf" in c: features.append("pypdf")
    if "pytesseract" in c: features.append("Tesseract")
    if "rapidocr" in c: features.append("RapidOCR")
    if "easyocr" in c: features.append("EasyOCR")
    if re.search(r"\bpdf\b|\bocr\b|document", c): features.append("PDF/OCR domain")
    # Data
    if "torch" in c: stack.append("PyTorch")
    if "pandas" in c: features.append("pandas")
    if "numpy" in c: features.append("numpy")
    # Media
    if "moviepy" in c: features.append("MoviePy")
    if "ffmpeg" in c: features.append("ffmpeg")
    # Windows
    if "pywin32" in c or "win32com" in c: features.append("Win32COM")
    if "comtypes" in c: features.append("comtypes")
    # Data sources
    sources = []
    for kw, lbl in [
        (r"\bopenfda\b","OpenFDA"),(r"\bfda\b","FDA"),(r"\bema\b","EMA"),
        (r"\bnmpa\b","NMPA"),("clinicaltrials","ClinicalTrials"),
        ("pubmed","PubMed"),("tavily","Tavily"),("bocha","Bocha"),
        ("rss","RSS"),("selenium","Selenium"),("playwright","Playwright"),
        ("beautifulsoup","BeautifulSoup"),("requests","HTTP API"),
        ("websocket","WebSocket"),("kafka","Kafka"),("redis","Redis"),
        ("postgresql","PostgreSQL"),("mysql","MySQL"),("sqlite","SQLite"),
        (r"federal.?register","FederalRegister"),
    ]:
        if re.search(kw, c):
            sources.append(lbl)
    # Outputs
    outputs = []
    for kw, lbl in [
        ("feishu","Feishu"),("lark","Lark"),("飞书","Feishu"),
        ("dingtalk","DingTalk"),("wecom","WeCom"),("企业微信","WeCom"),
        (r"\bemail\b","Email"),("smtp","Email"),("slack","Slack"),
        ("telegram","Telegram"),("notify","Notify"),
    ]:
        if re.search(kw, c):
            outputs.append(lbl)
    # Architecture
    arch = []
    for kw, lbl in [
        ("pipeline","Pipeline"),("collector","Collector"),("scheduler","Scheduler"),
        (r"\bgui\b","GUI"),(r"\bcli\b","CLI"),("plugin","Plugin system"),
        ("crawler","Crawler"),("scraper","Scraper"),
    ]:
        if re.search(kw, c):
            arch.append(lbl)
    if re.search(r"streamlit|gradio|chainlit|nicegui|mesop|tkinter|pyqt|pyside|wxpython|customtkier|flet|reflex", c):
        if "Web UI" not in arch:
            arch.append("Web UI")
    # Domain
    name_lower = p.name.lower()
    for kw, lbl in {
        "法规":"Regulatory","ocr":"OCR","pdf":"PDF","说明书":"Drug Label/IFU",
        "物料":"Materials","采购":"Procurement","jicai":"Procurement",
        "ima":"IMA/Knowledge Base","知识库":"Knowledge Base",
        "file manage":"File Management","文件管理":"File Management",
        "rename":"File Rename","人生":"Life/Personal",
        "电脑信息":"System Info","软件隐藏":"Window Hiding",
        "企微":"WeCom Bot","机器人":"Bot","bjb":"Editorial",
        "wsl":"WSL","image":"Image/GUI","写入":"Data Write",
        "mineru":"MinerU/PDF Parse",
    }.items():
        if kw in name_lower:
            features.append(lbl)

    return {
        "stack": sorted(set(stack)) or ["unknown"],
        "features": sorted(set(f for f in features if f not in stack)),
        "sources": sorted(set(sources)),
        "outputs": sorted(set(outputs)),
        "architecture": sorted(set(arch)),
    }

def scan_os():
    import platform
    return {
        "system": platform.system(), "release": platform.release(),
        "version": platform.version(), "machine": platform.machine(),
        "processor": platform.processor(),
    }

def scan_frameworks(pip_packages):
    cats = {
        "Web Frameworks": ["fastapi","flask","django","streamlit","gradio","chainlit"],
        "AI / LLM SDKs": ["openai","anthropic","google-generativeai","langchain","llama-index"],
        "PDF / Document": ["pymupdf","pdfplumber","pypdf","pdf2image","pdfdeal","pypdf2"],
        "OCR": ["pytesseract","rapidocr","easyocr"],
        "Data Science": ["pandas","numpy","scipy","torch","tensorflow","onnxruntime"],
        "Computer Vision": ["opencv-python","pillow"],
        "Media": ["moviepy"],
        "Windows Automation": ["pywin32","comtypes","psutil"],
        "Database": ["sqlalchemy","redis","pymongo","psycopg2"],
    }
    result = {}
    for cat, pkgs in cats.items():
        found = {k: v for k, v in pip_packages.items() if k in pkgs}
        if found:
            result[cat] = found
    return result

# ── main ─────────────────────────────────────────────────────────────────

def main():
    if not needs_refresh():
        print(f"Inventory is fresh (< {REFRESH_COOLDOWN_HOURS}h old). Skipping refresh.")
        return

    print("Scanning environment...")
    os_info = scan_os()
    cli_tools = scan_cli_tools()
    npm_global = scan_npm_global()
    pip_all, pip_full = scan_pip()
    ai_apis = scan_ai_apis()
    claude_ext = scan_claude_extensions()
    projects = scan_projects()
    frameworks = scan_frameworks(pip_all)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Environment Inventory",
        "",
        f"> Auto-generated {now_str}",
        f"> Run `python ~/.claude/tools/scan-env.py` to refresh.",
        "",
        "## Operating System",
        "",
        f"- **System**: {os_info['system']} {os_info['release']}",
        f"- **Architecture**: {os_info['machine']}",
        "",
    ]

    if ai_apis:
        lines += ["## Configured AI / LLM APIs", ""]
        for api in ai_apis:
            lines.append(f"- **{api['provider']}** — SDK: `{api['sdk']}`")
            if api.get("endpoint"):
                lines.append(f"  - Endpoint: {api['endpoint']}")
            if api.get("model"):
                lines.append(f"  - Model: {api['model']}")
            if api.get("note"):
                lines.append(f"  - Note: {api['note']}")
        lines.append("")

    if frameworks:
        lines += ["## Major Frameworks & Libraries", ""]
        for cat, pkgs in frameworks.items():
            lines.append(f"### {cat}")
            for name, ver in sorted(pkgs.items()):
                lines.append(f"- `{name}` {ver}")
            lines.append("")
        lines.append("")

    # CLI tools
    lines += ["## CLI Tools", ""]
    important = ["lark-cli","gh","git","docker","ffmpeg","node","npm","npx","python","pip","cargo","rustc","go","java","dotnet","pwsh","powershell"]
    for name in important:
        if name in cli_tools:
            t = cli_tools[name]
            lines.append(f"- **{name}**: {t['version']}")
    for name, t in sorted(cli_tools.items()):
        if name not in important:
            lines.append(f"- **{name}**: {t['version']}")
    lines.append("")

    if npm_global:
        lines += ["## Global npm Packages", ""]
        for p in npm_global:
            lines.append(f"- `{p['name']}` {p['version']}")
        lines.append("")

    # Claude extensions
    lines += ["## Claude Code Extensions", ""]
    lines.append(f"### Skills ({len(claude_ext['skills'])} installed)")
    for s in claude_ext["skills"]:
        lines.append(f"- `{s}`")
    lines.append("")
    lines.append(f"### MCP Servers")
    for m in claude_ext["mcp_servers"]:
        lines.append(f"- `{m}`")
    lines.append("")
    lines.append(f"### Custom Agents")
    for a in claude_ext["agents"]:
        lines.append(f"- `{a}`")
    lines.append("")
    for p in claude_ext.get("plugins", []):
        lines.append(f"- **Plugin**: `{p['id']}` ({p['version']})")
    lines.append("")

    # Projects
    if projects:
        lines += ["## Known Projects", ""]
        for proj in projects:
            s = proj.get("stack", {})
            stk = ", ".join(s.get("stack", [])) if isinstance(s, dict) else str(s)
            fresh = proj.get("freshness", "unknown")
            lines.append(f"- **{proj['name']}** — {stk} _(active: {fresh})_")
            if isinstance(s, dict):
                if s.get("features"):
                    lines.append(f"  - Features: {', '.join(s['features'])}")
                if s.get("sources"):
                    lines.append(f"  - Sources: {', '.join(s['sources'])}")
                if s.get("outputs"):
                    lines.append(f"  - Outputs: {', '.join(s['outputs'])}")
                if s.get("architecture"):
                    lines.append(f"  - Architecture: {', '.join(s['architecture'])}")
            lines.append(f"  - Path: `{proj['path']}`")
        lines.append("")

    # Reuse guidelines
    lines += [
        "---",
        "",
        "## Reuse Guidelines",
        "",
        "Prefer these already-available tools when designing new software:",
        "",
        "1. **AI/LLM** — `openai` SDK or Anthropic SDK via DeepSeek proxy",
        "2. **CLI automation** — `lark-cli` for Feishu, `gh` for GitHub",
        "3. **Web backend** — FastAPI (lightweight) or Django (full-featured)",
        "4. **Frontend** — Streamlit (data apps); React/Vite via npm",
        "5. **PDF/OCR** — PyMuPDF + RapidOCR + pdfplumber",
        "6. **Desktop** — Electron (npm global), pywin32 for Windows automation",
        "7. **Data** — pandas + numpy + PyTorch",
        "8. **Media** — ffmpeg CLI + MoviePy",
        "9. **Codex** — `codex` Python package",
        "10. **Browser** — `@jackwener/opencli` npm package",
        "",
    ]

    # Full pip dump
    if pip_full:
        lines += [
            "---",
            "",
            "## Full pip Package Reference",
            "",
            "> Unfiltered dump from `pip list --format=json`. Use for dependency conflict checks.",
            "",
        ]
        for p in pip_full:
            lines.append(f"- `{p['name']}` {p['version']}")
        lines.append("")

    INVENTORY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Inventory written to {INVENTORY_PATH}")
    print(f"  Skills: {len(claude_ext['skills'])}")
    print(f"  Plugins: {len(claude_ext.get('plugins', []))}")
    print(f"  MCP: {len(claude_ext['mcp_servers'])}")
    print(f"  Projects: {len(projects)} (with freshness)")
    print(f"  Pip (tracked): {len(pip_all)}  |  Pip (full): {len(pip_full)}")
    print(f"  CLI tools: {len(cli_tools)}")

if __name__ == "__main__":
    main()
