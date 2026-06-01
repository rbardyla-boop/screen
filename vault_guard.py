#!/usr/bin/env python3
"""
vault-guard.py — The ruthless cop that prevents your second brain from ever becoming a 48GB tar pit again.

This script is the enforcement layer. It must be called (or imported) by every other tool that touches the vault.

Rules (non-negotiable):
- No dev workspaces, venvs, node_modules, .git history, large builds, or video/media dumps inside the vault.
- 00_Inbox is a *temporary conversion drop zone only*. It must stay tiny.
- The Memory/ core must remain small and fast (< 1000 files total in the whole sacred surface).
- Any violation → loud failure + instructions + optional auto-quarantine.

Run manually:
    python vault-guard.py --audit
    python vault-guard.py --enforce

Exit codes:
  0 = clean
  1 = warnings (soft)
  2 = hard violations (scripts should refuse to proceed)
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# --- CONFIG (tune only if you have an extremely good reason) ---
VAULT_PATH = os.environ.get("VAULT_PATH", "")
if not VAULT_PATH:
    print("FATAL: VAULT_PATH not set in environment")
    sys.exit(2)

VAULT = Path(VAULT_PATH)

# Hard limits
MAX_INBOX_SIZE_MB = 500          # 00_Inbox total must stay under this
MAX_INBOX_FILES = 2000           # Rough cap on total files in inbox tree
MAX_MEMORY_SIZE_MB = 150         # Memory/ core must stay tiny and fast
MAX_SINGLE_FILE_MB = 25          # Nothing huge should ever land in inbox

# Toxic patterns that are *never* allowed inside the vault
TOXIC_PATTERNS = [
    "venv/", ".venv/", "env/", "ENV/",
    "node_modules/",
    ".git/objects/",  # full history, not just .git/ (we allow small .git for notes sometimes)
    "__pycache__/",
    ".mypy_cache/", ".ruff_cache/",
    "build/", "dist/", "target/", "out/",
    "automation/",  # often contains the real heavy lifting
    ".cache/",
]

# File extensions that are almost always wrong in a knowledge vault
TOXIC_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",  # video
    ".pt", ".bin", ".safetensors", ".gguf",   # large model weights
    ".iso", ".dmg", ".img",
}

# Directories we watch especially closely
CRITICAL_PATHS = [
    VAULT / "00_Inbox",
    VAULT / "Memory",
    VAULT,  # root
]

# --- Helpers ---

def human(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"

def find_toxic_items(root: Path, max_depth: int = 4) -> list[dict]:
    """Walk and report anything that looks like a dev workspace or toxic bulk."""
    findings = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)

        if depth > max_depth:
            dirnames[:] = []
            continue

        dirpath_str = str(dirpath) + "/"

        # Claude Code tool-config trees (.claude/) are exempt from the directory-NAME
        # toxic check: skills legitimately carry slugs like "build"/"dist"/"out", and
        # Python hooks regenerate __pycache__ on every run. This is tool config, not
        # knowledge content, so it cannot bloat the vault into a tar pit. Media/model
        # extension checks and vault-size totals below still apply here.
        in_claude_config = ".claude" in rel.parts

        # Check for toxic directory names
        if not in_claude_config:
            for pattern in TOXIC_PATTERNS:
                if pattern in dirpath_str:
                    findings.append({
                        "type": "toxic_dir",
                        "path": str(dirpath),
                        "reason": f"matches toxic pattern '{pattern}'",
                        "size": None,
                    })
                    # Don't descend into obvious venvs etc.
                    dirnames[:] = []
                    break

        # Check for toxic file extensions at this level (sample)
        toxic_files = [f for f in filenames if Path(f).suffix.lower() in TOXIC_EXTENSIONS]
        if toxic_files and len(toxic_files) > 3:
            findings.append({
                "type": "toxic_files",
                "path": str(dirpath),
                "reason": f"{len(toxic_files)} files with toxic extensions (video/models)",
                "examples": toxic_files[:3],
            })

    return findings


def measure_tree(path: Path) -> dict:
    """Return size + file count for a directory tree."""
    total_size = 0
    file_count = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = Path(dirpath) / f
                try:
                    total_size += fp.stat().st_size
                    file_count += 1
                except:
                    pass
    except Exception as e:
        return {"error": str(e)}

    return {
        "size_bytes": total_size,
        "size_human": human(total_size),
        "file_count": file_count,
    }


def audit_inbox() -> list[dict]:
    """Special ruthless audit of the inbox — this was the original failure point."""
    inbox = VAULT / "00_Inbox"
    if not inbox.exists():
        return []

    issues = []
    stats = measure_tree(inbox)

    if stats.get("size_bytes", 0) > MAX_INBOX_SIZE_MB * 1024 * 1024:
        issues.append({
            "severity": "CRITICAL",
            "msg": f"00_Inbox is {stats['size_human']} (limit {MAX_INBOX_SIZE_MB}MB). This is how the 48GB disaster started.",
            "action": "Evict large subfolders to ~/Projects/ immediately. Inbox is for temporary document conversion only."
        })

    if stats.get("file_count", 0) > MAX_INBOX_FILES:
        issues.append({
            "severity": "HIGH",
            "msg": f"00_Inbox has {stats['file_count']} files (soft limit {MAX_INBOX_FILES}).",
            "action": "Archive or organize. Flat or deep dumping is banned."
        })

    # Look for any remaining large subdirs inside inbox.
    # "Archive" is exempt — it's the watcher's own converted-document output folder.
    for child in inbox.iterdir():
        if child.is_dir() and child.name != "Archive":
            child_stats = measure_tree(child)
            if child_stats.get("size_bytes", 0) > 100 * 1024 * 1024:  # 100MB
                issues.append({
                    "severity": "HIGH",
                    "msg": f"Large folder still inside inbox: {child.name} ({child_stats['size_human']})",
                    "action": "Move to ~/Projects/ or proper archive location outside the vault."
                })

    return issues


def audit_memory() -> list[dict]:
    """Memory/ core must stay small and sacred."""
    mem = VAULT / "Memory"
    if not mem.exists():
        return [{"severity": "MEDIUM", "msg": "Memory/ folder does not exist. You broke the only part that matters.", "action": "Recreate it from the template."}]

    stats = measure_tree(mem)
    issues = []

    if stats.get("size_bytes", 0) > MAX_MEMORY_SIZE_MB * 1024 * 1024:
        issues.append({
            "severity": "HIGH",
            "msg": f"Memory/ core is {stats['size_human']} (limit {MAX_MEMORY_SIZE_MB}MB). It must stay tiny.",
            "action": "You are letting the memory surface bloat. Close loops harder."
        })

    if stats.get("file_count", 0) > 800:
        issues.append({
            "severity": "MEDIUM",
            "msg": f"Memory/ has {stats['file_count']} files. The goal is ruthless focus, not another archive.",
        })

    return issues


def run_audit(strict: bool = False) -> int:
    """Full audit. Returns worst exit code seen."""
    print("=== VAULT GUARD AUDIT ===")
    print(f"Vault: {VAULT}")
    print(f"Time: {datetime.now().isoformat()}\n")

    exit_code = 0
    all_issues = []

    # Inbox (the original sin)
    inbox_issues = audit_inbox()
    if inbox_issues:
        print("!! 00_INBOX VIOLATIONS (this is what killed you before)")
        for i in inbox_issues:
            print(f"  [{i['severity']}] {i['msg']}")
            print(f"           → {i['action']}")
            all_issues.append(i)
            if i["severity"] == "CRITICAL":
                exit_code = max(exit_code, 2)
            elif i["severity"] == "HIGH":
                exit_code = max(exit_code, 1)

    # Memory core
    mem_issues = audit_memory()
    if mem_issues:
        print("\n!! MEMORY CORE ISSUES")
        for i in mem_issues:
            print(f"  [{i['severity']}] {i['msg']}")
            if "action" in i: print(f"           → {i['action']}")
            all_issues.append(i)

    # Toxic pattern scan on critical paths
    for crit in CRITICAL_PATHS:
        if crit.exists():
            toxics = find_toxic_items(crit, max_depth=5)
            if toxics:
                print(f"\n!! TOXIC PATTERNS DETECTED under {crit.relative_to(VAULT)}")
                for t in toxics[:10]:
                    print(f"  - {t['path']}: {t['reason']}")
                if len(toxics) > 10:
                    print(f"  ... and {len(toxics)-10} more")
                exit_code = max(exit_code, 2 if strict else 1)

    # Whole vault size sanity (soft)
    vault_stats = measure_tree(VAULT)
    print(f"\n--- Vault totals ---")
    print(f"Size: {vault_stats.get('size_human', '?')}")
    print(f"Files: {vault_stats.get('file_count', '?')}")

    if vault_stats.get("size_bytes", 0) > 10 * 1024 * 1024 * 1024:  # 10GB warning
        print("WARNING: Vault > 10GB. You are drifting back toward the old failure mode.")

    if all_issues:
        print("\n=== AUDIT SUMMARY ===")
        print(f"Total issues: {len(all_issues)}")
    else:
        print("\n✓ Vault looks healthy under current ruthless rules.")

    return exit_code


if __name__ == "__main__":
    strict = "--enforce" in sys.argv or "--strict" in sys.argv
    code = run_audit(strict=strict)
    sys.exit(code)
