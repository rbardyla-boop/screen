#!/bin/bash
# start-screenpipe.sh
#
# Recommended way to start Screenpipe for your second brain setup.
#
# Features:
# - Records screen + OCR
# - Records system audio from the "screenpipe-capture" virtual sink (everything except Spotify)
# - Transcribes the audio
# - The data becomes available via the local API that your daily-memory-synthesis.py reads

set -e

# === CONFIGURATION ===
# Change this path to wherever you put the screenpipe binary
SCREENPIPE_BIN="${SCREENPIPE_BIN:-$HOME/screenpipe/screenpipe}"

# The virtual sink we created (everything except Spotify)
AUDIO_SOURCE="screenpipe-capture.monitor"

# === CHECKS ===
if [ ! -x "$SCREENPIPE_BIN" ]; then
    echo "ERROR: Screenpipe binary not found at: $SCREENPIPE_BIN"
    echo ""
    echo "Please either:"
    echo "  1. Set the environment variable: export SCREENPIPE_BIN=/path/to/your/screenpipe"
    echo "  2. Or edit this script and hardcode the correct path"
    echo ""
    echo "You can download the latest Linux binary from:"
    echo "  https://github.com/mediar-ai/screenpipe/releases"
    exit 1
fi

echo "=== Starting Screenpipe for your memory system ==="
echo "Screen recording + vision: enabled"
echo "Audio: system default (mic + output monitor)"
echo "Transcriptions will be available for your daily memory synthesis"
echo ""

# Run Screenpipe with good settings for long-term memory capture
exec "$SCREENPIPE_BIN" record \
    --use-system-default-audio \
    --audio-transcription-engine whisper-tiny \
    --port 3030 \
    --data-dir "$HOME/.screenpipe"
