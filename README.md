# Faceless Reel Pipeline

Render vertical 1080×1920 short-form video from a JSON script — ready to upload
to Facebook Reels, Instagram Reels, TikTok, or YouTube Shorts (they all share
the 9:16 / 1080×1920 spec). The pipeline makes **no LLM API calls** — you
generate the script separately (in Claude Code, ChatGPT, locally, or by hand)
and pass it in via `--script`.

## Table of contents

- [What it does](#what-it-does)
- [Setup](#setup)
- [Workflow](#workflow)
- [Voice (brand-locked)](#voice-brand-locked)
- [The 3-second rule](#the-3-second-rule-and-the-hook-gets-it-harder)
- [Caption style](#caption-style)
- [Background music](#background-music)
- [Project layout](#project-layout)
- [Output spec](#output-spec)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

```bash
# Step A: generate a script (one time, per topic)
#   → copy prompts/script-generation.md into Claude Code
#   → append your topic, save the output JSON to contents/sample_<topic>.json

# Step B: render the reel — bare topic names resolve against contents/
python3 reel.py --script sore_throat
# → out/sore_throat/final.mp4 (30–45 s voiceover, ready for Facebook Reels)

# Or list everything currently in contents/
python3 reel.py --list
```

## What it does

1. **Script** — *(you provide)* a JSON file with hook + 3 tips + CTA. Each section has a `queries` list of 2–3 Pexels search terms; the renderer rotates through them as it cuts.
2. **Voiceover** — **ElevenLabs API** (`eleven_multilingual_v2` model). Default voice `bill` (authoritative, deep narrator); per-segment synthesis so punctuation drives intonation. Override with `--voice <name|voice_id>` ([catalog](#voice-brand-locked)).
3. **Word timestamps** — `faster-whisper` (`base` model, CPU) produces per-word timing.
4. **Hook + body with the 3-second rule** — the hook is cut into 1.5–2 s shots with a Ken Burns 1.0 → 1.08 zoom (highest-retention real estate in a Reel). Body sections cut into 2.5–3 s shots. Within each section, transitions vary: 60% fade / 25% zoom-in / 15% slide (deterministic by cut index, so re-renders match). Hard cuts between sections.
5. **Captions** — karaoke style. Phrases (~5–7 words) appear in white; each word flips to the brand color (default green `#00FF66`) when it's spoken and stays highlighted. Gaussian-blurred drop shadow + 2 px outline. See [Caption style](#caption-style).
6. **Background music** — auto-picked at random from [`bg-music/`](#background-music), looped, mixed at ~-22 dB, faded out over the last 1.5 s.
7. **Outro / follow-call** — there's no separate outro segment any more. The follow-call (e.g. `"...and follow for more wake-up tips that actually work."`) is woven into the CTA text by the script generator, so the voice doesn't seam at the very end of the reel and the body captions sync the closing words naturally.
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

# 4. Configure environment
cp .env.example .env
# Then edit .env:
#   PEXELS_API_KEY=...        (https://www.pexels.com/api/)
#   ELEVENLABS_API_KEY=...    (https://elevenlabs.io/app/settings/api-keys)
#   FFMPEG_BIN=/usr/local/opt/ffmpeg-full/bin/ffmpeg     (only if not on PATH)
#   FFPROBE_BIN=/usr/local/opt/ffmpeg-full/bin/ffprobe   (only if not on PATH)
```

**ElevenLabs free tier** = 10,000 characters/month, enough for roughly 25–30
reels (~350 spoken characters each). The pipeline prints a credit usage
summary after every render and warns interactively if a single reel would
exceed the remaining balance.

## Workflow

### Step A — Generate a script

Open [`prompts/script-generation.md`](prompts/script-generation.md), copy the prompt block into Claude Code (claude.ai/code) or any LLM, replace the `<YOUR TOPIC HERE>` placeholder with your topic, and save the resulting JSON as **`contents/sample_<topic>.json`** (e.g. `contents/sample_sore_throat.json`). All reel scripts live in [`contents/`](contents/) — see [`contents/README.md`](contents/README.md) for the conventions.

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

`--script` accepts a topic name, filename, or full path — all of these resolve identically:

```bash
.venv/bin/python reel.py --script sore_throat
.venv/bin/python reel.py --script sample_sore_throat
.venv/bin/python reel.py --script sample_sore_throat.json
.venv/bin/python reel.py --script contents/sample_sore_throat.json
```

Outputs land at **`out/<topic>/final.mp4`** so renders don't overwrite each other.

```bash
# Full render with defaults (auto-picks music from bg-music/)
.venv/bin/python reel.py --script sore_throat

# List all available script topics in contents/
.venv/bin/python reel.py --list

# Cheap topic verification (validate schema + Pexels search, no TTS/whisper/render)
.venv/bin/python reel.py --script sore_throat --dry-run

# Specific music file (overrides bg-music/ auto-pick)
.venv/bin/python reel.py --script sore_throat --music ./my-track.mp3

# Skip background music
.venv/bin/python reel.py --script sore_throat --no-music

# Custom voice + text color
.venv/bin/python reel.py --script sore_throat \
    --voice callum \
    --text-color "#FF3366"

# Override the output path
.venv/bin/python reel.py --script sore_throat --out out/custom.mp4
```

### Flags

| Flag                    | Default                       | Description                                                          |
| ----------------------- | ----------------------------- | -------------------------------------------------------------------- |
| `--script NAME\|PATH`   | *(required)*                  | Topic name, filename, or path. Bare names resolve against `contents/` (e.g. `sore_throat` → `contents/sample_sore_throat.json`). |
| `--list`                | off                           | Print all available topics in `contents/` and exit.                  |
| `--out PATH`            | `out/<topic>/final.mp4`       | Output MP4 path. Default derives `<topic>` from the script filename. |
| `--voice NAME\|ID`      | `bill`                        | ElevenLabs voice name (case-insensitive) or raw voice_id ([catalog](#voice-brand-locked)). |
| `--music PATH`          | auto from `bg-music/`         | Background music file. Mixed at ~-22 dB, looped, faded out at end.   |
| `--no-music`            | off                           | Skip music even if files exist in `bg-music/`.                       |
| `--text-color HEX`      | `#00FF66`                     | Color for all body word-by-word captions.                            |
| `--dry-run`             | off                           | Validate script + Pexels search + cut plan only. No render.          |
| `--keep-work`           | off                           | Keep `work/<ts>/` after success.                                     |

## Voice (brand-locked)

The default voice is **`bill`** — an authoritative, deep ElevenLabs narrator
that lands well for health/wellness authority content. The brand voice is
intentionally consistent across every reel for audience recognition.
Override only when A/B-testing.

| Friendly name      | Voice ID                       | Tier      | Notes                             |
| ------------------ | ------------------------------ | --------- | --------------------------------- |
| `bill` *(default)* | `pqHfZKP75CvOlQylNhV4`         | Free      | Authoritative, deep               |
| `liam`             | `TX3LPaxmHKxFdv7VOQHJ`         | Free      | Expressive American male          |
| `charlie`          | `IKne3meq5aSn9XLyUdCD`         | Free      | Casual Australian male            |
| `callum`           | `N2lVS1w4EtoT3dr4eOWO`         | Free      | Intense, dramatic                 |
| `brian`            | `nPczCjzI2devNBz1zQrb`         | Free      | Warm, mature                      |
| `adam`             | `pNInz6obpgDQGcFmaJgB`         | Free      | Classic narrator                  |
| `josh`             | `TxGEqnHWrfWFTfGW9XjX`         | **Paid**  | Deep, mature narrator (library voice — requires paid plan) |
| `sam`              | `yoZ06aMxZJJ28mfd3POQ`         | **Paid**  | Raspy, real-sounding (library voice — requires paid plan) |

Names are case-insensitive — `--voice Bill`, `--voice bill`, and
`--voice BILL` all resolve identically. You can also pass a raw `voice_id` for
any ElevenLabs voice in your account. **Heads-up:** the ElevenLabs free tier
blocks "library voices" via the API (returns `402 paid_plan_required`). The
six entries marked "Free" above are premade voices and work on every tier.

```bash
# Default (bill)
python reel.py --script script.json

# Switch voice by friendly name
python reel.py --script script.json --voice callum

# Or by raw voice_id
python reel.py --script script.json --voice ErXwobaYiN019PkySvjV
```

Voice and pacing knobs live in [`pipeline/tts.py`](pipeline/tts.py):

```python
# pipeline/tts.py
DEFAULT_VOICE = "bill"
DEFAULT_MODEL = "eleven_multilingual_v2"   # better emotional range than turbo
VOICE_SETTINGS = VoiceSettings(
    stability=0.35,        # lower = more emotional variation
    similarity_boost=0.80, # keep voice identity stable
    style=0.55,            # higher = more dramatic narrator energy
    use_speaker_boost=True,
)
```

**Model trade-off.** `eleven_multilingual_v2` costs ~2× the credits per
character vs `eleven_turbo_v2_5`. At our ~350 chars/reel you still get
~12–15 reels per month on the free tier. If you want to maximize quantity
over quality, swap `DEFAULT_MODEL` back to turbo.

Snappy Reels timings: `.` 200 ms · `?/!` 250 ms · `...` 400 ms · `—` 200 ms.
Section gaps tapered: hook→tip1 250 ms, tip→tip 150 ms, tip3→cta 300 ms.

**Credit usage.** The pipeline prints a credit balance check before every
render and a "used by this reel" summary after. If your estimated character
count exceeds the remaining free-tier balance, you get a `[tts] WARNING` and
an interactive `Continue anyway? (y/N)` prompt.

## The 3-second rule (and the hook gets it harder)

Reels retention drops sharply when a single visual stays on screen for more than ~3 s. The pipeline enforces this aggressively:

- **Hook section (first 3-5 s of the reel) gets 1.5–2 s cuts** — viewers decide whether to keep watching in the first few seconds, so the visuals need to refresh constantly. Hook clips also get a subtle **Ken Burns zoom** (1.0 → 1.08 over the clip duration) so even within a single 2 s shot there's continuous motion.
- **Body sections get 2.5–3 s cuts.**
- **Transitions within a section vary by cut index**, deterministically: 60% are a fade, 25% are a zoom-in (`xfade=zoomin`), 15% are a slide (`slideleft` / `slideup` / `slideright` rotating). All transitions are 0.15 s — subtle, not flashy. Hard cut between sections (the topic change is its own visual punctuation).
- **Each cut uses a different Pexels clip**, deduped across the whole reel — no two cuts share a video ID. If Pexels has fewer unique clips than needed for a query, the pipeline reuses with adjacency relaxed (never two same clips in a row) and logs `[footage] WARN`.
- **Section queries rotate.** Each section in `script.json` has a `queries` list (2–3 entries); sub-segment N within a section searches `queries[N % len]`. Three queries × three sub-segments = three visually different shots per section.

A typical 35-second reel ends up with **~13–15 clip cuts**, with ~3 of them in the first 5 seconds.

## Caption style

All on-screen text uses a single color (default **green `#00FF66`**, matches the health/wellness niche). Override with `--text-color "#RRGGBB"`.

**Body captions** (karaoke / progressive highlight):
- Each phrase (~5–7 words) appears on screen as a single block in **white** with a 2 px black outline.
- As the voice speaks each word, that word flips to the brand color (default green `#00FF66`) and **stays** highlighted until the phrase ends.
- When the phrase ends, the line clears and the next phrase appears in white again.
- Centered horizontally, vertical position ~65 % of the frame.
- Real Gaussian-blurred drop shadow (two-layer ASS trick — libass doesn't support a single-property blurred shadow).

**How it works under the hood:**

Phrase grouping in [`pipeline/captions.py`](pipeline/captions.py) `group_words_into_phrases()` uses whisper word timestamps and breaks on (priority order):

1. Any word ending with `.` `?` `!`  (always — sentence terminator)
2. Reaching `KARAOKE_MAX_WORDS_PER_PHRASE` (7 by default)
3. Word ending with `,` once `KARAOKE_MIN_WORDS_FOR_WEAK_BREAK` (3) is reached
4. Speaker pause ≥ `KARAOKE_BIG_GAP_S` (0.50 s) once min-words is reached

Each phrase emits a shadow + main Dialogue pair with libass karaoke (`\k`) tags driving the per-word color flip. PrimaryColour = brand color (highlighted), SecondaryColour = white (unspoken).

**Inspect the style in isolation:**

```bash
.venv/bin/python scripts/karaoke_test.py
# → debug/karaoke_test.mp4  — one sentence on a dark background
```

**Outro / follow-call** lives inside the CTA text. There's no separate
overlay segment, no auto-appended `"Like and follow for more"` boilerplate —
the script generator weaves a follow-call into the CTA naturally so the voice
flows from the last tip straight through the closing sentence without a seam.

Example CTAs from the prompt:

- `"Save this for tomorrow morning, and follow for more wake-up tips that actually work."`
- `"Try this tonight, and follow for more natural remedies that actually work."`
- `"Pick just one and start today, then follow for more daily gut health hacks."`

```bash
python reel.py --script script.json                                  # default
python reel.py --script script.json --text-color "#FF3366"           # pink/red captions
```

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit-message conventions (conventional-commit-style prefixes).

## Project layout

```
reel.py                          # CLI entry, orchestrates the 5 render stages
pipeline/
  script.py                      # Load + validate the script JSON
  tts.py                         # ElevenLabs API     → per-segment MP3 → 16kHz mono voice.wav
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
- 30–45 s of voiceover (CTA includes the follow-call — no separate outro segment).
- ~12–14 clip cuts in a typical reel for high visual energy.
- Ready to upload directly to Facebook Reels with no further editing.

## Troubleshooting

- **`--script is required`** — see [Step A](#step-a--generate-a-script).
- **`invalid script (...)`** — JSON is missing a field or has the wrong shape. The error message points at the exact problem.
- **`PEXELS_API_KEY not set`** — fill `.env`.
- **Pexels `0 results`** — query in your script is too obscure. Edit `script.json` to broaden the `search_query`.
- **`[footage] WARN: limited Pexels variety`** — Pexels returned fewer unique videos than needed for that query. The reel still renders but reuses clips (never adjacent). Edit the query in `script.json` for more variety.
- **`Filter not found` / caption text missing** — your ffmpeg lacks libass; install `ffmpeg-full` (see [Setup](#setup)).
- **`ELEVENLABS_API_KEY not set`** — fill `.env`. Free key at https://elevenlabs.io/app/settings/api-keys.
- **`Aborted (insufficient credits...)`** — your free-tier balance is below the reel's estimated character count. Wait for the monthly reset or upgrade.
