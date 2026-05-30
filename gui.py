#!/usr/bin/env python3
"""Vault Control Panel — start/stop screenpipe, run memory-check, skills, and swarm."""
import os
import shlex
import signal
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
PYTHON = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable

# ── palette ───────────────────────────────────────────────────────────────────
BG      = "#0f1117"
SURFACE = "#1a1d27"
BORDER  = "#2a2d3a"
ACCENT  = "#7c6af7"
GREEN   = "#4ade80"
RED     = "#f87171"
AMBER   = "#fbbf24"
TEAL    = "#2dd4bf"
FG      = "#e2e8f0"
FG_DIM  = "#64748b"
MONO    = ("JetBrains Mono", "Fira Code", "Courier New")


def _mono(size: int = 9) -> tuple:
    return (MONO[0], size)


class VaultControl:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Vault Control")
        self.root.configure(bg=BG)
        self.root.geometry("760x700")
        self.root.minsize(640, 560)
        self.screenpipe_proc = None
        self.status_var = tk.StringVar(value="unknown")
        self._build_ui()
        self._poll_screenpipe()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self.root

        # title bar
        hdr = tk.Frame(root, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(hdr, text="⬡ Vault Control", font=("Inter", 15, "bold"),
                 bg=BG, fg=FG).pack(side="left")
        tk.Label(hdr, text="memory · skills · swarm · pipeline",
                 font=("Inter", 9), bg=BG, fg=FG_DIM).pack(side="left", padx=(10, 0))

        # ── screenpipe ─────────────────────────────────────────────────────────
        self._section_label(root, "SCREENPIPE SERVICE")
        sp_frame = self._card_frame(root)
        row = tk.Frame(sp_frame, bg=SURFACE)
        row.pack(fill="x", padx=14, pady=10)
        self.dot = tk.Label(row, text="●", font=("Inter", 13), bg=SURFACE, fg=FG_DIM)
        self.dot.pack(side="left")
        self.status_lbl = tk.Label(row, textvariable=self.status_var,
                                   font=("Inter", 9), bg=SURFACE, fg=FG_DIM)
        self.status_lbl.pack(side="left", padx=(6, 0))
        self._action_btn(row, "■  Stop",  self._stop_screenpipe,  RED,   "right", (0, 0))
        self._action_btn(row, "▶  Start", self._start_screenpipe, ACCENT, "right", (0, 8))

        # ── vault os ───────────────────────────────────────────────────────────
        self._section_label(root, "VAULT OS")
        vault_cmds = [
            ("🌙  Night Operator",   self._run_night_operator,    TEAL),
            ("📋  Project Snapshot…", self._run_project_snapshot,  TEAL),
            ("📂  Open Last Report",  self._run_open_last_report,  "#9b8afb"),
        ]
        self._button_grid(root, vault_cmds, cols=3)

        # ── swarm colony ───────────────────────────────────────────────────────
        self._section_label(root, "SWARM COLONY")
        swarm_cmds = [
            ("🐝  Swarm Dashboard",    self._run_swarm_dashboard, TEAL),
            ("⬡  Graph Analyze",       self._run_graph_analyze,   TEAL),
            ("⬡  Skill from Memopipe", self._run_skill_memopipe,  "#4ade80"),
            ("◎  Skill Audit",         self._run_skill_audit,     "#9b8afb"),
            ("✎  Skill Log",           self._run_skill_log,       "#9b8afb"),
        ]
        self._button_grid(root, swarm_cmds, cols=3)

        # ── memory commands ────────────────────────────────────────────────────
        self._section_label(root, "MEMORY COMMANDS")
        mem_cmds = [
            ("🧠  Memory Check",   self._run_memory_check,  ACCENT),
            ("↑  Promote Loop",    self._run_promote,        "#5ba3f5"),
            ("~  Daily Summary",   self._run_screenpipe_py,  "#5ba3f5"),
            ("◈  Connections",     self._run_connections,    "#9b8afb"),
            ("✉  Inbox",           self._run_inbox,          "#9b8afb"),
            ("≠  Contradict",      self._run_contradict,     FG_DIM),
        ]
        self._button_grid(root, mem_cmds, cols=3)

        # ── skills ─────────────────────────────────────────────────────────────
        self._section_label(root, "SKILLS & QUERY")
        skill_cmds = [
            ("📋  Gaps",           self._run_gaps,           ACCENT),
            ("✎  Skill Capture",   self._run_skill_capture,  "#5ba3f5"),
            ("◑  Synthesize…",     self._run_synthesize,     "#9b8afb"),
            ("?  Ask Vault…",      self._run_ask,            "#5ba3f5"),
            ("✍  Write Prep…",     self._run_write_prep,     "#9b8afb"),
        ]
        self._button_grid(root, skill_cmds, cols=3)

        # ── output pane ────────────────────────────────────────────────────────
        self._section_label(root, "OUTPUT")
        self.out = scrolledtext.ScrolledText(
            root, wrap="word", bg=SURFACE, fg=FG, insertbackground=FG,
            font=_mono(), bd=0, highlightthickness=1,
            highlightbackground=BORDER, relief="flat",
            state="disabled", padx=12, pady=8,
        )
        self.out.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        self.out.tag_config("dim",  foreground=FG_DIM)
        self.out.tag_config("ok",   foreground=GREEN)
        self.out.tag_config("err",  foreground=RED)
        self.out.tag_config("warn", foreground=AMBER)
        self.out.tag_config("swarm", foreground=TEAL)
        self._log("Ready.\n", "dim")

    # ── layout helpers ─────────────────────────────────────────────────────────

    def _section_label(self, parent: tk.Widget, title: str) -> None:
        tk.Label(parent, text=title, font=("Inter", 7, "bold"),
                 bg=BG, fg=FG_DIM, anchor="w").pack(fill="x", padx=20, pady=(10, 3))

    def _card_frame(self, parent: tk.Widget) -> tk.Frame:
        f = tk.Frame(parent, bg=SURFACE, highlightthickness=1,
                     highlightbackground=BORDER)
        f.pack(fill="x", padx=20, pady=(0, 6))
        return f

    def _action_btn(self, parent: tk.Widget, text: str, cmd,
                    color: str, side: str = "left",
                    padx: tuple = (8, 0)) -> tk.Button:
        b = tk.Button(parent, text=text, command=cmd,
                      bg=color, fg="#fff", activebackground=color,
                      activeforeground="#fff", relief="flat", bd=0,
                      font=("Inter", 9, "bold"), padx=10, pady=4,
                      cursor="hand2")
        b.pack(side=side, padx=padx)
        return b

    def _button_grid(self, parent: tk.Widget,
                     cmds: list[tuple], cols: int = 3) -> None:
        grid = tk.Frame(parent, bg=BG)
        grid.pack(fill="x", padx=20, pady=(0, 6))
        for col in range(cols):
            grid.columnconfigure(col, weight=1)
        for i, (label, cmd, color) in enumerate(cmds):
            row, col = divmod(i, cols)
            cell = tk.Frame(grid, bg=BG)
            cell.grid(row=row, column=col, padx=(0, 6), pady=(0, 6), sticky="ew")
            b = tk.Button(cell, text=label, command=cmd,
                          bg=SURFACE, fg=FG, activebackground=BORDER,
                          activeforeground=FG, relief="flat", bd=0,
                          font=("Inter", 9), padx=10, pady=9,
                          anchor="w", cursor="hand2",
                          highlightthickness=1, highlightbackground=BORDER)
            b.pack(fill="both", expand=True)
            b.bind("<Enter>", lambda e, btn=b, c=color: btn.config(highlightbackground=c))
            b.bind("<Leave>", lambda e, btn=b: btn.config(highlightbackground=BORDER))

    # ── screenpipe status ──────────────────────────────────────────────────────

    def _poll_screenpipe(self) -> None:
        self._check_screenpipe_status()
        self.root.after(5000, self._poll_screenpipe)

    def _check_screenpipe_status(self) -> None:
        running = self._is_screenpipe_running()
        if running:
            self.dot.config(fg=GREEN)
            self.status_var.set("Running")
            self.status_lbl.config(fg=GREEN)
        elif self.screenpipe_proc is not None:
            self.dot.config(fg=AMBER)
            self.status_var.set("Starting…")
            self.status_lbl.config(fg=AMBER)
        else:
            self.dot.config(fg=FG_DIM)
            self.status_var.set("Stopped")
            self.status_lbl.config(fg=FG_DIM)

    def _is_screenpipe_running(self) -> bool:
        try:
            r = subprocess.run(["pgrep", "-f", "screenpipe"],
                               capture_output=True, timeout=3)
            return r.returncode == 0
        except Exception:
            return False

    # ── screenpipe start / stop ────────────────────────────────────────────────

    def _start_screenpipe(self) -> None:
        if self._is_screenpipe_running():
            self._log("Screenpipe already running.\n", "warn")
            return
        script = os.path.join(SCRIPT_DIR, "start-screenpipe.sh")
        if not os.path.exists(script):
            self._log(f"ERROR: {script} not found.\n", "err")
            return
        self._log("▶ Starting screenpipe…\n", "dim")

        def _launch() -> None:
            try:
                self.screenpipe_proc = subprocess.Popen(
                    ["bash", script], cwd=SCRIPT_DIR,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, preexec_fn=os.setsid,
                )
                for line in self.screenpipe_proc.stdout:
                    self._log(line)
                self.screenpipe_proc.wait()
                self.screenpipe_proc = None
                self._log("Screenpipe process exited.\n", "warn")
            except Exception as exc:
                self._log(f"ERROR: {exc}\n", "err")

        threading.Thread(target=_launch, daemon=True).start()
        self.dot.config(fg=AMBER)
        self.status_var.set("Starting…")

    def _stop_screenpipe(self) -> None:
        stopped = False
        if self.screenpipe_proc and self.screenpipe_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.screenpipe_proc.pid), signal.SIGTERM)
                self.screenpipe_proc = None
                stopped = True
            except Exception as exc:
                self._log(f"WARN: {exc}\n", "warn")
        try:
            r = subprocess.run(["pkill", "-f", "screenpipe"],
                               capture_output=True, timeout=5)
            if r.returncode == 0:
                stopped = True
        except Exception:
            pass
        self._log(("■ Screenpipe stopped.\n" if stopped
                   else "Screenpipe was not running.\n"),
                  "warn" if stopped else "dim")
        self._check_screenpipe_status()

    # ── vault os commands ──────────────────────────────────────────────────────

    def _vault_path(self) -> str:
        env = self._build_env()
        return env.get("VAULT_PATH", "")

    def _vault_repos(self) -> str:
        env = self._build_env()
        return env.get("VAULT_OS_REPOS", "")

    def _run_night_operator(self) -> None:
        vault = self._vault_path()
        repos = self._vault_repos()
        if not vault:
            self._log("ERROR: VAULT_PATH not set in .env\n", "err")
            return
        if not repos:
            self._log("WARN: VAULT_OS_REPOS not set in .env — prompting.\n", "warn")
            self._prompt_one(
                "Night Operator",
                "Repo paths (comma-separated):",
                lambda r: self._run(
                    "vault-night-operator",
                    f"'{PYTHON}' vault_night_operator.py "
                    f"--vault {shlex.quote(vault)} --repos {shlex.quote(r)}",
                    header_tag="swarm",
                ),
            )
            return
        self._run(
            "vault-night-operator",
            f"'{PYTHON}' vault_night_operator.py "
            f"--vault {shlex.quote(vault)} --repos {shlex.quote(repos)}",
            header_tag="swarm",
        )

    def _run_project_snapshot(self) -> None:
        self._prompt_one(
            "Project Snapshot",
            "Repo path (writes docs/LLM_CONTEXT_BRIEF.md):",
            lambda repo: self._run(
                f"project-snapshot {repo}",
                f"'{PYTHON}' {shlex.quote(repo)}/scripts/project_snapshot.py --write",
                header_tag="swarm",
            ),
        )

    def _run_open_last_report(self) -> None:
        import datetime
        vault = self._vault_path()
        if not vault:
            self._log("ERROR: VAULT_PATH not set in .env\n", "err")
            return
        today = datetime.date.today().isoformat()
        report = os.path.join(vault, "06 - Automation", "Nightly Reports", f"{today}.md")
        if not os.path.exists(report):
            self._log(f"No report found for today ({today}).\n", "warn")
            return
        try:
            content = open(report, encoding="utf-8").read()
            self._log(f"\n📂 {os.path.basename(report)}\n", "swarm")
            self._log(content + "\n")
        except Exception as exc:
            self._log(f"ERROR reading report: {exc}\n", "err")

    # ── swarm commands ─────────────────────────────────────────────────────────

    def _run_swarm_dashboard(self) -> None:
        self._run("swarm-dashboard",
                  f"'{PYTHON}' vault_intelligence.py swarm-dashboard",
                  header_tag="swarm")

    def _run_graph_analyze(self) -> None:
        self._run("graph-analyze --scope Memory",
                  f"'{PYTHON}' vault_intelligence.py graph-analyze --scope Memory",
                  header_tag="swarm")

    def _run_skill_memopipe(self) -> None:
        self._run("skill-from-memopipe",
                  f"'{PYTHON}' vault_intelligence.py skill-from-memopipe",
                  header_tag="swarm")

    def _run_skill_audit(self) -> None:
        self._prompt_one("Skill Audit", "Skill slug (folder name):", lambda slug: (
            self._run(f"skill-audit {slug}",
                      f"'{PYTHON}' vault_intelligence.py skill-audit '{slug}'",
                      header_tag="swarm")
        ))

    def _run_skill_log(self) -> None:
        self._prompt_two(
            "Skill Log",
            "Skill slug:", "Observation:",
            lambda slug, obs: self._run(
                f"skill-log {slug}",
                f"'{PYTHON}' vault_intelligence.py skill-log '{slug}' '{obs}'",
                header_tag="swarm",
            ),
        )

    # ── memory commands ────────────────────────────────────────────────────────

    def _run_memory_check(self) -> None:
        mc = os.path.join(SCRIPT_DIR, "memory-check")
        self._run("memory-check", f"bash '{mc}'")

    def _run_promote(self) -> None:
        self._run("promote", f"'{PYTHON}' vault_intelligence.py promote")

    def _run_screenpipe_py(self) -> None:
        self._run("Screenpipe-to-Obsidian.py",
                  f"'{PYTHON}' Screenpipe-to-Obsidian.py")

    def _run_connections(self) -> None:
        self._run("connections",
                  f"'{PYTHON}' vault_intelligence.py connections")

    def _run_inbox(self) -> None:
        self._run("inbox", f"'{PYTHON}' vault_intelligence.py inbox")

    def _run_contradict(self) -> None:
        self._run("contradict",
                  f"'{PYTHON}' vault_intelligence.py contradict")

    # ── skills & query ─────────────────────────────────────────────────────────

    def _run_gaps(self) -> None:
        self._run("gaps --scope Memory",
                  f"'{PYTHON}' vault_intelligence.py gaps --scope Memory")

    def _run_skill_capture(self) -> None:
        self._prompt_text(
            "Skill Capture",
            "Paste or type raw text to convert into a skill:",
            lambda text: self._run(
                "skill-capture",
                f"'{PYTHON}' vault_intelligence.py skill-capture {shlex.quote(text)}",
            ),
        )

    def _run_synthesize(self) -> None:
        self._prompt_one("Synthesize", "Topic:", lambda topic: self._run(
            f"synthesize {topic!r}",
            f"'{PYTHON}' vault_intelligence.py synthesize '{topic}'",
        ))

    def _run_ask(self) -> None:
        self._prompt_one("Ask Vault", "Question:", lambda q: self._run(
            f"ask {q!r}",
            f"'{PYTHON}' vault_intelligence.py ask '{q}'",
        ))

    def _run_write_prep(self) -> None:
        self._prompt_one("Write Prep", "Topic:", lambda topic: self._run(
            f"write-prep {topic!r}",
            f"'{PYTHON}' vault_intelligence.py write-prep '{topic}'",
        ))

    # ── generic command runner ─────────────────────────────────────────────────

    def _run(self, label: str, cmd: str,
             shell: bool = True, header_tag: str = "dim") -> None:
        self._log(f"\n$ {label}\n", header_tag)

        def _worker() -> None:
            env = self._build_env()
            try:
                proc = subprocess.Popen(
                    cmd, shell=shell, cwd=SCRIPT_DIR, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in proc.stdout:
                    self._log(line)
                rc = proc.wait()
                self._log(f"[exit {rc}]\n", "ok" if rc == 0 else "err")
            except Exception as exc:
                self._log(f"ERROR: {exc}\n", "err")

        threading.Thread(target=_worker, daemon=True).start()

    def _build_env(self) -> dict:
        env = os.environ.copy()
        env_file = os.path.join(SCRIPT_DIR, ".env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        env.setdefault(k.strip(), v.strip().strip('"'))
        return env

    # ── prompt dialogs ─────────────────────────────────────────────────────────

    def _prompt_one(self, title: str, label: str, on_submit) -> None:
        dlg = self._dlg(title, height=130)
        tk.Label(dlg, text=label, bg=BG, fg=FG,
                 font=("Inter", 9)).pack(pady=(16, 4))
        entry = self._dlg_entry(dlg)

        def submit() -> None:
            val = entry.get().strip()
            dlg.destroy()
            if val:
                on_submit(val)

        entry.bind("<Return>", lambda _e: submit())
        self._dlg_btn(dlg, submit)

    def _prompt_two(self, title: str, label1: str, label2: str,
                    on_submit) -> None:
        dlg = self._dlg(title, height=190)
        tk.Label(dlg, text=label1, bg=BG, fg=FG,
                 font=("Inter", 9)).pack(pady=(14, 2))
        e1 = self._dlg_entry(dlg)
        tk.Label(dlg, text=label2, bg=BG, fg=FG,
                 font=("Inter", 9)).pack(pady=(8, 2))
        e2 = self._dlg_entry(dlg)

        def submit() -> None:
            v1, v2 = e1.get().strip(), e2.get().strip()
            dlg.destroy()
            if v1 and v2:
                on_submit(v1, v2)

        e2.bind("<Return>", lambda _e: submit())
        self._dlg_btn(dlg, submit)

    def _prompt_text(self, title: str, label: str, on_submit) -> None:
        dlg = self._dlg(title, height=260)
        tk.Label(dlg, text=label, bg=BG, fg=FG,
                 font=("Inter", 9), wraplength=340, justify="left").pack(
            pady=(14, 4), padx=20, anchor="w")
        txt = scrolledtext.ScrolledText(
            dlg, wrap="word", bg=SURFACE, fg=FG, insertbackground=FG,
            font=_mono(9), bd=0, highlightthickness=1,
            highlightbackground=BORDER, relief="flat",
            height=6, padx=8, pady=6,
        )
        txt.pack(fill="both", expand=True, padx=20)
        txt.focus_set()

        def submit() -> None:
            val = txt.get("1.0", "end").strip()
            dlg.destroy()
            if val:
                on_submit(val)

        tk.Button(dlg, text="Run", command=submit,
                  bg=ACCENT, fg="#fff", relief="flat", bd=0,
                  font=("Inter", 9, "bold"), padx=14, pady=5,
                  cursor="hand2").pack(pady=8)

    def _dlg(self, title: str, height: int = 140) -> tk.Toplevel:
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.configure(bg=BG)
        dlg.geometry(f"380x{height}")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        return dlg

    def _dlg_entry(self, parent: tk.Widget) -> tk.Entry:
        e = tk.Entry(parent, bg=SURFACE, fg=FG, insertbackground=FG,
                     font=("Inter", 10), relief="flat", bd=0,
                     highlightthickness=1, highlightbackground=BORDER)
        e.pack(fill="x", padx=20)
        e.focus_set()
        return e

    def _dlg_btn(self, parent: tk.Widget, cmd) -> None:
        tk.Button(parent, text="Run", command=cmd,
                  bg=ACCENT, fg="#fff", relief="flat", bd=0,
                  font=("Inter", 9, "bold"), padx=14, pady=5,
                  cursor="hand2").pack(pady=8)

    # ── output ─────────────────────────────────────────────────────────────────

    def _log(self, text: str, tag: str | None = None) -> None:
        def _do() -> None:
            self.out.config(state="normal")
            if tag:
                self.out.insert("end", text, tag)
            else:
                self.out.insert("end", text)
            self.out.see("end")
            self.out.config(state="disabled")
        self.root.after(0, _do)

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self.screenpipe_proc and self.screenpipe_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.screenpipe_proc.pid), signal.SIGTERM)
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    VaultControl().run()
