#!/bin/bash
# install-screenpipe-deps.sh
#
# Installs the common runtime dependencies needed for Screenpipe on Ubuntu/Debian
# (especially when using the npx method, which ships prebuilt binaries).
#
# This should fix the "libopenblas.so.0" error you're seeing.

set -e

echo "=== Installing Screenpipe runtime dependencies ==="

sudo apt-get update

sudo apt-get install -y \
    libopenblas0 \
    libgomp1 \
    ffmpeg \
    tesseract-ocr \
    libasound2t64 \
    libavformat60 \
    libavcodec60 \
    libavutil58 \
    libswresample4

echo ""
echo "=== Done ==="
echo "Now try running Screenpipe again with:"
echo ""
echo "npx screenpipe@latest record \\"
echo "  --enable-ocr \\"
echo "  --audio-device \"screenpipe-capture.monitor\""
echo ""
echo "Make sure you have already run:"
echo "  ./setup-audio-for-screenpipe.sh"
echo "and moved Spotify with:"
echo "  ./move-spotify-to-real-audio.sh"
echo ""
echo "If you still get missing library errors after this, we'll switch to building from source (more reliable on Linux)."
