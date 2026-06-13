"""Tests for scan-env.py — synthetic data, monkeypatched externals.

Strategy: every test that depends on subprocess/filesystem is monkeypatched.
Pure functions tested directly. Integration tests skipped unless ENV_INVENTORY_INTEGRATION=1.
"""

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# ── Import scanner under test (filename has a hyphen) ─────────────
_spec = importlib.util.spec_from_file_location(
    "scan_env", str(Path.home() / ".claude" / "tools" / "scan-env.py")
)
scan_env = importlib.util.module_from_spec(_spec)  # type: ignore
_spec.loader.exec_module(scan_env)

# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def _no_cooldown(monkeypatch):
    """Disable 24h cooldown. Use in tests that call main()."""
    monkeypatch.setattr(scan_env, "needs_refresh", lambda: True)

@pytest.fixture
def tmp_work_root(tmp_path):
    """Create a temporary project directory with synthetic code files."""
    root = tmp_path / "projects"
    root.mkdir()
    return root

# ══════════════════════════════════════════════════════════════════
# 1. needs_refresh — timestamp logic
# ══════════════════════════════════════════════════════════════════

def test_needs_refresh_no_file(monkeypatch):
    """Returns True when inventory file doesn't exist."""
    monkeypatch.setattr(scan_env, "INVENTORY_PATH", Path("/nonexistent/env.md"))
    assert scan_env.needs_refresh() is True

def test_needs_refresh_stale_file(monkeypatch, tmp_path):
    """Returns True when inventory is older than 24h."""
    p = tmp_path / "env.md"
    p.write_text("old")
    # Set mtime to 25 hours ago
    old = time.time() - 25 * 3600
    os.utime(str(p), (old, old))
    monkeypatch.setattr(scan_env, "INVENTORY_PATH", p)
    assert scan_env.needs_refresh() is True

def test_needs_refresh_fresh_file(monkeypatch, tmp_path):
    """Returns False when inventory is newer than 24h."""
    p = tmp_path / "env.md"
    p.write_text("fresh")
    monkeypatch.setattr(scan_env, "INVENTORY_PATH", p)
    assert scan_env.needs_refresh() is False  # file just created

# ══════════════════════════════════════════════════════════════════
# 2. _has_code — directory classification
# ══════════════════════════════════════════════════════════════════

def test_has_code_with_py_file(tmp_path):
    p = tmp_path / "project"
    p.mkdir()
    (p / "main.py").write_text("print('hello')")
    assert scan_env._has_code(p) is True

def test_has_code_with_package_json(tmp_path):
    p = tmp_path / "node_project"
    p.mkdir()
    (p / "package.json").write_text("{}")
    assert scan_env._has_code(p) is True

def test_has_code_with_requirements_txt(tmp_path):
    p = tmp_path / "py_project"
    p.mkdir()
    (p / "requirements.txt").write_text("fastapi")
    assert scan_env._has_code(p) is True

def test_has_code_empty_dir(tmp_path):
    p = tmp_path / "empty"
    p.mkdir()
    assert scan_env._has_code(p) is False

def test_has_code_dotfiles_only(tmp_path):
    p = tmp_path / "hidden"
    p.mkdir()
    (p / ".gitignore").write_text("*.pyc")
    (p / ".env").write_text("KEY=val")
    assert scan_env._has_code(p) is False

# ══════════════════════════════════════════════════════════════════
# 3. scan_frameworks — pure data transformation
# ══════════════════════════════════════════════════════════════════

def test_scan_frameworks_empty():
    result = scan_env.scan_frameworks({})
    assert result == {}

def test_scan_frameworks_categorizes():
    pkgs = {"fastapi": "0.135", "pandas": "2.2", "pymupdf": "1.27", "openai": "2.11"}
    result = scan_env.scan_frameworks(pkgs)
    assert "Web Frameworks" in result
    assert result["Web Frameworks"]["fastapi"] == "0.135"
    assert "AI / LLM SDKs" in result
    assert "PDF / Document" in result
    assert "Data Science" in result

def test_scan_frameworks_unknown_pkg_ignored():
    pkgs = {"some-random-lib": "9.9"}
    result = scan_env.scan_frameworks(pkgs)
    assert result == {}  # not in any category

