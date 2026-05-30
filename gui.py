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

from path_config import PathConfig

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


def _bind_tree(widget: tk.Widget, event: str, callback) -> None:
    """Bind an event to a widget and all its descendants."""
    widget.bind(event, callback)
    for child in widget.winfo_children():
        _bind_tree(child, event, callback)


# ── tool registry ──────────────────────────────────────────────────────────────

TOOL_REGISTRY: list[dict] = [
    # Vault OS — specialized panels handle these; "fields" unused but kept for nav
    {"id": "project-snapshot", "section": "Vault OS",     "label": "Project Snapshot",
     "desc": "Writes docs/LLM_CONTEXT_BRIEF.md to the target repo.", "fields": []},
    {"id": "night-operator",   "section": "Vault OS",     "label": "Night Operator",
     "desc": "Runs nightly vault sweep across configured repos.",     "fields": []},
    # Swarm Colony
    {"id": "skill-audit",      "section": "Swarm Colony", "label": "Skill Audit",
     "desc": "Audit a skill by its slug (folder name).",
     "fields": [{"key": "slug", "label": "Skill slug", "type": "entry"}]},
    {"id": "skill-log",        "section": "Swarm Colony", "label": "Skill Log",
     "desc": "Log an observation for a skill.",
     "fields": [{"key": "slug",  "label": "Skill slug",   "type": "entry"},
                {"key": "obs",   "label": "Observation",  "type": "entry"}]},
    {"id": "skill-capture",    "section": "Swarm Colony", "label": "Skill Capture",
     "desc": "Convert raw text into a vault skill.",
     "fields": [{"key": "text", "label": "Raw text to convert into a skill", "type": "text"}]},
    # Skills & Query
    {"id": "synthesize",       "section": "Skills & Query", "label": "Synthesize",
     "desc": "Synthesise a topic from vault memory.",
     "fields": [{"key": "topic",    "label": "Topic",    "type": "entry"}]},
    {"id": "ask",              "section": "Skills & Query", "label": "Ask Vault",
     "desc": "Ask the vault a freeform question.",
     "fields": [{"key": "question", "label": "Question", "type": "entry"}]},
    {"id": "write-prep",       "section": "Skills & Query", "label": "Write Prep",
     "desc": "Prepare writing scaffolding for a topic.",
     "fields": [{"key": "topic",    "label": "Topic",    "type": "entry"}]},
]


# ── SmartPathPicker ────────────────────────────────────────────────────────────

