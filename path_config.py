"""Path persistence and discovery for Vault Control."""
import json
import os

_CONFIG_FILE = os.path.expanduser("~/.config/vault-control/paths.json")
_HOME = os.path.expanduser("~")


def _load_data() -> dict:
    try:
        with open(_CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "recent_paths": [],
            "pinned_paths": [],
            "last_project_snapshot_repo": "",
            "last_vault_path": "",
        }


def _save_data(data: dict) -> None:
    os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
    with open(_CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


class PathConfig:
    """Loads, discovers, and persists known paths for Vault Control."""

    def __init__(self, env: dict, app_dir: str) -> None:
        self._env = env
        self._app_dir = app_dir
        self._data = _load_data()

    # ── persistence ───────────────────────────────────────────────────────────

    def add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        lst: list[str] = self._data.setdefault("recent_paths", [])
        if path in lst:
            lst.remove(path)
        lst.insert(0, path)
        self._data["recent_paths"] = lst[:12]
        _save_data(self._data)

    def set_last_snapshot_repo(self, path: str) -> None:
        self._data["last_project_snapshot_repo"] = os.path.abspath(path)
        self.add_recent(path)

    def set_last_vault_path(self, path: str) -> None:
        self._data["last_vault_path"] = os.path.abspath(path)
        self.add_recent(path)

    # ── read ──────────────────────────────────────────────────────────────────

    @property
    def last_snapshot_repo(self) -> str:
        return self._data.get("last_project_snapshot_repo", "")

    @property
    def last_vault_path(self) -> str:
        return self._data.get("last_vault_path", "")

    @property
    def recent_paths(self) -> list[str]:
        return self._data.get("recent_paths", [])

    # ── discovery ─────────────────────────────────────────────────────────────

    def path_cards(self) -> list[dict]:
        """Return all discovered paths as card dicts with label/path/group/type/exists."""
        seen: set[str] = set()
        cards: list[dict] = []

        def _add(label: str, path: str, group: str, ptype: str) -> None:
            if not path:
                return
            norm = os.path.abspath(path)
            if norm in seen:
                return
            seen.add(norm)
            cards.append(
                {
                    "label": label,
                    "path": norm,
                    "group": group,
                    "type": ptype,
                    "exists": os.path.isdir(norm),
                }
            )

        env = self._env

        # vault from env
        for key in ("OBSIDIAN_VAULT_PATH", "VAULT_PATH"):
            v = env.get(key, "").strip().strip('"')
            if v:
                _add("Obsidian Vault", v, "vault", "vault")
                break

        # repos from VAULT_OS_REPOS
        for rp in env.get("VAULT_OS_REPOS", "").split(","):
            rp = rp.strip().strip('"')
            if rp:
                _add(os.path.basename(rp), rp, "known repos", "repo")

        # app dir itself
        _add("Screenpipe-to-Obsidian", self._app_dir, "known repos", "repo")

        # scan ~/Downloads/grok for sibling repos
        grok = os.path.join(_HOME, "Downloads", "grok")
        if os.path.isdir(grok):
            for name in sorted(os.listdir(grok)):
                fp = os.path.join(grok, name)
                if os.path.isdir(fp):
                    _add(name, fp, "known repos", "repo")

        # home shortcuts
        for label, sub in [
            ("Home", ""),
            ("Documents", "Documents"),
            ("Downloads", "Downloads"),
            ("Projects", "Projects"),
        ]:
            p = os.path.join(_HOME, sub) if sub else _HOME
            if os.path.isdir(p):
                _add(label, p, "home", "folder")

        # recent paths (deduplicated by seen set)
        for p in self.recent_paths:
            if p not in seen and os.path.isdir(p):
                _add(os.path.basename(p) or p, p, "recent", "recent")

        return cards