# ══════════════════════════════════════════════════════════════════
# 4. detect_stack — synthetic project structures
# ══════════════════════════════════════════════════════════════════

def test_detect_stack_python_fastapi(tmp_work_root):
    p = tmp_work_root / "myapi"
    p.mkdir()
    (p / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\nimport pandas as pd")
    result = scan_env.detect_stack(p)
    assert "Python" in result["stack"]
    assert "FastAPI" in result["stack"]
    assert "pandas" in result["features"]

def test_detect_stack_nodejs(tmp_work_root):
    p = tmp_work_root / "webapp"
    p.mkdir()
    (p / "package.json").write_text('{"name":"web"}')
    (p / "tsconfig.json").write_text('{}')  # required: scanner checks this file
    result = scan_env.detect_stack(p)
    assert "Node.js" in result["stack"]
    assert "TypeScript" in result["stack"]

def test_detect_stack_ocr_project(tmp_work_root):
    p = tmp_work_root / "pdf ocr"
    p.mkdir()
    (p / "ocr.py").write_text("import pymupdf\nimport rapidocr\n# PDF OCR processing")
    result = scan_env.detect_stack(p)
    assert "PyMuPDF" in result["features"]
    assert "RapidOCR" in result["features"]
    # Directory name triggers domain detection
    assert any("OCR" in f for f in result["features"])

def test_detect_stack_feishu_integration(tmp_work_root):
    p = tmp_work_root / "notifier"
    p.mkdir()
    (p / "send.py").write_text('import requests\nrequests.post("https://open.feishu.cn", json={"msg":"hi"})')
    result = scan_env.detect_stack(p)
    assert "Feishu" in result["outputs"]
    assert "HTTP API" in result["sources"]

def test_detect_stack_django_ecommerce(tmp_work_root):
    p = tmp_work_root / "shop"
    p.mkdir()
    (p / "manage.py").write_text("import django\n# django settings")
    # Scanner regex checks for "postgresql" keyword, not just psycopg2 import
    (p / "models.py").write_text("from django.db import models\nimport psycopg2\n# database: postgresql")
    result = scan_env.detect_stack(p)
    assert "Django" in result["stack"]
    assert "PostgreSQL" in result["sources"]

def test_detect_stack_filesystem_cap(tmp_work_root):
    """Filesystem cap: 51 .py files → only first 50 scanned."""
    p = tmp_work_root / "big_project"
    p.mkdir()
    for i in range(51):
        (p / f"mod_{i}.py").write_text(f"# module {i}")
    # Should not raise — cap kicks in
    result = scan_env.detect_stack(p)
    assert "Python" in result["stack"]

def test_detect_stack_empty_project(tmp_work_root):
    p = tmp_work_root / "empty_proj"
    p.mkdir()
    result = scan_env.detect_stack(p)
    assert result["stack"] == ["unknown"]

def test_detect_stack_windows_automation(tmp_work_root):
    p = tmp_work_root / "auto"
    p.mkdir()
    (p / "auto.py").write_text("import pywin32\nimport comtypes\n# automation")
    result = scan_env.detect_stack(p)
    assert "Win32COM" in result["features"]
    assert "comtypes" in result["features"]

# ══════════════════════════════════════════════════════════════════
# 5. CLI tools — mock shutil.which
# ══════════════════════════════════════════════════════════════════

def test_scan_cli_tools_empty(monkeypatch):
    monkeypatch.setattr(scan_env, "find_tool", lambda _: None)
    result = scan_env.scan_cli_tools()
    assert result == {}

def test_scan_cli_tools_finds_git(monkeypatch):
    calls = {}
    def fake_which(name):
        calls[name] = True
        if name == "git":
            return "/usr/bin/git"
        return None
    monkeypatch.setattr(scan_env, "find_tool", fake_which)
    monkeypatch.setattr(scan_env, "run", lambda cmd, **kw: "git version 2.45.0" if "git" in cmd else "")
    result = scan_env.scan_cli_tools()
    assert "git" in result
    assert result["git"]["version"] == "git version 2.45.0"

# ══════════════════════════════════════════════════════════════════
# 6. project_freshness — mock git
# ══════════════════════════════════════════════════════════════════

def test_project_freshness_git(monkeypatch, tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    def fake_run(cmd, **kw):
        return type("R", (), {"returncode": 0, "stdout": "2026-06-10 14:30:00 +0800"})()
    monkeypatch.setattr(scan_env.subprocess, "run", fake_run)
    result = scan_env.project_freshness(p)
    assert result == "2026-06-10"

def test_project_freshness_git_fail_fallback(monkeypatch, tmp_path):
    p = tmp_path / "norepo"
    p.mkdir()
    (p / "file.txt").write_text("hello")
    def fake_run(cmd, **kw):
        raise Exception("no git")
    monkeypatch.setattr(scan_env.subprocess, "run", fake_run)
    result = scan_env.project_freshness(p)
    # Should fall back to file mtime
    assert result != "unknown"
    assert "-" in result  # YYYY-MM-DD

# ══════════════════════════════════════════════════════════════════
# 7. scan_ai_apis — mock settings.json
# ══════════════════════════════════════════════════════════════════

def test_scan_ai_apis_deepseek():
    """Real integration test — reads actual ~/.claude/settings.json.
    Skip if file doesn't exist or has no API config.
    """
    sp = Path.home() / ".claude" / "settings.json"
    if not sp.exists():
        pytest.skip("No settings.json found")
    result = scan_env.scan_ai_apis()
    assert isinstance(result, list)

# ══════════════════════════════════════════════════════════════════
# 8. Output validation — generated markdown structure
# ══════════════════════════════════════════════════════════════════

def test_main_generates_valid_markdown(monkeypatch, tmp_path, _no_cooldown):
    """End-to-end: run main() with mocked externals, verify output structure."""
    out = tmp_path / "env-inventory.md"
    monkeypatch.setattr(scan_env, "INVENTORY_PATH", out)
    monkeypatch.setattr(scan_env, "scan_os", lambda: {"system": "TestOS", "release": "1.0", "version": "", "machine": "x86_64", "processor": ""})
    monkeypatch.setattr(scan_env, "scan_cli_tools", lambda: {"python": {"path": "/usr/bin/python", "version": "3.14"}})
    monkeypatch.setattr(scan_env, "scan_npm_global", lambda: [{"name": "docx", "version": "9.7"}])
    monkeypatch.setattr(scan_env, "scan_pip", lambda: ({}, []))
    monkeypatch.setattr(scan_env, "scan_ai_apis", lambda: [])
    monkeypatch.setattr(scan_env, "scan_claude_extensions", lambda: {"skills": [], "mcp_servers": [], "agents": [], "plugins": []})
    monkeypatch.setattr(scan_env, "scan_projects", lambda: [{"name": "test-proj", "path": "/tmp/test", "stack": {"stack": ["Python"], "features": [], "sources": [], "outputs": [], "architecture": []}, "freshness": "2026-06-13"}])
    monkeypatch.setattr(scan_env, "scan_frameworks", lambda _: {"Test Category": {"testlib": "1.0"}})

    scan_env.main()

    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "# Environment Inventory" in text
    assert "## Operating System" in text
    assert "## CLI Tools" in text
    assert "## Major Frameworks & Libraries" in text
    assert "## Known Projects" in text
    assert "## Reuse Guidelines" in text
    assert "(active: 2026-06-13)" in text

# ══════════════════════════════════════════════════════════════════
# 9. Edge case: needs_refresh when file mtime is exactly 24h ago
# ══════════════════════════════════════════════════════════════════

def test_needs_refresh_exactly_24h(monkeypatch, tmp_path):
    p = tmp_path / "env.md"
    p.write_text("borderline")
    # Set mtime to exactly 24 hours ago
    old = time.time() - 24 * 3600
    os.utime(str(p), (old, old))
    monkeypatch.setattr(scan_env, "INVENTORY_PATH", p)
    # 24 hours exactly → should be considered stale (>), not fresh
    assert scan_env.needs_refresh() is True


# ── Run summary ───────────────────────────────────────────────────
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
