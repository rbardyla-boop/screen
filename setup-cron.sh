#!/bin/bash
# setup-cron.sh — Install vault_night_operator cron jobs
# Usage: bash setup-cron.sh

VAULT_PATH="$HOME/Documents/Obsidian Vault"
REPOS_PATH="/home/thebackhand/Downloads/grok/Screenpipe-to-Obsidian,/home/thebackhand/Downloads/grok/memopipe"
SCRIPT_PATH="/home/thebackhand/Downloads/grok/Screenpipe-to-Obsidian/vault_night_operator.py"

# Validate
if [ ! -d "$VAULT_PATH" ]; then
    echo "ERROR: Vault path does not exist: $VAULT_PATH"
    exit 1
fi

if [ ! -f "$SCRIPT_PATH" ]; then
    echo "ERROR: Script not found: $SCRIPT_PATH"
    exit 1
fi

echo "Installing cron jobs..."
echo ""
echo "Vault: $VAULT_PATH"
echo "Repos: $REPOS_PATH"
echo "Script: $SCRIPT_PATH"
echo ""

# Create temp crontab file
CRON_FILE=$(mktemp)

# Export current crontab
crontab -l > "$CRON_FILE" 2>/dev/null || true

# Add 6am morning briefing
echo "0 6 * * * cd /home/thebackhand/Downloads/grok/Screenpipe-to-Obsidian && source .venv/bin/activate && python vault_night_operator.py --vault \"$VAULT_PATH\" --repos \"$REPOS_PATH\" --briefing 2>&1 | logger -t vault_operator" >> "$CRON_FILE"

# Add 10pm nightly report
echo "0 22 * * * cd /home/thebackhand/Downloads/grok/Screenpipe-to-Obsidian && source .venv/bin/activate && python vault_night_operator.py --vault \"$VAULT_PATH\" --repos \"$REPOS_PATH\" 2>&1 | logger -t vault_operator" >> "$CRON_FILE"

# Install updated crontab
crontab "$CRON_FILE"
rm "$CRON_FILE"

echo ""
echo "✅ Cron jobs installed:"
echo "  - 6:00am  — Morning briefing (--briefing)"
echo "  - 10:00pm — Nightly report"
echo ""
echo "Verify with: crontab -l"
