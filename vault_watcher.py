"""
vault_watcher.py — Watches 00_Inbox/ for PDFs and Word docs and converts them
to Markdown using pandoc/pdftotext (with Tesseract OCR fallback for scanned PDFs),
then archives the originals.

Usage:
    python vault_watcher.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

load_dotenv()

VAULT_PATH: str = os.environ.get("VAULT_PATH", "")
SUPPORTED: set[str] = {".pdf", ".docx", ".doc", ".odt", ".rtf"}
_EMPTY_THRESHOLD = 100  # bytes — below this, treat pdftotext output as effectively empty

# RUTHLESS GUARDRAILS — never again
MAX_SINGLE_FILE_MB = 30
TOXIC_DIR_NAMES = {"venv", ".venv", "node_modules", ".git", "build", "dist", "target", "__pycache__", "automation"}
TOXIC_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".pt", ".bin", ".safetensors", ".gguf", ".iso"}

def _is_toxic_drop(path: Path) -> tuple[bool, str]:
    """Return (is_toxic, reason) for anything that should never enter the inbox."""
    name_lower = path.name.lower()
    # Directories (if someone drops a whole folder somehow)
    if any(bad in name_lower for bad in TOXIC_DIR_NAMES):
        return True, f"contains toxic directory pattern '{name_lower}' (venv, node_modules, .git, automation, etc.)"
    if path.suffix.lower() in TOXIC_EXTS:
        return True, f"toxic file extension {path.suffix} (video / model weights / disk images)"
    try:
        if path.is_file() and path.stat().st_size > MAX_SINGLE_FILE_MB * 1024 * 1024:
            return True, f"file > {MAX_SINGLE_FILE_MB}MB — inbox is not a bulk storage dump"
    except:
        pass
    # Deep path check (someone dropped a subfolder with bad stuff)
    parts = [p.lower() for p in path.parts]
    for bad in TOXIC_DIR_NAMES:
        if bad in parts:
            return True, f"path contains toxic segment '{bad}'"
    return False, ""


def _ocr_pdf(src: Path, dest: Path) -> bool:
    """OCR a scanned PDF via pdftoppm + Tesseract. Returns True on success."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        r = subprocess.run(
            ["pdftoppm", "-r", "200", "-png", str(src), str(tmp / "page")],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(f"[watcher] pdftoppm failed for {src.name}: {r.stderr.strip()}")
            return False

        pages = sorted(tmp.glob("page-*.png"))
        if not pages:
            print(f"[watcher] No page images extracted from {src.name}")
            return False

        print(f"[watcher] OCR: processing {len(pages)} pages from {src.name} …")
        texts: list[str] = []
        for i, page in enumerate(pages, 1):
            r = subprocess.run(
                ["tesseract", str(page), "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0 and r.stdout.strip():
                texts.append(r.stdout.strip())
            if i % 10 == 0:
                print(f"[watcher]   … {i}/{len(pages)} pages done")

        if not texts:
            return False

        dest.write_text("\n\n---\n\n".join(texts), encoding="utf-8")
        return True


def convert_to_markdown(src: Path, out_dir: Path, archive_dir: Path) -> None:
    """Convert a document to Markdown, write to out_dir, move original to archive_dir."""
    stem = src.stem
    dest = out_dir / f"{stem}.md"
    archive = archive_dir / src.name

    # RUTHLESS PRE-FLIGHT — refuse to process toxic or oversized drops
    is_toxic, reason = _is_toxic_drop(src)
    if is_toxic:
        quarantine = archive_dir / "QUARANTINE" / src.name
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(quarantine))
        except:
            pass
        print(f"[GUARD] REFUSED + QUARANTINED: {src.name} — {reason}")
        print(f"[GUARD] This is how your previous 48GB disaster started. Do not repeat.")
        return

    try:
        if src.suffix.lower() == ".pdf":
            result = subprocess.run(
                ["pdftotext", "-layout", str(src), str(dest)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"[watcher] Conversion failed for {src.name}: {result.stderr.strip()}")
                return

            # Scanned PDFs produce near-empty output — fall back to Tesseract OCR
            if not dest.exists() or dest.stat().st_size < _EMPTY_THRESHOLD:
                print(f"[watcher] {src.name}: pdftotext output empty, trying Tesseract OCR …")
                dest.unlink(missing_ok=True)
                if not _ocr_pdf(src, dest):
                    print(f"[watcher] OCR also failed for {src.name} — skipping")
                    return
                print(f"[watcher] OCR complete: {src.name}")
        else:
            result = subprocess.run(
                ["pandoc", str(src), "-t", "markdown", "-o", str(dest)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"[watcher] Conversion failed for {src.name}: {result.stderr.strip()}")
                return

        shutil.move(str(src), str(archive))
        print(f"[watcher] Converted: {src.name} → {dest.name}  (original → Archive/)")

    except FileNotFoundError as e:
        print(f"[watcher] Missing tool — install pandoc, poppler-utils, and tesseract-ocr: {e}")
    except subprocess.TimeoutExpired:
        print(f"[watcher] Tesseract timed out on a page in {src.name} — partial output may exist")
    except Exception as e:
        print(f"[watcher] Unexpected error processing {src.name}: {e}")


class InboxHandler(FileSystemEventHandler):
    def __init__(self, inbox: Path, archive: Path) -> None:
        self.inbox = inbox
        self.archive = archive

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        if path.suffix.lower() not in SUPPORTED:
            return
        # Brief pause so the file finishes writing before we read it
        time.sleep(1)
        convert_to_markdown(path, self.inbox, self.archive)
        # After every drop, run a lightweight inbox sanity check (fast path)
        try:
            from vault_guard import audit_inbox
            issues = audit_inbox()
            if issues:
                print("[GUARD] Post-drop inbox audit found issues — review the output above.")
        except:
            pass


def main() -> None:
    if not VAULT_PATH:
        print("Error: VAULT_PATH is not set in .env")
        sys.exit(1)

    inbox = Path(VAULT_PATH) / "00_Inbox"
    archive = inbox / "Archive"
    inbox.mkdir(parents=True, exist_ok=True)
    archive.mkdir(parents=True, exist_ok=True)

    # === RUTHLESS STARTUP GUARD ===
    try:
        from vault_guard import run_audit  # type: ignore
        code = run_audit(strict=False)
        if code >= 2:
            print("\n[GUARD] Vault health check FAILED with critical violations.")
            print("Fix the problems above before running the watcher. This is non-negotiable.")
            sys.exit(2)
    except Exception:
        # If guard import fails we still continue — but log it
        print("[GUARD] Could not import vault-guard.py (continuing, but you should fix this)")

    # Convert any files already sitting in the inbox before we start watching
    for f in inbox.iterdir():
        if f.is_file() and f.suffix.lower() in SUPPORTED:
            convert_to_markdown(f, inbox, archive)

    observer = Observer()
    observer.schedule(InboxHandler(inbox, archive), str(inbox), recursive=False)
    observer.start()
    print(f"[watcher] Watching {inbox}  (Ctrl-C to stop)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
