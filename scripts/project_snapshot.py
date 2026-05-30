#!/usr/bin/env python3
"""Generate docs/LLM_CONTEXT_BRIEF.md for any git repo.

Usage (from within the target repo):
    python scripts/project_snapshot.py --write

Usage (bundled, targeting another repo):
    python /path/to/scripts/project_snapshot.py --repo /path/to/target --write

Without --write, prints to stdout.
"""
import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── file-type groups for stats ─────────────────────────────────────────────────
_CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".c", ".cpp", ".h",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".sh", ".bash", ".zsh",
}
_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".ruff_cache", "dist", "build", "target", ".next", ".nuxt", "coverage",
    ".pytest_cache",
}


def _git(repo: Path, *args: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _read_first_lines(path: Path, n: int = 10) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[:n])
    except Exception:
        return ""


def _dir_tree(root: Path, max_depth: int = 3, indent: str = "") -> list[str]:
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return lines
    for entry in entries:
        if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
            continue
        prefix = "├── " if entry != entries[-1] else "└── "
        if entry.is_dir():
            lines.append(f"{indent}{prefix}{entry.name}/")
            if max_depth > 1:
                lines.extend(_dir_tree(entry, max_depth - 1, indent + ("│   " if entry != entries[-1] else "    ")))
        else:
            lines.append(f"{indent}{prefix}{entry.name}")
    return lines


def _code_stats(root: Path) -> dict:
    totals: dict[str, int] = {}
    file_count = 0
    line_count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in _SKIP_DIRS]
        for fname in filenames:
            fp = Path(dirpath) / fname
            ext = fp.suffix.lower()
            if ext in _CODE_EXT:
                file_count += 1
                totals[ext] = totals.get(ext, 0) + 1
                try:
                    line_count += fp.read_text(
                        encoding="utf-8", errors="replace").count("\n")
                except Exception:
                    pass
    return {"files": file_count, "lines": line_count, "by_ext": totals}


def _detect_stack(repo: Path) -> list[str]:
    stack = []
    checks = [
        ("package.json",      "Node / JavaScript"),
        ("requirements.txt",  "Python (pip)"),
        ("pyproject.toml",    "Python (pyproject)"),
        ("Cargo.toml",        "Rust"),
        ("go.mod",            "Go"),
        ("pom.xml",           "Java / Maven"),
        ("build.gradle",      "Java / Gradle"),
        ("Gemfile",           "Ruby"),
        ("composer.json",     "PHP"),
        ("pubspec.yaml",      "Dart / Flutter"),
        ("CMakeLists.txt",    "C / C++ (CMake)"),
    ]
    for fname, label in checks:
        if (repo / fname).exists():
            stack.append(label)
    return stack


def _readme_excerpt(repo: Path, lines: int = 15) -> str:
    for name in ("README.md", "readme.md", "README.rst", "README"):
        p = repo / name
        if p.exists():
            return _read_first_lines(p, lines)
    return ""


def _recent_commits(repo: Path, n: int = 10) -> str:
    return _git(repo, "log", f"-{n}", "--oneline", "--no-decorate")


def _branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"


def _todo_count(repo: Path) -> int:
    count = 0
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in _SKIP_DIRS]
        for fname in filenames:
            fp = Path(dirpath) / fname
            if fp.suffix.lower() in _CODE_EXT:
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace").upper()
                    count += text.count("TODO") + text.count("FIXME")
                except Exception:
                    pass
    return count


def generate(repo: Path) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    name = repo.name
    branch = _branch(repo)
    stack = _detect_stack(repo)
    stats = _code_stats(repo)
    tree = _dir_tree(repo, max_depth=3)
    commits = _recent_commits(repo)
    readme = _readme_excerpt(repo)
    todos = _todo_count(repo)

    top_exts = sorted(stats["by_ext"].items(), key=lambda x: -x[1])[:5]
    ext_summary = "  ".join(f"{ext}:{n}" for ext, n in top_exts) or "—"

    sections = [
        f"# LLM Context Brief — {name}",
        f"\n> Generated {now}  ·  branch `{branch}`",
        "",
        "## Stack",
        "\n".join(f"- {s}" for s in stack) if stack else "_(not detected)_",
        "",
        "## Code Stats",
        f"- **{stats['files']}** source files",
        f"- **{stats['lines']:,}** lines",
        f"- Extensions: {ext_summary}",
        f"- TODOs/FIXMEs: {todos}",
        "",
        "## Directory Structure",
        "```",
        f"{name}/",
        *tree[:60],  # cap at 60 lines
        "```",
        "",
    ]

    if commits:
        sections += [
            "## Recent Commits",
            "```",
            commits,
            "```",
            "",
        ]

    if readme:
        sections += [
            "## README (excerpt)",
            "```",
            readme,
            "```",
            "",
        ]

    sections += [
        "---",
        f"_Written by project_snapshot.py — do not edit manually._",
    ]

    return "\n".join(sections) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLM context brief for a repo.")
    parser.add_argument("--repo", default=".", help="Path to target repo (default: cwd)")
    parser.add_argument("--write", action="store_true",
                        help="Write to docs/LLM_CONTEXT_BRIEF.md instead of stdout")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        sys.exit(f"ERROR: {repo} is not a directory")

    content = generate(repo)

    if args.write:
        out_dir = repo / "docs"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "LLM_CONTEXT_BRIEF.md"
        out_file.write_text(content, encoding="utf-8")
        print(f"Updated: {out_file}")
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
