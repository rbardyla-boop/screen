"""Unit tests for vault_night_operator clippings organizer."""
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vault_night_operator import organize_clippings, parse_frontmatter


def _clip(dirp: Path, name: str, source: str, created: str, body: str = "x") -> Path:
    """Write a minimal Web-Clipper-style note into dirp."""
    p = dirp / name
    p.write_text(
        f'---\ntitle: "{name[:-3]}"\nsource: "{source}"\n'
        f'created: {created}\ntags:\n  - "clippings"\n---\n{body}\n',
        encoding="utf-8",
    )
    return p


def test_quarantines_reclips_and_writes_index():
    """Re-clips ('X' / 'X 1') of one page collapse to one; the larger copy is kept."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        clips = vault / "Clippings"
        clips.mkdir()
        # Web Clipper names re-clips of the same page Title.md / Title 1.md;
        # trailing slash in source must normalize equal.
        _clip(clips, "Article A.md", "https://example.com/a", "2026-06-01", body="short")
        _clip(clips, "Article A 1.md", "https://example.com/a/", "2026-06-02",
              body="a substantially longer body that should be kept as canonical")
        _clip(clips, "Article B.md", "https://example.com/b", "2026-06-03")

        result = organize_clippings(vault, dry_run=False)

        assert result["present"] is True
        assert result["total"] == 3
        assert result["unique"] == 2            # the two A re-clips collapse to one
        assert result["duplicates_moved"] == 1
        # the larger copy stays in place; the smaller is quarantined
        assert (clips / "Article A 1.md").exists()
        assert not (clips / "Article A.md").exists()
        assert (clips / "_Duplicates" / "Article A.md").exists()
        # index lists kept clips and the quarantine count
        index = (clips / "_Index.md").read_text(encoding="utf-8")
        assert "Clippings — 2 notes" in index
        assert "Quarantined duplicates (1)" in index


def test_distinct_clips_sharing_generic_source_are_kept():
    """Two different pages that share a generic source (e.g. x.com/home) are NOT merged."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        clips = vault / "Clippings"
        clips.mkdir()
        _clip(clips, "Post by @DamiDefi on X.md", "https://x.com/home", "2026-06-01")
        _clip(clips, "Post by @Eljaboom on X.md", "https://x.com/home", "2026-06-02")

        result = organize_clippings(vault, dry_run=False)

        assert result["unique"] == 2            # different base titles → both kept
        assert result["duplicates_moved"] == 0
        assert not (clips / "_Duplicates").exists()


def test_dry_run_moves_and_writes_nothing():
    """A dry run reports the would-be quarantine but touches no files."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        clips = vault / "Clippings"
        clips.mkdir()
        _clip(clips, "X.md", "https://e.com/x", "2026-06-01")
        _clip(clips, "X 1.md", "https://e.com/x", "2026-06-02")

        result = organize_clippings(vault, dry_run=True)

        assert result["duplicates_moved"] == 1          # computed, not performed
        assert (clips / "X.md").exists()
        assert (clips / "X 1.md").exists()
        assert not (clips / "_Duplicates").exists()
        assert not (clips / "_Index.md").exists()


def test_idempotent_second_run_quarantines_nothing_new():
    """Running twice is stable: the second pass finds no new duplicates."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        clips = vault / "Clippings"
        clips.mkdir()
        _clip(clips, "Report.md", "https://e.com/a", "2026-06-01")
        _clip(clips, "Report 1.md", "https://e.com/a", "2026-06-02")

        first = organize_clippings(vault, dry_run=False)
        second = organize_clippings(vault, dry_run=False)

        assert first["duplicates_moved"] == 1
        assert second["duplicates_moved"] == 0          # nothing new to move
        # the quarantine section still reflects the standing duplicate
        index = (clips / "_Index.md").read_text(encoding="utf-8")
        assert "Quarantined duplicates (1)" in index


def test_missing_clippings_dir_is_noop():
    with tempfile.TemporaryDirectory() as tmp:
        result = organize_clippings(Path(tmp), dry_run=False)
        assert result == {"present": False}


def test_parse_frontmatter_ignores_nested_list_items():
    fm = parse_frontmatter(
        '---\ntitle: "T"\nsource: "https://s"\n'
        'author:\n  - "[[X]]"\ntags:\n  - "clippings"\n---\nbody'
    )
    assert fm["title"] == "T"
    assert fm["source"] == "https://s"
    assert fm.get("author") == ""   # nested "- [[X]]" not captured as the value
