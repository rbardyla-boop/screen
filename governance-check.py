#!/usr/bin/env python3
"""
governance-check.py — Monthly governance audit reminder
Checks for expired rules and alerts user to review.

Usage:
    python governance-check.py
    (Scheduled: 1st of each month at 9am)
"""

import re
from datetime import date
from pathlib import Path

VAULT_PATH = Path.home() / "Documents" / "Obsidian Vault"
AUDIT_FILE = VAULT_PATH / "Memory" / "governance-audit.md"


def parse_expiration_dates(audit_file: Path) -> list[dict]:
    """Extract rule expiration dates from governance-audit.md."""
    if not audit_file.exists():
        print("❌ governance-audit.md not found")
        return []

    content = audit_file.read_text(encoding="utf-8")
    results = []

    # Find all "Expires: YYYY-MM-DD" lines
    for match in re.finditer(r"\*\*Expires:\*\*\s+(\d{4}-\d{2}-\d{2})", content):
        expires_str = match.group(1)
        # Try to find the rule name above this line
        pos = match.start()
        rule_section = content[:pos].split("\n")[-5:]  # Last 5 lines before expiry
        rule_name = "Unknown"
        for line in rule_section:
            if line.strip().startswith("### Rule"):
                rule_name = line.replace("###", "").strip()
                break

        try:
            expires_date = date.fromisoformat(expires_str)
            results.append({"rule": rule_name, "expires": expires_date})
        except ValueError:
            pass

    return results


def check_expirations() -> None:
    """Check which rules have expired or are expiring soon."""
    rules = parse_expiration_dates(AUDIT_FILE)
    if not rules:
        print("❌ No expiration dates found in governance-audit.md")
        return

    today = date.today()
    expired = []
    expiring_soon = []

    for rule in rules:
        days_left = (rule["expires"] - today).days
        if days_left < 0:
            expired.append((rule, abs(days_left)))
        elif days_left <= 30:
            expiring_soon.append((rule, days_left))

    # Report
    print(f"📋 Governance Audit Check — {today.isoformat()}")
    print(f"   Total rules under governance: {len(rules)}")
    print()

    if expired:
        print("⚠️  EXPIRED RULES (need review NOW):")
        for rule, days_overdue in expired:
            print(f"   - {rule['rule']}")
            print(f"     Expired {days_overdue} days ago ({rule['expires'].isoformat()})")
        print()

    if expiring_soon:
        print("📅 Expiring Soon (within 30 days):")
        for rule, days_left in expiring_soon:
            print(f"   - {rule['rule']}")
            print(f"     Expires in {days_left} days ({rule['expires'].isoformat()})")
        print()

    if not expired and not expiring_soon:
        print("✅ All rules current. Next review deadline(s):")
        for rule in sorted(rules, key=lambda r: r["expires"])[:3]:
            print(f"   - {rule['rule']} expires {rule['expires'].isoformat()}")

    print()
    print("📖 Full audit: Memory/governance-audit.md")


if __name__ == "__main__":
    check_expirations()
