# Faceless Reel Pipeline

Render vertical 1080×1920 Facebook Reels from a JSON script. The pipeline makes
**no LLM API calls** — you generate the script separately (in Claude Code,
ChatGPT, locally, or by hand) and pass it in via `--script`.

```bash
# Step A: generate a script (one time, per topic)
#   → copy prompts/script-generation.md into Claude Code
#   → append your topic, save the output JSON to script.json

# Step B: render the reel
python3 reel.py --script script.json
# → out/final.mp4 (30-45s voiceover + 2.5s green-text outro, ready for Facebook Reels)
```

## What it does

1. **Script** — *(you provide)* a JSON file with hook + 3 tips + CTA. Each section has a `queries` list of 2–3 Pexels search terms; the renderer rotates through them as it cuts.
2. **Voiceover** — **Kokoro TTS** (82M-param open-source model, runs on CPU, MIT license). Voice is hardcoded to `am_michael` for brand consistency, played at `speed=0.95` with sentence-level micro-pauses for breathing rhythm. Override only when prototyping with `--voice`.
3. **Word timestamps** — `faster-whisper` (`base` model, CPU) produces per-word timing.
4. **Hook + body with the 3-second rule** — the hook is cut into 1.5–2 s shots with a Ken Burns 1.0 → 1.08 zoom (highest-retention real estate in a Reel). Body sections cut into 2.5–3 s shots. Within each section, transitions vary: 60% fade / 25% zoom-in / 15% slide (deterministic by cut index, so re-renders match). Hard cuts between sections.
5. **Captions** — ASS subtitle file, bold green (`#00FF66`) word-by-word with Gaussian-blurred shadow.
6. **Background music** — auto-picked at random from [`bg-music/`](#background-music), looped, mixed at ~-22 dB, faded out over the last 1.5 s.
7. **Outro overlay** — the CTA footage extends 2.5 s past the voiceover, with the outro text fading in over a stepped-gradient darken at the bottom of the frame. No separate solid card.
8. **Assemble** — `ffmpeg` trims/scales clips (blurred-bg fallback for non-portrait), xfades within sections, concats sections, draws the outro gradient, burns captions, mixes audio, encodes H.264 + AAC.

## Setup

**Prerequisites:** macOS or Linux, an ffmpeg build with **libass** (for caption burn-in), Python 3.12.

The default Homebrew `ffmpeg` formula does **not** include libass. Use `ffmpeg-full` instead (or any build that includes the `subtitles` filter — verify with `ffmpeg -filters | grep subtitles`).

Python 3.14 currently lacks an `onnxruntime` wheel (a transitive dep of `faster-whisper`), so this project uses Python 3.12.

```bash
# 1. Install ffmpeg with libass
brew install ffmpeg-full
# ffmpeg-full is keg-only, so its binaries aren't on PATH by default.
# Either add it to PATH:
echo 'export PATH="/usr/local/opt/ffmpeg-full/bin:$PATH"' >> ~/.zshrc
# OR set FFMPEG_BIN / FFPROBE_BIN env vars in .env (see below).

# 2. Install Python 3.12 (if not already)
brew install python@3.12

# 3. Create venv and install deps
/usr/local/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Note: first install pulls in torch (~250MB) for Kokoro. Total dep size ~1GB.

# 4. Configure environment
cp .env.example .env
# Then edit .env:
#   PEXELS_API_KEY=...   (https://www.pexels.com/api/)
#   FFMPEG_BIN=/usr/local/opt/ffmpeg-full/bin/ffmpeg     (only if not on PATH)
#   FFPROBE_BIN=/usr/local/opt/ffmpeg-full/bin/ffprobe   (only if not on PATH)
```

**First run** downloads the Kokoro model (~330 MB) and a spaCy English model.
This takes 1–2 minutes — subsequent runs use the cache.

## Workflow

### Step A — Generate a script

Open [`prompts/script-generation.md`](prompts/script-generation.md), copy the prompt block into Claude Code (claude.ai/code) or any LLM, replace the `<YOUR TOPIC HERE>` placeholder with your topic, and save the resulting JSON as `script.json`.

The expected schema is:

```json
{
  "hook": { "text": "...", "queries": ["...", "...", "..."] },
  "tips": [
    { "text": "...", "queries": ["...", "...", "..."] },
    { "text": "...", "queries": ["...", "...", "..."] },
    { "text": "...", "queries": ["...", "...", "..."] }
  ],
  "cta":  { "text": "...", "queries": ["...", "..."] }
}
```

`tips` must contain exactly 3 items. Each section gets a `queries` list (2–3 entries recommended) — the pipeline rotates through them as it cuts sub-segments, so more queries = more visual variety. Older scripts with a single `search_query` or `query` string still load (treated as a one-element list) but new scripts should use `queries`.

For symptoms or body-related content, write queries that **show body parts** — viewers self-identify and retention shoots up. Examples in [prompts/script-generation.md](prompts/script-generation.md).

### Step B — Render

```bash
# Full render with defaults (auto-picks music from bg-music/, green outro)
.venv/bin/python reel.py --script script.json

# Cheap topic verification (validate schema + Pexels search, no TTS/whisper/render)
.venv/bin/python reel.py --script script.json --dry-run

# Specific music file (overrides bg-music/ auto-pick)
.venv/bin/python reel.py --script script.json --music ./my-track.mp3

# Skip background music
.venv/bin/python reel.py --script script.json --no-music

# Custom voice, outro text, outro color
.venv/bin/python reel.py --script script.json \
    --voice am_michael \
    --outro-text "SAVE THIS|FOR LATER" \
    --outro-color "#FF3366"

# Skip the outro entirely
.venv/bin/python reel.py --script script.json --no-outro
```

### Flags

| Flag                    | Default                       | Description                                                          |
| ----------------------- | ----------------------------- | -------------------------------------------------------------------- |
| `--script PATH`         | *(required)*                  | Path to the script JSON file.                                        |
| `--out PATH`            | `out/final.mp4`               | Output MP4 path.                                                     |
| `--voice NAME`          | `am_michael`                  | Kokoro voice. Brand voice is locked — override only when prototyping. |
| `--music PATH`          | auto from `bg-music/`         | Background music file. Mixed at ~-22 dB, looped, faded out at end.   |
| `--no-music`            | off                           | Skip music even if files exist in `bg-music/`.                       |
| `--no-outro`            | off                           | Skip the 2.5 s outro overlay.                                        |
| `--outro-text "L1\|L2"` | `LIKE AND FOLLOW\|FOR MORE`   | Override outro text. `\|` is the line separator.                     |
| `--text-color HEX`      | `#00FF66`                     | Color for **all** on-screen text (body captions + outro).            |
| `--dry-run`             | off                           | Validate script + Pexels search + cut plan only. No render.          |
| `--keep-work`           | off                           | Keep `work/<ts>/` after success.                                     |

## Voice (brand-locked blend)

The default voice is a **custom blend** of three Kokoro voices, averaged in
embedding space with equal weights: `af_alloy + am_echo + am_fenrir`. The blend
was auditioned on the Kokoro web demo and chosen for a warm-but-authoritative
narrator quality — keep this consistent across all uploads for audience
recognition. The blend constant lives in
[`pipeline/tts.py`](pipeline/tts.py).

```python
# pipeline/tts.py
DEFAULT_VOICE_BLEND = ["af_alloy", "am_echo", "am_fenrir"]
DEFAULT_SPEED = 1.0
```

Pacing is `speed=1.0` (Kokoro's natural pace — matches the kokoroai.org web
demo). A ~140 ms micro-pause is inserted between sentences for natural
breathing. Inter-section silences are **400 ms** after the hook, **250 ms**
between tips, and **500 ms** before the CTA for editorial rhythm.

The `--voice` CLI flag accepts either a single Kokoro voice name (`--voice am_michael`)
or a comma-separated blend (`--voice af_alloy,am_echo,am_fenrir`). Blends are
averaged by `torch.mean(torch.stack(voice_tensors), dim=0)` — `pipeline/tts.py`
caches loaded voice tensors so repeated calls inside one process don't repeat
the load.

```bash
# Default — locked brand blend
python reel.py --script script.json

# Single voice for testing
python reel.py --script script.json --voice am_michael

# Custom blend
python reel.py --script script.json --voice "am_michael,am_fenrir"

# Override speed
python reel.py --script script.json --speed 1.0
```

## The 3-second rule (and the hook gets it harder)

Reels retention drops sharply when a single visual stays on screen for more than ~3 s. The pipeline enforces this aggressively:

- **Hook section (first 3-5 s of the reel) gets 1.5–2 s cuts** — viewers decide whether to keep watching in the first few seconds, so the visuals need to refresh constantly. Hook clips also get a subtle **Ken Burns zoom** (1.0 → 1.08 over the clip duration) so even within a single 2 s shot there's continuous motion.
- **Body sections get 2.5–3 s cuts.**
- **Transitions within a section vary by cut index**, deterministically: 60% are a fade, 25% are a zoom-in (`xfade=zoomin`), 15% are a slide (`slideleft` / `slideup` / `slideright` rotating). All transitions are 0.15 s — subtle, not flashy. Hard cut between sections (the topic change is its own visual punctuation).
- **Each cut uses a different Pexels clip**, deduped across the whole reel — no two cuts share a video ID. If Pexels has fewer unique clips than needed for a query, the pipeline reuses with adjacency relaxed (never two same clips in a row) and logs `[footage] WARN`.
- **Section queries rotate.** Each section in `script.json` has a `queries` list (2–3 entries); sub-segment N within a section searches `queries[N % len]`. Three queries × three sub-segments = three visually different shots per section.

A typical 35-second reel ends up with **~13–15 clip cuts**, with ~3 of them in the first 5 seconds.

## Caption + outro style

All on-screen text uses a single color (default **green `#00FF66`**, matches the health/wellness niche). Override with `--text-color "#RRGGBB"`.

**Body captions** (word-by-word):
- Bold green, one word visible at a time, synced to whisper timestamps.
- Centered horizontally, vertical position ~65 % of the frame.
- Real Gaussian-blurred drop shadow (two-layer ASS trick — libass doesn't support a single-property blurred shadow).
- Pop-in scale animation (80→100% over 80 ms).

**Outro** (overlaid on extended CTA footage — no separate solid card):
- The CTA video is extended by 2.5 s past the voiceover end.
- During that 2.5 s, a stepped-gradient bottom darken (drawbox bands at increasing alpha) appears for readability.
- Two-line outro text appears in the lower-third with a 300 ms fade-in, same bold green color, ~140 px.
- Default text: `LIKE AND FOLLOW` / `FOR MORE`.

```bash
python reel.py --script script.json                                  # default
python reel.py --script script.json --no-outro                       # skip outro
python reel.py --script script.json --outro-text "SAVE THIS|FOR LATER"
python reel.py --script script.json --text-color "#FF3366"           # pink/red text everywhere
```

The voiceover audio is automatically padded with 2.5 s of silence when the outro is included.

**Changing the font:** default is `Arial Black` (always on macOS). To use Montserrat Black or Anton, install the font system-wide and edit the `fontname` default in `pipeline/captions.py`.

## Background music

Drop royalty-free MP3 or WAV files into [`bg-music/`](bg-music/) and the pipeline picks one at random per render, loops it to cover the full reel, mixes it under the voiceover at ~-22 dB, and fades it out over the last 1.5 s.

If `bg-music/` is empty, music is skipped silently — no error. Override with `--music PATH` or skip explicitly with `--no-music`.

### Where to source free music

- **Pixabay Music** — https://pixabay.com/music/ — CC0, no attribution required, large catalogue.
- **YouTube Audio Library** — https://www.youtube.com/audiolibrary — royalty-free, varied genres.
- **Uppbeat free tier** — https://uppbeat.io/ — free with attribution, curated.
- **Free Music Archive** — https://freemusicarchive.org/ — Creative Commons.

Verify the license fits your use case (some require attribution in the post caption).

## Project layout

```
reel.py                          # CLI entry, orchestrates the 5 render stages
pipeline/
  script.py                      # Load + validate the script JSON
  tts.py                         # Kokoro TTS         → voice.wav (24kHz → 16kHz mono)
  transcribe.py                  # voice.wav          → faster-whisper → word timestamps
  footage.py                     # Plan cuts + parallel Pexels download + video_id cache
  captions.py                    # word timestamps    → captions.ass (yellow body, green outro)
  assemble.py                    # ffmpeg: process_clip, xfade chain, concat, mux, burn
prompts/
  script-generation.md           # Reusable LLM prompt for Step A
bg-music/                        # Drop royalty-free MP3s/WAVs here
requirements.txt
docs/superpowers/specs/          # design doc
```

Each run creates `work/<timestamp>/` for intermediates (`script.json`, `voice.wav`,
`words.json`, `captions.ass`, per-segment MP4s). The Pexels clip cache lives at
`work/.clip_cache/{video_id}.mp4` and **persists across runs** so re-rendering the
same script skips the network.

## Output spec

- 1080×1920 MP4 (H.264, CRF 23, `-preset medium`, yuv420p), AAC audio (192 k), `+faststart` for streaming.
- 30–45 s of voiceover + 2.5 s outro card (unless `--no-outro`).
- ~12–14 clip cuts in a typical reel for high visual energy.
- Ready to upload directly to Facebook Reels with no further editing.

## Troubleshooting

- **`--script is required`** — see [Step A](#step-a--generate-a-script).
- **`invalid script (...)`** — JSON is missing a field or has the wrong shape. The error message points at the exact problem.
- **`PEXELS_API_KEY not set`** — fill `.env`.
- **Pexels `0 results`** — query in your script is too obscure. Edit `script.json` to broaden the `search_query`.
- **`[footage] WARN: limited Pexels variety`** — Pexels returned fewer unique videos than needed for that query. The reel still renders but reuses clips (never adjacent). Edit the query in `script.json` for more variety.
- **`Filter not found` / caption text missing** — your ffmpeg lacks libass; install `ffmpeg-full` (see [Setup](#setup)).
- **First Kokoro run is slow** — downloading ~330 MB Kokoro model + ~12 MB spaCy English model. Cached afterwards.
- **Kokoro warns "PyTorch >= 2.4 is required"** — pin `transformers<5.0` in `requirements.txt` (already done). Intel macOS is stuck on torch 2.2 because no newer x86 wheel exists.
