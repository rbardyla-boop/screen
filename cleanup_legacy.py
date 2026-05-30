"""
cleanup_legacy.py — Prune the 47GB legacy dump created on 2026-05-28.

Four phases, safe-by-default (--dry-run unless --execute is passed):

  Phase 1  Delete zero-risk build artifacts (video output, venvs, __pycache__)
  Phase 2  Check git remotes on repos — delete those with a remote, flag orphans
  Phase 3  Move creative writing dirs to ~/Documents/Writing/
  Phase 4  Write DECISION_NEEDED.md for remaining ambiguous dev projects

Usage:
    python cleanup_legacy.py           # dry-run (nothing is changed)
    python cleanup_legacy.py --execute # actually do it
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LEGACY_ROOT = Path.home() / "Projects" / "legacy-from-obsidian-vault" / "2026-05-28"
WRITING_DEST = Path.home() / "Documents" / "Writing"

# Phase 1 — specific paths to delete outright (zero unique value)
ARTIFACT_PATHS = [
    LEGACY_ROOT / "youtube_system" / "automation" / "output",
    LEGACY_ROOT / "youtube_system" / "automation" / "pipline",  # duplicate
]

# Phase 1 — directory names that are always build artifacts (recursively found).
# "env" is intentionally excluded — too broad, matches npm package subdirs like axios/lib/env.
# Named venvs (ocr_venv, lcb_env, etc.) are caught by _is_unnamed_venv() instead.
ARTIFACT_DIR_NAMES = {".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache"}


def _is_unnamed_venv(path: Path) -> bool:
    """Detect Python venvs that don't use standard names (.venv, venv, env).
    A directory is a venv if it has bin/activate AND lib/python*/site-packages."""
    if not path.is_dir():
        return False
    if (path / "bin" / "activate").exists():
        lib = path / "lib"
        if lib.is_dir():
            for child in lib.iterdir():
                if child.name.startswith("python") and (child / "site-packages").exists():
                    return True
    return False

# Phase 2 — directories we know have .git and should be checked for remotes
GIT_REPO_DIRS = [
    LEGACY_ROOT / "scp",
    LEGACY_ROOT / "Cognitive Guardian System (CGS)",
]

# Phase 3 — creative writing dirs to rescue (move to ~/Documents/Writing/)
WRITING_DIRS = [
    "book",
    "new book",
    "jans book",
    "novellas",
    "bruise",
    "inden",
    "war",
    "pendulum",
    "heart",
    "fem",
    "devil",
]

DRY_RUN = "--execute" not in sys.argv


def fmt_size(path: Path) -> str:
    """Return human-readable size via du -sh."""
    try:
        result = subprocess.run(
            ["du", "-sh", str(path)], capture_output=True, text=True, timeout=30
        )
        return result.stdout.split()[0] if result.stdout else "?"
    except Exception:
        return "?"


def last_modified(path: Path) -> str:
    try:
        mtime = max(f.stat().st_mtime for f in path.rglob("*") if f.is_file())
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        return "?"


def delete(path: Path, reason: str) -> None:
    size = fmt_size(path)
    if DRY_RUN:
        print(f"  [DRY-RUN] Would delete ({size}): {path}  —  {reason}")
    else:
        print(f"  Deleting ({size}): {path}  —  {reason}")
        shutil.rmtree(path)
        print(f"  Done.")


def move(src: Path, dest: Path) -> None:
    if DRY_RUN:
        print(f"  [DRY-RUN] Would move: {src} → {dest}")
    else:
        print(f"  Moving: {src} → {dest}")
        shutil.move(str(src), str(dest))
        print(f"  Done.")


# ---------------------------------------------------------------------------
# Phase 1 — zero-risk artifact deletion
# ---------------------------------------------------------------------------

def phase1() -> None:
    print("\n" + "=" * 70)
    print("PHASE 1 — Delete zero-risk build artifacts")
    print("=" * 70)

    # Specific known-bad paths first
    for path in ARTIFACT_PATHS:
        if path.exists():
            delete(path, "known artifact/output dir")
        else:
            print(f"  [SKIP] Already gone: {path}")

    # Walk the tree with os.walk pruning so we never recurse INTO a dir we plan to delete.
    # This is orders of magnitude faster than rglob on a large tree.
    writing_roots = {str(LEGACY_ROOT / name) for name in WRITING_DIRS}
    phase2_roots = {str(r) for r in GIT_REPO_DIRS}
    phase1_specific = {str(r) for r in ARTIFACT_PATHS}
    # All roots that Phase 1 should not descend into
    no_descend = writing_roots | phase2_roots | phase1_specific

    deduped: list[Path] = []

    for dirpath, dirnames, _ in os.walk(str(LEGACY_ROOT)):
        current = Path(dirpath)

        # Prune: remove dirs we won't descend into from os.walk's dirnames in-place
        to_prune: list[str] = []
        to_delete_here: list[str] = []

        for d in list(dirnames):
            child = current / d
            child_str = str(child)

            if child_str in no_descend:
                to_prune.append(d)
                continue

            if d in ARTIFACT_DIR_NAMES or _is_unnamed_venv(child):
                to_delete_here.append(d)
                to_prune.append(d)  # don't recurse further into it

        for d in to_prune:
            if d in dirnames:
                dirnames.remove(d)

        for d in to_delete_here:
            deduped.append(current / d)

    for path in deduped:
        if path.exists():
            delete(path, f"build artifact ({path.name}/)")


# ---------------------------------------------------------------------------
# Phase 2 — git remote check
# ---------------------------------------------------------------------------

def git_remote(repo: Path) -> str:
    """Return the remote URL string, or empty string if none."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def phase2() -> list[tuple[str, str]]:
    """Returns list of (dir_name, status) for the manifest."""
    print("\n" + "=" * 70)
    print("PHASE 2 — Git repos: check remote, delete if safe")
    print("=" * 70)

    results = []
    for repo in GIT_REPO_DIRS:
        if not repo.exists():
            print(f"  [SKIP] Not found: {repo}")
            results.append((repo.name, "ALREADY GONE"))
            continue

        remote = git_remote(repo)
        size = fmt_size(repo)

        if remote:
            print(f"  {repo.name} ({size}) — remote: {remote}")
            delete(repo, f"has remote at {remote}, safe to re-clone")
            results.append((repo.name, f"DELETED — remote: {remote}"))
        else:
            print(f"  WARNING: {repo.name} ({size}) — NO REMOTE found. Leaving in place.")
            print(f"    → You need to manually decide: keep, push somewhere, or delete.")
            results.append((repo.name, "ORPHANED — no remote, left in place"))

    return results


