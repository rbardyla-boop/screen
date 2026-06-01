#!/usr/bin/env python3
"""
vault_sync.py — Distribute Memory exports across multiple machines
Syncs the latest Memory-Export to each configured target via rsync.

Usage:
    python vault_sync.py                           # Uses VAULT_SYNC_TARGETS env var
    python vault_sync.py --targets /tmp/backup1 /tmp/backup2
    python vault_sync.py --targets user@desktop1:/backup user@desktop2:/backup
    python vault_sync.py --dry-run                 # Show what would sync without doing it
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

BACKUPS_DIR = Path.home() / "Backups" / "Vault-Memory"
DEFAULT_TARGETS = os.environ.get("VAULT_SYNC_TARGETS", "").split(",")


def find_latest_export(backups_dir: Path) -> Path | None:
    """Find the most recent Memory-Export.tar.gz file."""
    if not backups_dir.exists():
        return None
    exports = sorted(backups_dir.glob("Memory-Export-*.tar.gz"), reverse=True)
    return exports[0] if exports else None


def sync_to_target(export_file: Path, target: str, dry_run: bool = False) -> bool:
    """Sync export file to a single target via rsync."""
    target = target.strip()
    if not target:
        return False

    # Ensure target ends with /
    if not target.endswith("/"):
        target += "/"

    cmd = ["rsync", "-av"]
    if dry_run:
        cmd.append("--dry-run")

    cmd.extend([str(export_file), target])

    try:
        print(f"→ Syncing to {target}...", end=" ", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print("✅")
            return True
        else:
            print(f"❌ (exit code {result.returncode})")
            if result.stderr:
                print(f"  Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ (timeout)")
        return False
    except Exception as e:
        print(f"❌ ({e})")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Distribute Memory exports to backup targets")
    parser.add_argument(
        "--targets",
        nargs="+",
        help="Rsync targets (local paths or user@host:/path). Overrides VAULT_SYNC_TARGETS env var",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be synced without doing it")
    args = parser.parse_args()

    targets = [t for t in (args.targets or DEFAULT_TARGETS) if t]
    if not targets:
        print("❌ No targets configured. Set VAULT_SYNC_TARGETS or pass --targets")
        sys.exit(1)

    export_file = find_latest_export(BACKUPS_DIR)
    if not export_file:
        print(f"❌ No Memory exports found in {BACKUPS_DIR}")
        sys.exit(1)

    print(f"📦 Export: {export_file.name} ({export_file.stat().st_size / (1024*1024):.1f} MB)")
    print(f"🎯 Targets: {len(targets)}")
    if args.dry_run:
        print("   [DRY RUN — no files will be copied]")
    print()

    results = []
    for target in targets:
        success = sync_to_target(export_file, target, dry_run=args.dry_run)
        results.append((target, success))

    # Summary
    print()
    passed = sum(1 for _, s in results if s)
    print(f"Summary: {passed}/{len(results)} targets synced successfully")

    if passed < len(results):
        print("\nFailed targets:")
        for target, success in results:
            if not success:
                print(f"  - {target}")
        sys.exit(1)


if __name__ == "__main__":
    main()