class SmartPathPicker:
    """In-app path picker with grouped cards and a search filter.

    Replaces the native directory dialog. Calls on_select(path) on selection.
    If append=True, the caller is responsible for appending (pass a dedicated callback).
    """

    _ICONS = {"vault": "🏛", "repo": "⬡", "folder": "📁",
              "recent": "🕐", "pinned": "📌", "home": "🏠"}
    _GROUP_ORDER = ["vault", "pinned", "known repos", "home", "recent"]

    def __init__(self, parent, path_config: PathConfig,
                 on_select, title: str = "Select Path") -> None:
        self._cfg = path_config
        self._on_select = on_select
        self._cards = path_config.path_cards()

        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.configure(bg=BG)
        self.win.geometry("600x500")
        self.win.resizable(True, True)
        self.win.transient(parent)
        self.win.grab_set()
        self._build()

    def _build(self) -> None:
        # search bar
        sf = tk.Frame(self.win, bg=SURFACE, highlightthickness=1,
                      highlightbackground=BORDER)
        sf.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(sf, text="⌕", bg=SURFACE, fg=FG_DIM,
                 font=("Inter", 13)).pack(side="left", padx=(10, 4))
        self._q = tk.StringVar()
        self._q.trace_add("write", lambda *_: self._refresh())
        e = tk.Entry(sf, textvariable=self._q, bg=SURFACE, fg=FG,
                     insertbackground=FG, font=("Inter", 10),
                     relief="flat", bd=0, highlightthickness=0)
        e.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 10))
        e.focus_set()

        # scrollable card list via canvas
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        cv = tk.Canvas(outer, bg=BG, bd=0, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        self._lf = tk.Frame(cv, bg=BG)
        cw = cv.create_window((0, 0), window=self._lf, anchor="nw")
        self._lf.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(cw, width=e.width))
        cv.bind("<Button-4>", lambda e: cv.yview_scroll(-1, "units"))
        cv.bind("<Button-5>", lambda e: cv.yview_scroll(1, "units"))
        self._refresh()

    def _refresh(self) -> None:
        q = self._q.get().lower()
        for w in self._lf.winfo_children():
            w.destroy()
        cards = [c for c in self._cards
                 if not q or q in c["label"].lower() or q in c["path"].lower()]
        if not cards:
            tk.Label(self._lf, text="No paths match.", bg=BG, fg=FG_DIM,
                     font=("Inter", 9)).pack(pady=20)
            return
        groups: dict[str, list] = {}
        for c in cards:
            groups.setdefault(c["group"], []).append(c)
        for g in self._GROUP_ORDER + [x for x in groups if x not in self._GROUP_ORDER]:
            if g not in groups:
                continue
            tk.Label(self._lf, text=g.upper(), font=("Inter", 7, "bold"),
                     bg=BG, fg=FG_DIM, anchor="w").pack(fill="x", padx=8, pady=(10, 3))
            for card in groups[g]:
                self._card(card)

    def _card(self, c: dict) -> None:
        icon = self._ICONS.get(c["type"], "📁")
        sc = GREEN if c["exists"] else RED
        home = os.path.expanduser("~")
        short = c["path"].replace(home, "~")

        f = tk.Frame(self._lf, bg=SURFACE, highlightthickness=1,
                     highlightbackground=BORDER)
        f.pack(fill="x", padx=4, pady=2)

        top = tk.Frame(f, bg=SURFACE)
        top.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(top, text=icon,      bg=SURFACE, fg=FG,
                 font=("Inter", 10)).pack(side="left")
        tk.Label(top, text=c["label"], bg=SURFACE, fg=FG,
                 font=("Inter", 10, "bold"), anchor="w").pack(side="left", padx=(6, 0))
        tk.Label(top, text=f"● {'exists' if c['exists'] else 'missing'}",
                 bg=SURFACE, fg=sc, font=("Inter", 8)).pack(side="right")
        tk.Label(f, text=short, bg=SURFACE, fg=FG_DIM,
                 font=_mono(8), anchor="w").pack(fill="x", padx=12, pady=(0, 8))

        path = c["path"]

        def _click(e, p=path):
            self.win.destroy()
            self._on_select(p)

        def _leave(e, fr=f):
            x = fr.winfo_pointerx() - fr.winfo_rootx()
            y = fr.winfo_pointery() - fr.winfo_rooty()
            if not (0 <= x < fr.winfo_width() and 0 <= y < fr.winfo_height()):
                fr.config(highlightbackground=BORDER)

        f.bind("<Enter>", lambda e, fr=f: fr.config(highlightbackground=ACCENT))
        f.bind("<Leave>", _leave)
        _bind_tree(f, "<Button-1>", _click)
        _bind_tree(f, "<Enter>",    lambda e, fr=f: fr.config(highlightbackground=ACCENT))
        _bind_tree(f, "<Leave>",    _leave)
        for w in [f, top] + list(f.winfo_children()) + list(top.winfo_children()):
            try:
                w.config(cursor="hand2")
            except Exception:
                pass


# ── ToolModal ─────────────────────────────────────────────────────────────────

