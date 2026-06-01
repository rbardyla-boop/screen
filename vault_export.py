#!/usr/bin/env python3
"""
vault_export.py — Institutional Vulnerability mitigation + Agent Integration

Serializes the Memory/ layer into portable formats.

Usage:
    python vault_export.py                                    # normal tar.gz export
    python vault_export.py --output ~/Backups/Memory-Export-2026-06-01.tar.gz

    # New: Structured export for AI agents (open loops, guardrails, memory classes as native data)
    python vault_export.py --structured
    python vault_export.py --for-agents --output ~/Backups/vault-for-agents.json

The --structured / --for-agents flag produces a rich JSON snapshot that external
discovery agents (e.g. caitlin-brain) can consume as first-class primitives
instead of raw text. This is the bridge for deeper architectural integration.
"""

import argparse
import os
import tarfile
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VAULT_PATH = Path(os.environ.get("VAULT_PATH", "/home/thebackhand/Documents/Obsidian Vault"))


def export_memory(vault: Path, output_path: Path | None = None) -> Path:
    """Export Memory/ layer to a compressed tar archive."""
    memory_dir = vault / "Memory"
    if not memory_dir.exists():
        raise FileNotFoundError(f"Memory/ directory not found at {memory_dir}")

    today = date.today().isoformat()
    if output_path is None:
        export_dir = Path.home() / "Backups" / "Vault-Memory"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / f"Memory-Export-{today}.tar.gz"

    print(f"Exporting Memory/ → {output_path}")

    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(str(memory_dir), arcname="Memory")

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"✅ Export complete ({size_mb:.1f} MB)")
    print(f"   Location: {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Memory/ layer (and optionally structured primitives for AI agents)")
    parser.add_argument("--output", type=Path, help="Custom output path (.tar.gz)")
    parser.add_argument(
        "--structured", "--for-agents", action="store_true",
        help="Also (or only) export a rich JSON snapshot of open loops, guardrails, and memory class policies for AI agents"
    )
    args = parser.parse_args()

    try:
        if args.structured:
            from vault_primitives import export_structured_for_agents
            out = export_structured_for_agents(VAULT_PATH)
            print(f"\n✅ Structured agent export ready: {out}")
            print("   This is the preferred format for deep integration with caitlin-brain / external agents.")

        if not args.structured or args.output:
            export_path = export_memory(VAULT_PATH, args.output)
            print("\nFalsification test ready:")
            print("   1. Delete or rename Memory/ folder")
            print("   2. Extract the .tar.gz")
            print("   3. Verify all notes, skills, dashboards, and structure are intact")

    except Exception as e:
        print(f"❌ Export failed: {e}")
        exit(1)


if __name__ == "__main__":
    main()
