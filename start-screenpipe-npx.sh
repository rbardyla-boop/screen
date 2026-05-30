#!/bin/bash
# start-screenpipe-npx.sh
#
# Convenient wrapper for running the current npx version of Screenpipe
# with your custom audio routing (system audio without Spotify).

set -e

AUDIO_SOURCE="screenpipe-capture.monitor"

echo "=== Starting Screenpipe via npx (with your Spotify-excluded audio) ==="
echo "Audio device: $AUDIO_SOURCE"
echo "Transcription: whisper-large-v3-turbo + music filter"
echo "API will be on http://localhost:3030"
echo ""

exec npx screenpipe@latest record \
    -i "$AUDIO_SOURCE" \
    -a whisper-large-v3-turbo \
    --filter-music \
    -p 3030 \
    --data-dir "$HOME/.screenpipe"