class ToolModal:
    """Navigation-style modal. Left nav lists all tools; right pane renders the active tool."""

    def __init__(self, parent: tk.Tk, initial_id: str,
                 on_submit, path_config: PathConfig) -> None:
        self._on_submit = on_submit
        self._path_config = path_config
        self._selected_id = initial_id
        self._field_widgets: dict[str, tk.Widget] = {}
        self._nav_buttons: dict[str, tk.Button] = {}

        self.win = tk.Toplevel(parent)
        self.win.title("Vault Control — Tools")
        self.win.configure(bg=BG)
        self.win.geometry("700x540")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()
        self._build_layout()
        self._select(initial_id)

    def _build_layout(self) -> None:
        pane = tk.Frame(self.win, bg=BG)
        pane.pack(fill="both", expand=True)
        nav = tk.Frame(pane, bg=SURFACE, width=190)
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        tk.Frame(pane, bg=BORDER, width=1).pack(side="left", fill="y")
        self._form_frame = tk.Frame(pane, bg=BG)
        self._form_frame.pack(side="left", fill="both", expand=True)

        current_section: str | None = None
        for tool in TOOL_REGISTRY:
            if tool["section"] != current_section:
                current_section = tool["section"]
                tk.Label(nav, text=current_section.upper(),
                         font=("Inter", 7, "bold"), bg=SURFACE, fg=FG_DIM,
                         anchor="w").pack(fill="x", padx=12, pady=(12, 3))
            b = tk.Button(nav, text=tool["label"],
                          bg=SURFACE, fg=FG, activebackground=BORDER, activeforeground=FG,
                          relief="flat", bd=0, font=("Inter", 9),
                          padx=14, pady=7, anchor="w", cursor="hand2",
                          command=lambda tid=tool["id"]: self._select(tid))
            b.pack(fill="x")
            self._nav_buttons[tool["id"]] = b

    def _select(self, tool_id: str) -> None:
        self._selected_id = tool_id
        for tid, btn in self._nav_buttons.items():
            btn.config(bg=ACCENT if tid == tool_id else SURFACE,
                       fg="#fff" if tid == tool_id else FG)
        for w in self._form_frame.winfo_children():
            w.destroy()
        self._field_widgets.clear()
        if tool_id == "project-snapshot":
            self._panel_project_snapshot()
        elif tool_id == "night-operator":
            self._panel_night_operator()
        else:
            tool = next(t for t in TOOL_REGISTRY if t["id"] == tool_id)
            self._panel_generic(tool)

    # ── shared helpers ─────────────────────────────────────────────────────────

    def _panel_header(self, title: str, desc: str, badge: str, badge_color: str) -> None:
        f = self._form_frame
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", padx=24, pady=(20, 4))
        tk.Label(row, text=title, font=("Inter", 13, "bold"),
                 bg=BG, fg=FG, anchor="w").pack(side="left")
        tk.Label(row, text=badge, font=("Inter", 7, "bold"),
                 bg=badge_color, fg="#000", padx=6, pady=2).pack(side="right")
        tk.Label(f, text=desc, font=("Inter", 9), bg=BG, fg=FG_DIM,
                 anchor="w", wraplength=440, justify="left").pack(
            fill="x", padx=24, pady=(0, 14))

    def _val_row(self, parent: tk.Frame, sym: str, text: str, color: str) -> None:
        r = tk.Frame(parent, bg=BG)
        r.pack(fill="x", pady=1)
        tk.Label(r, text=sym,  bg=BG, fg=color, font=("Inter", 9)).pack(side="left")
        tk.Label(r, text=text, bg=BG, fg=color, font=("Inter", 9),
                 anchor="w").pack(side="left", padx=(4, 0))

    def _footer(self, run_cmd, run_state: str = "normal") -> tk.Button:
        row = tk.Frame(self._form_frame, bg=BG)
        row.pack(fill="x", padx=24, pady=(6, 20))
        btn = tk.Button(row, text="Run", command=run_cmd,
                        bg=ACCENT, fg="#fff", activebackground=ACCENT,
                        activeforeground="#fff", relief="flat", bd=0,
                        font=("Inter", 9, "bold"), padx=18, pady=6,
                        cursor="hand2", state=run_state)
        btn.pack(side="left")
        tk.Button(row, text="Cancel", command=self.win.destroy,
                  bg=SURFACE, fg=FG_DIM, activebackground=BORDER, activeforeground=FG,
                  relief="flat", bd=0, font=("Inter", 9), padx=12, pady=6,
                  cursor="hand2").pack(side="left", padx=(8, 0))
        return btn

    def _browse_btn(self, parent, label: str, cmd) -> None:
        tk.Button(parent, text=label, command=cmd,
                  bg=SURFACE, fg=FG_DIM, activebackground=BORDER, activeforeground=FG,
                  relief="flat", bd=0, font=("Inter", 9), padx=10,
                  cursor="hand2", highlightthickness=1,
                  highlightbackground=BORDER).pack(side="left", padx=(4, 0), fill="y")

    # ── generic panel ──────────────────────────────────────────────────────────

    def _panel_generic(self, tool: dict) -> None:
        f = self._form_frame
        tk.Label(f, text=tool["label"], font=("Inter", 13, "bold"),
                 bg=BG, fg=FG, anchor="w").pack(fill="x", padx=24, pady=(20, 4))
        tk.Label(f, text=tool["desc"], font=("Inter", 9), bg=BG, fg=FG_DIM,
                 anchor="w", wraplength=440).pack(fill="x", padx=24, pady=(0, 16))
        for field in tool["fields"]:
            tk.Label(f, text=field["label"], font=("Inter", 9), bg=BG, fg=FG,
                     anchor="w").pack(fill="x", padx=24, pady=(0, 3))
            if field["type"] == "text":
                w: tk.Widget = scrolledtext.ScrolledText(
                    f, wrap="word", bg=SURFACE, fg=FG, insertbackground=FG,
                    font=_mono(9), bd=0, highlightthickness=1,
                    highlightbackground=BORDER, relief="flat",
                    height=6, padx=8, pady=6)
                w.pack(fill="both", expand=True, padx=24, pady=(0, 12))
            else:
                w = tk.Entry(f, bg=SURFACE, fg=FG, insertbackground=FG,
                             font=("Inter", 10), relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=BORDER)
                w.pack(fill="x", padx=24, pady=(0, 12))
                w.bind("<Return>", lambda _e: self._submit())
            self._field_widgets[field["key"]] = w
        if self._field_widgets:
            next(iter(self._field_widgets.values())).focus_set()
        self._footer(self._submit)

    def _submit(self) -> None:
        tool = next(t for t in TOOL_REGISTRY if t["id"] == self._selected_id)
        values: dict[str, str] = {}
        for field in tool["fields"]:
            w = self._field_widgets[field["key"]]
            raw = (w.get("1.0", "end")  # type: ignore[union-attr]
                   if isinstance(w, scrolledtext.ScrolledText)
                   else w.get())        # type: ignore[union-attr]
            values[field["key"]] = raw.strip()
        if any(not v for v in values.values()):
            return
        self.win.destroy()
        self._on_submit(self._selected_id, values)

    # ── Project Snapshot panel ─────────────────────────────────────────────────

    def _panel_project_snapshot(self) -> None:
        self._panel_header("Project Snapshot",
                           "Writes docs/LLM_CONTEXT_BRIEF.md to the target repo.",
                           "WRITES MARKDOWN", TEAL)
        f = self._form_frame
        cfg = self._path_config
        self._ps_script = ""
        self._ps_repo_abs = ""

        tk.Label(f, text="Repo path", font=("Inter", 9), bg=BG, fg=FG,
                 anchor="w").pack(fill="x", padx=24, pady=(0, 3))
        ir = tk.Frame(f, bg=BG)
        ir.pack(fill="x", padx=24, pady=(0, 6))
        self._ps_repo = tk.StringVar(value=cfg.last_snapshot_repo)
        e = tk.Entry(ir, textvariable=self._ps_repo, bg=SURFACE, fg=FG,
                     insertbackground=FG, font=("Inter", 10), relief="flat", bd=0,
                     highlightthickness=1, highlightbackground=BORDER)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _: self._ps_run())
        self._browse_btn(ir, "Browse ▾", self._ps_browse)

        # quick picks (existing repo cards)
        repo_cards = [c for c in cfg.path_cards()
                      if c["type"] == "repo" and c["exists"]][:5]
        if repo_cards:
            tk.Label(f, text="Quick pick:", font=("Inter", 8),
                     bg=BG, fg=FG_DIM, anchor="w").pack(fill="x", padx=24, pady=(0, 3))
            qp = tk.Frame(f, bg=BG)
            qp.pack(fill="x", padx=24, pady=(0, 10))
            for card in repo_cards:
                lbl = card["label"][:18] + ("…" if len(card["label"]) > 18 else "")
                tk.Button(qp, text=lbl,
                          command=lambda p=card["path"]: self._ps_repo.set(p),
                          bg=SURFACE, fg=FG_DIM, activebackground=BORDER,
                          activeforeground=FG, relief="flat", bd=0,
                          font=("Inter", 8), padx=8, pady=4, cursor="hand2",
                          highlightthickness=1, highlightbackground=BORDER
                          ).pack(side="left", padx=(0, 6))

        self._ps_val = tk.Frame(f, bg=BG)
        self._ps_val.pack(fill="x", padx=24, pady=(0, 6))
        self._ps_run_btn = self._footer(self._ps_run, "disabled")
        self._ps_repo.trace_add("write", lambda *_: self._ps_validate())
        self._ps_validate()

    def _ps_browse(self) -> None:
        SmartPathPicker(self.win, self._path_config,
                        on_select=lambda p: self._ps_repo.set(p))

    def _ps_validate(self) -> None:
        for w in self._ps_val.winfo_children():
            w.destroy()
        repo = self._ps_repo.get().strip()
        if not repo:
            self._ps_run_btn.config(state="disabled")
            return
        repo = os.path.abspath(repo)
        if not os.path.isdir(repo):
            self._val_row(self._ps_val, "✕", "Path does not exist", RED)
            self._ps_run_btn.config(state="disabled")
            return
        self._val_row(self._ps_val, "●", "Repo exists", GREEN)
        if os.path.isdir(os.path.join(repo, ".git")):
            self._val_row(self._ps_val, "●", "Git repo detected", GREEN)

        local = os.path.join(repo, "scripts", "project_snapshot.py")
        bundled = os.path.join(SCRIPT_DIR, "scripts", "project_snapshot.py")
        if os.path.exists(local):
            self._val_row(self._ps_val, "●", "Snapshot script found in repo", GREEN)
            self._ps_script = local
        elif os.path.exists(bundled):
            self._val_row(self._ps_val, "~", "Using bundled snapshot script", AMBER)
            self._ps_script = bundled
        else:
            self._val_row(self._ps_val, "✕",
                          "No project_snapshot.py found — cannot run", RED)
            self._ps_run_btn.config(state="disabled")
            return

        short = os.path.join(repo, "docs", "LLM_CONTEXT_BRIEF.md").replace(
            os.path.expanduser("~"), "~")
        self._val_row(self._ps_val, "→", f"Will write: {short}", FG_DIM)
        self._ps_run_btn.config(state="normal")
        self._ps_repo_abs = repo

    def _ps_run(self) -> None:
        repo = getattr(self, "_ps_repo_abs", "")
        script = getattr(self, "_ps_script", "")
        if not repo or not script or self._ps_run_btn["state"] == "disabled":
            return
        self.win.destroy()
        self._on_submit("project-snapshot", {"repo": repo, "script": script})

    # ── Night Operator panel ────────────────────────────────────────────────────

    def _panel_night_operator(self) -> None:
        self._panel_header("Night Operator",
                           "Runs nightly vault sweep across configured repos.",
                           "WRITES MARKDOWN", TEAL)
        f = self._form_frame
        cfg = self._path_config
        env = cfg._env

        # vault path
        tk.Label(f, text="Vault path", font=("Inter", 9), bg=BG, fg=FG,
                 anchor="w").pack(fill="x", padx=24, pady=(0, 3))
        vr = tk.Frame(f, bg=BG)
        vr.pack(fill="x", padx=24, pady=(0, 10))
        vault_default = (env.get("OBSIDIAN_VAULT_PATH") or env.get("VAULT_PATH") or
                         cfg.last_vault_path or "")
        self._no_vault = tk.StringVar(value=vault_default.strip().strip('"'))
        tk.Entry(vr, textvariable=self._no_vault, bg=SURFACE, fg=FG,
                 insertbackground=FG, font=("Inter", 10), relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=BORDER).pack(
            side="left", fill="x", expand=True)
        self._browse_btn(vr, "Browse ▾",
                         lambda: SmartPathPicker(self.win, cfg,
                                                 lambda p: self._no_vault.set(p)))

        # repos
        tk.Label(f, text="Repo paths (comma-separated)", font=("Inter", 9),
                 bg=BG, fg=FG, anchor="w").pack(fill="x", padx=24, pady=(0, 3))
        rr = tk.Frame(f, bg=BG)
        rr.pack(fill="x", padx=24, pady=(0, 8))
        repos_default = env.get("VAULT_OS_REPOS", "").strip().strip('"')
        self._no_repos = tk.StringVar(value=repos_default)
        tk.Entry(rr, textvariable=self._no_repos, bg=SURFACE, fg=FG,
                 insertbackground=FG, font=("Inter", 10), relief="flat", bd=0,
                 highlightthickness=1, highlightbackground=BORDER).pack(
            side="left", fill="x", expand=True)

        def _browse_append():
            def _add(p: str) -> None:
                cur = self._no_repos.get().strip()
                self._no_repos.set((cur + "," + p) if cur else p)
            SmartPathPicker(self.win, cfg, _add, title="Add Repo")

        self._browse_btn(rr, "Add ▾", _browse_append)

        self._no_val = tk.Frame(f, bg=BG)
        self._no_val.pack(fill="x", padx=24, pady=(0, 6))
        self._no_run_btn = self._footer(self._no_run, "disabled")
        for var in (self._no_vault, self._no_repos):
            var.trace_add("write", lambda *_: self._no_validate())
        self._no_validate()

    def _no_validate(self) -> None:
        for w in self._no_val.winfo_children():
            w.destroy()
        vault = self._no_vault.get().strip()
        repos = [r.strip() for r in self._no_repos.get().split(",") if r.strip()]
        vault_ok = bool(vault) and os.path.isdir(os.path.abspath(vault))
        if vault:
            self._val_row(self._no_val, "●" if vault_ok else "✕",
                          "Vault exists" if vault_ok else "Vault path not found",
                          GREEN if vault_ok else RED)
        repos_ok = False
        for rp in repos:
            exists = os.path.isdir(os.path.abspath(rp))
            self._val_row(self._no_val, "●" if exists else "✕",
                          f"{'Repo exists' if exists else 'Not found'}: {os.path.basename(rp)}",
                          GREEN if exists else RED)
            if exists:
                repos_ok = True
        self._no_run_btn.config(state="normal" if (vault_ok and repos_ok) else "disabled")

    def _no_run(self) -> None:
        if self._no_run_btn["state"] == "disabled":
            return
        vault = os.path.abspath(self._no_vault.get().strip())
        repos = self._no_repos.get().strip()
        self.win.destroy()
        self._on_submit("night-operator", {"vault": vault, "repos": repos})


