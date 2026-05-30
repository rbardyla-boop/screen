# Audio Recording Setup (System Audio Minus Spotify)

This is exactly what you asked for:
- Record screen video + OCR
- Record system audio (meetings, videos, voice, browser sound, etc.)
- **Exclude Spotify** so your music doesn't pollute the transcriptions
- Get the audio transcribed automatically
- Transcriptions become searchable in Markdown files for linking into your second brain / open loops

## Files Created

| Script                              | Purpose |
|-------------------------------------|--------|
| `setup-audio-for-screenpipe.sh`     | One-time setup that creates a virtual audio sink and routes most apps to it |
| `move-spotify-to-real-audio.sh`     | Force Spotify back to your real speakers/headphones (run after starting Spotify) |
| `start-screenpipe.sh`               | Recommended way to launch Screenpipe with the correct audio source |

## Step-by-Step Setup

### 1. Run the audio routing setup (do this once)

```bash
cd ~/Downloads/grok/Screenpipe-to-Obsidian
./setup-audio-for-screenpipe.sh
```

This creates a virtual sink called `screenpipe-capture`. Most apps will now output to it.

### 2. Start Spotify (if you want music)

After Spotify starts playing sound, run:

```bash
./move-spotify-to-real-audio.sh
```

This moves Spotify's audio back to your real speakers so it won't be recorded.

### 3. Install Screenpipe

Download the latest Linux binary from:
https://github.com/mediar-ai/screenpipe/releases

Put it somewhere (example: `~/screenpipe/screenpipe`) and make it executable.

### 4. Start recording with the right settings (current npx version)

Use this command (the old flags like `--enable-ocr` no longer exist):

```bash
./start-screenpipe-npx.sh
```

Or run directly:

```bash
npx screenpipe@latest record \
  -i "screenpipe-capture.monitor" \
  -a whisper-large-v3-turbo \
  --filter-music \
  -p 3030
```

This uses:
- Your virtual sink (everything except Spotify)
- Good quality transcription
- Music filtering as extra protection
- The local API on port 3030 (so your `daily-memory-synthesis.py` and `memory-check` can read it)

## How it connects to your memory system

Once Screenpipe is running with the above settings:

- Your existing `memory-check` command will automatically pull the transcribed audio from that day.
- The new `daily-memory-synthesis.py` will analyze the transcripts along with screen activity.
- Transcribed conversations, videos you watched, meetings, etc. will appear in:
  - `Memory/Daily Reviews/YYYY-MM-DD.md`
  - Your `Open-Loops.md` when relevant
  - The Unfinished Work Dashboard when they contain tasks or intentions

This gives you searchable, linkable text from audio without your Spotify playlists cluttering everything.

## Making it start automatically

If you want Screenpipe + the audio routing to start on login, tell me and I'll create proper systemd user services for both.

## Important Notes

- The virtual sink setup is not 100% permanent across reboots. You may need to re-run `setup-audio-for-screenpipe.sh` after restarting your computer (or we can make it a service).
- Spotify sometimes creates new audio streams. Running `move-spotify-to-real-audio.sh` after it starts is the safest.
- Transcription uses local Whisper (via Screenpipe). It will use some CPU/GPU while transcribing.
