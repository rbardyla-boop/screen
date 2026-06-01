#!/usr/bin/env python3
"""
skill_pipeline_experiment.py — Distinguish skill pipeline discovery vs. creation

Hypothesis: Does the pipeline extract existing knowledge (discovery) or
generate new knowledge through forced decomposition (creation)?

Methodology:
1. Measure baseline note count for a domain (clovelearn)
2. Run pipeline synthesis on that domain
3. Measure delta (new notes created)
4. Track weekly: does growth continue or plateau?

Interpretation:
- DISCOVERY: Notes plateau after pipeline runs
- CREATION: Notes continue growing after pipeline stops
"""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

VAULT_PATH = Path.home() / "Documents" / "Obsidian Vault"
DOMAIN = "clovelearn"
RESULTS_FILE = VAULT_PATH / "Memory" / "Outputs" / f"pipeline-experiment-{DOMAIN}.jsonl"


def count_domain_notes(vault: Path, domain: str) -> int:
    """Count all notes mentioning the domain."""
    memory_dir = vault / "Memory"
    if not memory_dir.exists():
        return 0

    count = 0
    for md_file in memory_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            if domain.lower() in content.lower():
                count += 1
        except Exception:
            pass

    return count


def run_synthesis(domain: str) -> bool:
    """Run vault_intelligence.py synthesize on the domain."""
    try:
        result = subprocess.run(
            ["python", "vault_intelligence.py", "synthesize", domain],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def measure_cycle(vault: Path, domain: str) -> dict:
    """Run one measurement cycle: baseline → synthesis → delta."""
    print(f"🔍 Measuring baseline for '{domain}'...", end=" ", flush=True)
    baseline = count_domain_notes(vault, domain)
    print(f"{baseline} notes")

    print(f"🚀 Running synthesis...", end=" ", flush=True)
    success = run_synthesis(domain)
    if not success:
        print("❌ synthesis failed")
        return None
    print("✅")

    print(f"📊 Measuring delta...", end=" ", flush=True)
    after = count_domain_notes(vault, domain)
    delta = after - baseline
    print(f"{after} notes (Δ={delta:+d})")

    return {
        "date": date.today().isoformat(),
        "domain": domain,
        "baseline": baseline,
        "after_synthesis": after,
        "delta": delta,
    }


def log_result(result: dict) -> None:
    """Append result to experiment log (JSONL format)."""
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")
    print(f"\n📝 Logged to {RESULTS_FILE.name}")


def analyze_trajectory(vault: Path, domain: str) -> None:
    """Analyze all results so far: discovery or creation?"""
    if not RESULTS_FILE.exists():
        print("\n_(no prior measurements yet)_")
        return

    measurements = []
    try:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                measurements.append(json.loads(line))
    except Exception:
        return

    if not measurements:
        return

    print(f"\n📈 Trajectory Analysis ({len(measurements)} measurements)")
    print("Date       | Baseline | After | Delta | Interpretation")
    print("-----------|----------|-------|-------|----------------")

    deltas = []
    for m in measurements:
        delta = m["delta"]
        deltas.append(delta)
        interp = "📈 growth" if delta > 0 else "⏸️  stable" if delta == 0 else "📉 shrink"
        print(f"{m['date']} | {m['baseline']:8d} | {m['after_synthesis']:5d} | {delta:5d} | {interp}")

    print()
    avg_delta = sum(deltas) / len(deltas) if deltas else 0
    if avg_delta > 2:
        print("🎯 **CREATION SIGNAL**: Notes growing after synthesis. Pipeline generates knowledge.")
    elif avg_delta > 0:
        print("🤔 **MIXED SIGNAL**: Slight growth. Pipeline may discover and create.")
    else:
        print("🔍 **DISCOVERY SIGNAL**: No growth after synthesis. Pipeline extracts existing knowledge.")


def main() -> None:
    if not VAULT_PATH.exists():
        print(f"❌ Vault not found: {VAULT_PATH}")
        sys.exit(1)

    print(f"🧪 Skill Pipeline Experiment: {DOMAIN}")
    print(f"   Vault: {VAULT_PATH}")
    print()

    result = measure_cycle(VAULT_PATH, DOMAIN)
    if not result:
        print("❌ Measurement failed")
        sys.exit(1)

    log_result(result)
    analyze_trajectory(VAULT_PATH, DOMAIN)

    print()
    print("Next: Run this again next week to see the trajectory.")
    print(f"      Weekly schedule: Mondays at 4am")


if __name__ == "__main__":
    main()