# ── VaultControl ───────────────────────────────────────────────────────────────

class VaultControl:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Vault Control")
        self.root.configure(bg=BG)
        self.root.geometry("760x700")
        self.root.minsize(640, 560)
        self.screenpipe_proc = None
        self.status_var = tk.StringVar(value="unknown")
        self._path_config = PathConfig(self._build_env(), SCRIPT_DIR)
        self._build_ui()
        self._poll_screenpipe()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = self.root
        hdr = tk.Frame(root, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(16, 0))
        tk.Label(hdr, text="⬡ Vault Control", font=("Inter", 15, "bold"),
                 bg=BG, fg=FG).pack(side="left")
        tk.Label(hdr, text="memory · skills · swarm · pipeline",
                 font=("Inter", 9), bg=BG, fg=FG_DIM).pack(side="left", padx=(10, 0))

        self._section_label(root, "SCREENPIPE SERVICE")
        sp_frame = self._card_frame(root)
        row = tk.Frame(sp_frame, bg=SURFACE)
        row.pack(fill="x", padx=14, pady=10)
        self.dot = tk.Label(row, text="●", font=("Inter", 13), bg=SURFACE, fg=FG_DIM)
        self.dot.pack(side="left")
        self.status_lbl = tk.Label(row, textvariable=self.status_var,
                                   font=("Inter", 9), bg=SURFACE, fg=FG_DIM)
        self.status_lbl.pack(side="left", padx=(6, 0))
        self._action_btn(row, "■  Stop",  self._stop_screenpipe,  RED,    "right", (0, 0))
        self._action_btn(row, "▶  Start", self._start_screenpipe, ACCENT, "right", (0, 8))

        self._section_label(root, "VAULT OS")
        self._button_grid(root, [
            ("🌙  Night Operator",    self._run_night_operator,   TEAL),
            ("📋  Project Snapshot…", self._run_project_snapshot, TEAL),
            ("📂  Open Last Report",  self._run_open_last_report, "#9b8afb"),
        ], cols=3)

        self._section_label(root, "SWARM COLONY")
        self._button_grid(root, [
            ("🐝  Swarm Dashboard",    self._run_swarm_dashboard, TEAL),
            ("⬡  Graph Analyze",       self._run_graph_analyze,   TEAL),
            ("⬡  Skill from Memopipe", self._run_skill_memopipe,  "#4ade80"),
            ("◎  Skill Audit",         self._run_skill_audit,     "#9b8afb"),
            ("✎  Skill Log",           self._run_skill_log,       "#9b8afb"),
        ], cols=3)

        self._section_label(root, "MEMORY COMMANDS")
        self._button_grid(root, [
            ("🧠  Memory Check",  self._run_memory_check,  ACCENT),
            ("↑  Promote Loop",   self._run_promote,        "#5ba3f5"),
            ("~  Daily Summary",  self._run_screenpipe_py,  "#5ba3f5"),
            ("◈  Connections",    self._run_connections,    "#9b8afb"),
            ("✉  Inbox",          self._run_inbox,          "#9b8afb"),
            ("≠  Contradict",     self._run_contradict,     FG_DIM),
        ], cols=3)

        self._section_label(root, "SKILLS & QUERY")
        self._button_grid(root, [
            ("📋  Gaps",         self._run_gaps,          ACCENT),
            ("✎  Skill Capture", self._run_skill_capture, "#5ba3f5"),
            ("◑  Synthesize…",   self._run_synthesize,    "#9b8afb"),
            ("?  Ask Vault…",    self._run_ask,           "#5ba3f5"),
            ("✍  Write Prep…",   self._run_write_prep,    "#9b8afb"),
        ], cols=3)

        self._section_label(root, "OUTPUT")
        self.out = scrolledtext.ScrolledText(
            root, wrap="word", bg=SURFACE, fg=FG, insertbackground=FG,
            font=_mono(), bd=0, highlightthickness=1, highlightbackground=BORDER,
            relief="flat", state="disabled", padx=12, pady=8)
        self.out.pack(fill="both", expand=True, padx=20, pady=(0, 14))
        for tag, color in [("dim", FG_DIM), ("ok", GREEN), ("err", RED),
                           ("warn", AMBER), ("swarm", TEAL)]:
            self.out.tag_config(tag, foreground=color)
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

    def _action_btn(self, parent: tk.Widget, text: str, cmd, color: str,
                    side: str = "left", padx: tuple = (8, 0)) -> tk.Button:
        b = tk.Button(parent, text=text, command=cmd,
                      bg=color, fg="#fff", activebackground=color,
                      activeforeground="#fff", relief="flat", bd=0,
                      font=("Inter", 9, "bold"), padx=10, pady=4, cursor="hand2")
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
            self.dot.config(fg=GREEN);  self.status_var.set("Running");  self.status_lbl.config(fg=GREEN)
        elif self.screenpipe_proc is not None:
            self.dot.config(fg=AMBER);  self.status_var.set("Starting…"); self.status_lbl.config(fg=AMBER)
        else:
            self.dot.config(fg=FG_DIM); self.status_var.set("Stopped");  self.status_lbl.config(fg=FG_DIM)

    def _is_screenpipe_running(self) -> bool:
        try:
            return subprocess.run(["pgrep", "-f", "screenpipe"],
                                  capture_output=True, timeout=3).returncode == 0
        except Exception:
            return False

    # ── screenpipe start / stop ────────────────────────────────────────────────

    def _start_screenpipe(self) -> None:
        if self._is_screenpipe_running():
            self._log("Screenpipe already running.\n", "warn"); return
        script = os.path.join(SCRIPT_DIR, "start-screenpipe.sh")
        if not os.path.exists(script):
            self._log(f"ERROR: {script} not found.\n", "err"); return
        self._log("▶ Starting screenpipe…\n", "dim")
        def _launch() -> None:
            try:
                self.screenpipe_proc = subprocess.Popen(
                    ["bash", script], cwd=SCRIPT_DIR,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, preexec_fn=os.setsid)
                for line in self.screenpipe_proc.stdout:
                    self._log(line)
                self.screenpipe_proc.wait()
                self.screenpipe_proc = None
                self._log("Screenpipe process exited.\n", "warn")
            except Exception as exc:
                self._log(f"ERROR: {exc}\n", "err")
        threading.Thread(target=_launch, daemon=True).start()
        self.dot.config(fg=AMBER); self.status_var.set("Starting…")

    def _stop_screenpipe(self) -> None:
        stopped = False
        if self.screenpipe_proc and self.screenpipe_proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.screenpipe_proc.pid), signal.SIGTERM)
                self.screenpipe_proc = None; stopped = True
            except Exception as exc:
                self._log(f"WARN: {exc}\n", "warn")
        try:
            if subprocess.run(["pkill", "-f", "screenpipe"],
                              capture_output=True, timeout=5).returncode == 0:
                stopped = True
        except Exception:
            pass
        self._log("■ Screenpipe stopped.\n" if stopped else "Screenpipe was not running.\n",
                  "warn" if stopped else "dim")
        self._check_screenpipe_status()

    # ── vault os ──────────────────────────────────────────────────────────────

    def _vault_path(self) -> str:
        env = self._build_env()
        return (env.get("VAULT_PATH") or env.get("OBSIDIAN_VAULT_PATH") or "").strip().strip('"')

    def _vault_repos(self) -> str:
        return self._build_env().get("VAULT_OS_REPOS", "").strip().strip('"')

    def _run_night_operator(self) -> None:
        vault = self._vault_path()
        repos = self._vault_repos()
        if vault and repos:
            self._run("vault-night-operator",
                      f"'{PYTHON}' vault_night_operator.py "
                      f"--vault {shlex.quote(vault)} --repos {shlex.quote(repos)}",
                      header_tag="swarm")
        else:
            self._open_tool_modal("night-operator")

    def _run_project_snapshot(self) -> None:
        self._open_tool_modal("project-snapshot")

    def _run_open_last_report(self) -> None:
        import datetime
        vault = self._vault_path()
        if not vault:
            self._log("ERROR: VAULT_PATH not set in .env\n", "err"); return
        today = datetime.date.today().isoformat()
        report = os.path.join(vault, "06 - Automation", "Nightly Reports", f"{today}.md")
        if not os.path.exists(report):
            self._log(f"No report found for today ({today}).\n", "warn"); return
        try:
            self._log(f"\n📂 {os.path.basename(report)}\n", "swarm")
            self._log(open(report, encoding="utf-8").read() + "\n")
        except Exception as exc:
            self._log(f"ERROR reading report: {exc}\n", "err")

    # ── swarm ──────────────────────────────────────────────────────────────────

    def _run_swarm_dashboard(self) -> None:
        self._run("swarm-dashboard", f"'{PYTHON}' vault_intelligence.py swarm-dashboard",
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
        self._open_tool_modal("skill-audit")

    def _run_skill_log(self) -> None:
        self._open_tool_modal("skill-log")

    # ── memory ─────────────────────────────────────────────────────────────────

    def _run_memory_check(self) -> None:
        self._run("memory-check", f"bash '{os.path.join(SCRIPT_DIR, 'memory-check')}'")

    def _run_promote(self) -> None:
        self._run("promote", f"'{PYTHON}' vault_intelligence.py promote")

    def _run_screenpipe_py(self) -> None:
        self._run("Screenpipe-to-Obsidian.py", f"'{PYTHON}' Screenpipe-to-Obsidian.py")

    def _run_connections(self) -> None:
        self._run("connections", f"'{PYTHON}' vault_intelligence.py connections")

    def _run_inbox(self) -> None:
        self._run("inbox", f"'{PYTHON}' vault_intelligence.py inbox")

    def _run_contradict(self) -> None:
        self._run("contradict", f"'{PYTHON}' vault_intelligence.py contradict")

    # ── skills ─────────────────────────────────────────────────────────────────

    def _run_gaps(self) -> None:
        self._run("gaps --scope Memory",
                  f"'{PYTHON}' vault_intelligence.py gaps --scope Memory")

    def _run_skill_capture(self) -> None:
        self._open_tool_modal("skill-capture")

    def _run_synthesize(self) -> None:
        self._open_tool_modal("synthesize")

    def _run_ask(self) -> None:
        self._open_tool_modal("ask")

    def _run_write_prep(self) -> None:
        self._open_tool_modal("write-prep")

    # ── tool modal wiring ──────────────────────────────────────────────────────

    def _open_tool_modal(self, tool_id: str) -> None:
        self._path_config = PathConfig(self._build_env(), SCRIPT_DIR)
        ToolModal(self.root, tool_id, self._execute_tool, self._path_config)

    def _execute_tool(self, tool_id: str, values: dict[str, str]) -> None:
        if tool_id == "project-snapshot":
            repo = values["repo"]
            script = values.get("script", "")
            if not script:
                # fallback in case panel was bypassed
                local = os.path.join(repo, "scripts", "project_snapshot.py")
                bundled = os.path.join(SCRIPT_DIR, "scripts", "project_snapshot.py")
                script = local if os.path.exists(local) else (
                    bundled if os.path.exists(bundled) else "")
            if not script:
                self._log(
                    f"ERROR: No project_snapshot.py found in {repo}/scripts/ "
                    f"or {SCRIPT_DIR}/scripts/\n", "err")
                return
            self._path_config.set_last_snapshot_repo(repo)
            # if the script lives inside the target repo, run it in-place;
            # if it's the bundled copy, pass the target via --repo
            if script.startswith(repo + os.sep):
                cmd = f"'{PYTHON}' {shlex.quote(script)} --write"
            else:
                cmd = f"'{PYTHON}' {shlex.quote(script)} --repo {shlex.quote(repo)} --write"
            self._run(f"project-snapshot {os.path.basename(repo)}", cmd,
                      header_tag="swarm")

        elif tool_id == "night-operator":
            vault = values["vault"]
            repos = values["repos"]
            self._path_config.set_last_vault_path(vault)
            self._run("vault-night-operator",
                      f"'{PYTHON}' vault_night_operator.py "
                      f"--vault {shlex.quote(vault)} --repos {shlex.quote(repos)}",
                      header_tag="swarm")

        elif tool_id == "skill-audit":
            slug = values["slug"]
            self._run(f"skill-audit {slug}",
                      f"'{PYTHON}' vault_intelligence.py skill-audit '{slug}'",
                      header_tag="swarm")

        elif tool_id == "skill-log":
            slug, obs = values["slug"], values["obs"]
            self._run(f"skill-log {slug}",
                      f"'{PYTHON}' vault_intelligence.py skill-log '{slug}' '{obs}'",
                      header_tag="swarm")

        elif tool_id == "skill-capture":
            self._run("skill-capture",
                      f"'{PYTHON}' vault_intelligence.py skill-capture "
                      f"{shlex.quote(values['text'])}")

        elif tool_id == "synthesize":
            topic = values["topic"]
            self._run(f"synthesize {topic!r}",
                      f"'{PYTHON}' vault_intelligence.py synthesize '{topic}'")

        elif tool_id == "ask":
            q = values["question"]
            self._run(f"ask {q!r}",
                      f"'{PYTHON}' vault_intelligence.py ask '{q}'")

        elif tool_id == "write-prep":
            topic = values["topic"]
            self._run(f"write-prep {topic!r}",
                      f"'{PYTHON}' vault_intelligence.py write-prep '{topic}'")

    # ── generic runner ─────────────────────────────────────────────────────────

    def _run(self, label: str, cmd: str,
             shell: bool = True, header_tag: str = "dim") -> None:
        self._log(f"\n$ {label}\n", header_tag)
        def _worker() -> None:
            env = self._build_env()
            try:
                proc = subprocess.Popen(
                    cmd, shell=shell, cwd=SCRIPT_DIR, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
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

    def _log(self, text: str, tag: str | None = None) -> None:
        def _do() -> None:
            self.out.config(state="normal")
            self.out.insert("end", text, tag) if tag else self.out.insert("end", text)
            self.out.see("end")
            self.out.config(state="disabled")
        self.root.after(0, _do)

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
