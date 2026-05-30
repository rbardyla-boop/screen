#!/bin/bash
# setup-audio-for-screenpipe.sh (Improved robust version)
#
# Creates a virtual "null sink" called screenpipe-capture.
# Most apps will be routed to it.
# Spotify will be forced to play on your real hardware speakers/headphones.
#
# This way Screenpipe records clean system audio WITHOUT your Spotify music.

set -e

SINK_NAME="screenpipe-capture"
REAL_SINK="alsa_output.pci-0000_00_1f.3.analog-stereo"

echo "=== Setting up robust audio routing for Screenpipe (excluding Spotify) ==="

# Unload any old module with the same name to avoid duplicates
echo "Cleaning up any previous virtual sink..."
pactl list short modules | grep "sink_name=$SINK_NAME" | awk '{print $1}' | while read -r id; do
    pactl unload-module "$id" 2>/dev/null || true
done

# Create a null sink. This is very reliable on PipeWire + Pulse layer.
echo "Creating virtual null sink: $SINK_NAME"
MODULE_ID=$(pactl load-module module-null-sink \
    sink_name="$SINK_NAME" \
    sink_properties="device.description='Screenpipe-Capture (No Spotify)'")

if [ -z "$MODULE_ID" ]; then
    echo "ERROR: Failed to create virtual sink."
    exit 1
fi

echo "Virtual sink created (module $MODULE_ID)"

# Set it as the default sink so new apps use it
echo "Setting $SINK_NAME as default sink..."
pactl set-default-sink "$SINK_NAME" || true

echo ""
echo "=== Current audio situation ==="
echo "Default sink: $(pactl get-default-sink)"
echo ""

# Move Spotify streams to real hardware if it's running
SPOTIFY_PIDS=$(pgrep -f spotify || true)
if [ -n "$SPOTIFY_PIDS" ]; then
    echo "Spotify is running. Moving its audio to real hardware..."
    for pid in $SPOTIFY_PIDS; do
        pactl list sink-inputs | awk -v pid="$pid" '
            /Sink Input/ { id=$3 }
            /application.process.id/ && $3 == "\"" pid "\"" {
                print id
            }' | tr -d '#' | while read -r input; do
                if [ -n "$input" ]; then
                    echo "  Moving sink-input #$input (Spotify) → $REAL_SINK"
                    pactl move-sink-input "$input" "$REAL_SINK" 2>/dev/null || true
                fi
            done
    done
else
    echo "Spotify not currently running."
fi

echo ""
echo "=== SUCCESS ==="
echo "Virtual capture sink created: $SINK_NAME"
echo "Its monitor source for Screenpipe: $SINK_NAME.monitor"
echo ""
echo "Next step: Start Screenpipe with:"
echo "  npx screenpipe@latest record -i \"$SINK_NAME.monitor\" -a whisper-large-v3-turbo --filter-music -p 3030"
echo ""
echo "Tip: If you restart your computer, re-run this script (or we can make it a systemd service)."
