#!/usr/bin/env python3
"""
vault_primitives.py — Machine-readable representation of the vault's core architectural invariants.

This module defines the high-signal primitives from the personal memory system
that AI agents (in caitlin-brain or elsewhere) should treat as *native constraints*,
not just text to be retrieved.

Goal (Option D): Make open loops, guardrails, and memory class policies first-class
concepts that agents must understand, query, and respect during reasoning and action.

These are designed to be serializable to clean JSON for agent consumption.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryClass(str, Enum):
    """Explicit memory classes with different policies (anti-bloat foundation)."""
    MEMORY_CORE = "MemoryCore"      # Sacred, tiny, highest priority, always fast
    INBOX = "Inbox"                 # Temporary airlock, strict limits, auto-archive
    ACTIVE = "Active"               # Current serious projects (limited bloat allowed)
    COLD = "Cold"                   # Lower priority, can be deprioritized or excluded
    ARCHIVE = "Archive"             # Heavy stuff, excluded from most operations by default


@dataclass
class MemoryClassPolicy:
    """Policy rules attached to a MemoryClass."""
    max_size_mb: Optional[int] = None
    max_files: Optional[int] = None
    allow_toxic_patterns: bool = False
    priority_for_agents: int = 50          # Higher = more important for agents to consider
    description: str = ""


# Default policies (should be kept in sync with vault_guard.py logic)
DEFAULT_MEMORY_CLASS_POLICIES: Dict[MemoryClass, MemoryClassPolicy] = {
    MemoryClass.MEMORY_CORE: MemoryClassPolicy(
        max_size_mb=150,
        max_files=1000,
        allow_toxic_patterns=False,
        priority_for_agents=100,
        description="Sacred high-signal core. Agents should treat content here as high-authority personal truth.",
    ),
    MemoryClass.INBOX: MemoryClassPolicy(
        max_size_mb=500,
        max_files=2000,
        allow_toxic_patterns=False,
        priority_for_agents=20,
        description="Temporary conversion zone. Content here is transient and lower trust until promoted.",
    ),
    MemoryClass.ACTIVE: MemoryClassPolicy(
        priority_for_agents=70,
        description="Current serious work. Agents should pay strong attention but respect scope limits.",
    ),
    MemoryClass.COLD: MemoryClassPolicy(
        priority_for_agents=30,
        description="Background / lower urgency material.",
    ),
    MemoryClass.ARCHIVE: MemoryClassPolicy(
        priority_for_agents=10,
        description="Historical or heavy material. Agents should rarely surface unless explicitly asked.",
    ),
}


class OpenLoopStatus(str, Enum):
    ACTIVE = "active"
    EVAPORATING = "evaporating"   # 14+ days unseen — critical failure mode
    KILLED = "killed"
    PROMOTED = "promoted"         # Turned into Project / Concept / Literature


@dataclass
class OpenLoop:
    """A first-class representation of an unfinished item the user must not forget."""
    fingerprint: str
    text: str
    first_seen: datetime
    last_seen: datetime
    status: OpenLoopStatus = OpenLoopStatus.ACTIVE
    source_note: Optional[str] = None          # Relative path in vault
    tags: List[str] = field(default_factory=list)

    @property
    def age_days(self) -> int:
        return (datetime.now() - self.first_seen).days

    @property
    def is_evaporating(self) -> bool:
        return self.age_days >= 14 and self.status == OpenLoopStatus.ACTIVE

    def to_agent_dict(self) -> Dict[str, Any]:
        """Compact representation optimized for agent reasoning."""
        return {
            "fingerprint": self.fingerprint,
            "text": self.text,
            "age_days": self.age_days,
            "status": self.status.value,
            "is_evaporating": self.is_evaporating,
            "source": self.source_note,
            "tags": self.tags,
        }


@dataclass
class Guardrail:
    """A hard constraint the user has chosen to enforce on their knowledge system."""
    name: str
    description: str
    severity: str = "hard"          # "hard" | "soft" | "warning"
    category: str = "anti_bloat"    # "anti_bloat", "scope", "security", "focus", etc.


@dataclass
class VaultPolicySnapshot:
    """
    A point-in-time snapshot of the vault's core invariants.
    This is the object we want agents to consume and respect.
    """
    timestamp: datetime
    memory_classes: Dict[MemoryClass, MemoryClassPolicy]
    active_open_loops: List[OpenLoop]
    evaporating_loops: List[OpenLoop]
    guardrails: List[Guardrail]
    total_memory_size_mb: Optional[float] = None
    notes: str = "This snapshot represents the user's explicit cognitive guardrails and priorities."


# --- Helper to build a snapshot from current vault state (stub for now) ---

def build_vault_policy_snapshot(vault_path: Path) -> VaultPolicySnapshot:
    """
    Builds a rich, agent-consumable snapshot of the vault's core primitives.

    This is the key function for deep integration (Option D). Agents should
    prefer consuming this structured form over raw RAG when possible.
    """
    from vault_intelligence import _load_loop_state, collect_gaps

    # Load real open loop state + actual gap text
    loop_state = _load_loop_state()
    now = datetime.now()

    # Get rich gap data (this gives us real text + sources)
    try:
        raw_gaps = collect_gaps(["Memory"])
    except Exception:
        raw_gaps = []

    # Build a lookup from fingerprint to real text
    gap_lookup: Dict[str, tuple[str, str]] = {}  # fp -> (text, source)
    for gap in raw_gaps:
        # The fingerprinting logic in vault_intelligence uses a hash of the gap text
        import hashlib
        fp = hashlib.md5(gap.encode("utf-8")).hexdigest()[:16]
        gap_lookup[fp] = (gap, "unknown")  # source is not perfectly tracked in current gaps

    active_loops: List[OpenLoop] = []
    evaporating_loops: List[OpenLoop] = []

    for fp, first_seen_str in loop_state.items():
        try:
            first_seen = datetime.strptime(first_seen_str, "%Y-%m-%d")
            age = (now - first_seen).days
            status = OpenLoopStatus.EVAPORATING if age >= 14 else OpenLoopStatus.ACTIVE

            text, source = gap_lookup.get(fp, (fp, "unknown"))

            loop = OpenLoop(
                fingerprint=fp,
                text=text,
                first_seen=first_seen,
                last_seen=first_seen,
                status=status,
                source_note=source,
            )
            if loop.is_evaporating:
                evaporating_loops.append(loop)
            else:
                active_loops.append(loop)
        except Exception:
            continue

    # Core hard guardrails (sourced from vault_guard philosophy)
    guardrails = [
        Guardrail(
            name="no_dev_workspaces",
            description="Never allow venvs, node_modules, .git/objects, builds, or large media inside the vault.",
            severity="hard",
            category="anti_bloat",
        ),
        Guardrail(
            name="memory_core_size_limit",
            description="Memory/ core must stay tiny and fast (<150MB target).",
            severity="hard",
            category="anti_bloat",
        ),
        Guardrail(
            name="evaporating_loops_must_be_addressed",
            description="Items unseen for 14+ days enter EVAPORATING state and require an explicit kill or commit decision.",
            severity="hard",
            category="focus",
        ),
    ]

    return VaultPolicySnapshot(
        timestamp=now,
        memory_classes=DEFAULT_MEMORY_CLASS_POLICIES,
        active_open_loops=active_loops,
        evaporating_loops=evaporating_loops,
        guardrails=guardrails,
        notes="Hydrated from actual vault gaps + loop state. Full open loop text is now included where available.",
    )


def export_structured_for_agents(vault_path: Path, output_path: Optional[Path] = None) -> Path:
    """
    Exports the vault's core primitives in a clean, agent-optimized JSON format.
    This is the preferred bridge for deep integration with systems like caitlin-brain.
    """
    snapshot = build_vault_policy_snapshot(vault_path)

    if output_path is None:
        export_dir = Path.home() / "Backups" / "Vault-Agent-Exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        output_path = export_dir / f"vault-primitives-{today}.json"

    data = {
        "timestamp": snapshot.timestamp.isoformat(),
        "memory_class_policies": {
            k.value: {
                "max_size_mb": v.max_size_mb,
                "max_files": v.max_files,
                "priority_for_agents": v.priority_for_agents,
                "description": v.description,
            }
            for k, v in snapshot.memory_classes.items()
        },
        "active_open_loops": [loop.to_agent_dict() for loop in snapshot.active_open_loops],
        "evaporating_open_loops": [loop.to_agent_dict() for loop in snapshot.evaporating_loops],
        "guardrails": [g.__dict__ for g in snapshot.guardrails],
        "notes": snapshot.notes,
    }

    output_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"✅ Structured agent export written to: {output_path}")
    return output_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Export vault primitives (open loops, guardrails, memory classes) for AI agents"
    )
    parser.add_argument(
        "--output", type=Path,
        help="Custom output path for the JSON snapshot"
    )
    parser.add_argument(
        "--vault", type=Path,
        default=Path(os.environ.get("VAULT_PATH", ".")),
        help="Path to the Obsidian vault (defaults to VAULT_PATH env var)"
    )
    args = parser.parse_args()

    out = export_structured_for_agents(args.vault, args.output)
    print(f"\n✅ Agent-ready structured export written to: {out}")
    print("   This JSON contains first-class OpenLoop, Guardrail, and MemoryClass data.")


if __name__ == "__main__":
    main()