#!/bin/bash
# move-spotify-to-real-audio.sh
#
# Force Spotify to play on your real speakers/headphones
# so it does NOT get recorded by Screenpipe.
#
# Run this after starting Spotify, or put it in a loop / autostart.

REAL_SINK="alsa_output.pci-0000_00_1f.3.analog-stereo"

echo "Moving Spotify audio streams to real hardware ($REAL_SINK)..."

SPOTIFY_PIDS=$(pgrep -f spotify || true)

if [ -z "$SPOTIFY_PIDS" ]; then
    echo "Spotify is not running."
    exit 0
fi

MOVED=0
for pid in $SPOTIFY_PIDS; do
    # Find sink inputs belonging to this Spotify process
    INPUTS=$(pactl list sink-inputs | awk -v pid="$pid" '
        /Sink Input/ { id=$3 }
        /application.process.id/ && $3 == "\"" pid "\"" { print id }
    ' | tr -d '#')

    for input in $INPUTS; do
        if [ -n "$input" ]; then
            echo "  Moving sink-input #$input → $REAL_SINK"
            pactl move-sink-input "$input" "$REAL_SINK" 2>/dev/null && MOVED=$((MOVED+1))
        fi
    done
done

if [ "$MOVED" -gt 0 ]; then
    echo "Moved $MOVED Spotify audio stream(s) to real speakers."
else
    echo "No Spotify audio streams found to move (might take a second after Spotify starts playing)."
fi