# ---------------------------------------------------------------------------
# Phase 3 — creative writing rescue
# ---------------------------------------------------------------------------

def phase3() -> None:
    print("\n" + "=" * 70)
    print("PHASE 3 — Move creative writing dirs to ~/Documents/Writing/")
    print("=" * 70)

    if not DRY_RUN:
        WRITING_DEST.mkdir(parents=True, exist_ok=True)

    for name in WRITING_DIRS:
        src = LEGACY_ROOT / name
        dest = WRITING_DEST / name

        if not src.exists():
            print(f"  [SKIP] Not found: {src}")
            continue

        if dest.exists():
            print(f"  [SKIP] Destination already exists: {dest}")
            continue

        move(src, dest)


# ---------------------------------------------------------------------------
# Phase 4 — decision manifest for remaining dirs
# ---------------------------------------------------------------------------

def phase4(git_results: list[tuple[str, str]]) -> None:
    print("\n" + "=" * 70)
    print("PHASE 4 — Generate DECISION_NEEDED.md for remaining dirs")
    print("=" * 70)

    # Collect dirs still present after phases 1-3
    skip_names = set(WRITING_DIRS) | {r.name for r in GIT_REPO_DIRS} | {"MANIFEST_AND_WARNING.md"}
    remaining = sorted(
        [d for d in LEGACY_ROOT.iterdir() if d.is_dir() and d.name not in skip_names],
        key=lambda d: -d.stat().st_size if d.exists() else 0,
    )

    rows = []
    for d in remaining:
        if not d.exists():
            continue
        has_git = (d / ".git").exists()
        size = fmt_size(d)
        modified = last_modified(d)
        remote = git_remote(d) if has_git else ""
        if has_git and remote:
            rec = f"Has remote ({remote}) — safe to delete"
        elif has_git:
            rec = "Orphaned git repo — push or delete manually"
        elif size in ("?",) or size.endswith("K") or (size.endswith("M") and float(size[:-1]) < 50):
            rec = "Small — review and delete or keep"
        else:
            rec = "LARGE — decide: delete, archive, or move to ~/Projects/"
        rows.append((d.name, size, "yes" if has_git else "no", modified, rec))

    lines = [
        "# Decision Needed — Remaining Legacy Dirs\n",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n",
        "These directories were NOT automatically handled. Each needs a deliberate decision.\n\n",
        "## Phase 2 Git Repo Results\n\n",
    ]
    for name, status in git_results:
        lines.append(f"- **{name}**: {status}\n")

    lines += [
        "\n## Remaining Dev Directories\n\n",
        "| Directory | Size | Has .git | Last Modified | Recommendation |\n",
        "|-----------|------|----------|---------------|----------------|\n",
    ]
    for name, size, git, mod, rec in rows:
        lines.append(f"| {name} | {size} | {git} | {mod} | {rec} |\n")

    lines += [
        "\n## Options per directory\n\n",
        "- **Delete**: `rm -rf ~/Projects/legacy-from-obsidian-vault/2026-05-28/<dir>`\n",
        "- **Keep**: Move to `~/Projects/<dir>` if you're actively using it\n",
        "- **Archive**: Zip it, move to external drive or cold storage\n",
        "\nIf you haven't touched something since before 2026-04-01, delete it.\n",
    ]

    out = LEGACY_ROOT / "DECISION_NEEDED.md"
    content = "".join(lines)

    if DRY_RUN:
        print(f"  [DRY-RUN] Would write: {out}")
        print()
        print(content)
    else:
        out.write_text(content, encoding="utf-8")
        print(f"  Written: {out}")
        print(f"  {len(rows)} directories need your decision.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not LEGACY_ROOT.exists():
        print(f"ERROR: Legacy root not found: {LEGACY_ROOT}")
        sys.exit(1)

    mode = "DRY-RUN (no changes)" if DRY_RUN else "EXECUTE (changes will be made)"
    print(f"\ncleanup_legacy.py — {mode}")
    print(f"Legacy root: {LEGACY_ROOT}")
    initial_size = fmt_size(LEGACY_ROOT)
    print(f"Current size: {initial_size}\n")

    if DRY_RUN:
        print("Pass --execute to actually perform the cleanup.")

    phase1()
    git_results = phase2()
    phase3()
    phase4(git_results)

    print("\n" + "=" * 70)
    if DRY_RUN:
        print("DRY-RUN complete. No changes made.")
        print("Run with --execute to apply.")
    else:
        final_size = fmt_size(LEGACY_ROOT)
        print(f"Done. Size before: {initial_size}  →  after: {final_size}")
        print(f"Creative writing moved to: {WRITING_DEST}")
        print(f"Open DECISION_NEEDED.md for the remaining items.")
    print("=" * 70)


if __name__ == "__main__":
    main()
