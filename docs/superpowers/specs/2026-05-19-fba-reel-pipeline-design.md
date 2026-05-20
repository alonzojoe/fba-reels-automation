# Faceless Health/Home-Remedies Reel Pipeline — Design

**Date:** 2026-05-19
**Status:** Approved (revised — file-based script input)

## Goal

A two-step workflow that turns a topic into a Facebook-Reels-ready vertical MP4
without any paid LLM API call on the rendering side:

```bash
# Step A — generate a script in Claude Code (or any LLM), save to script.json
# Step B — render
python reel.py --script script.json
# → out/final.mp4  (1080×1920, 30–45s VO + 2.5s outro)
```

The user has Claude Max (chat subscription) but no Anthropic API credits, so the
pipeline must not call the Messages API. The script-generation step is delegated
to an LLM-of-choice via a reusable prompt at `prompts/script-generation.md`.

## Architecture

```
fba-pipeline/
├── reel.py                  # CLI entry, orchestrates the 6 stages
├── pipeline/
│   ├── __init__.py
│   ├── script.py            # topic       → Claude              → script.json
│   ├── tts.py               # script.json → edge-tts            → voice.wav
│   ├── transcribe.py        # voice.wav   → faster-whisper      → word_timestamps.json
│   ├── footage.py           # script.json → Pexels              → clips/*.mp4
│   ├── captions.py          # word_timestamps → ASS subtitle file
│   └── assemble.py          # everything → ffmpeg               → final.mp4
├── requirements.txt
├── README.md
├── .env.example
├── .env                     # gitignored
└── .gitignore
```

Each run gets a working directory `work/<timestamp>/` for intermediates so any stage can be inspected or re-run in isolation. Final output lands in `out/final.mp4` (override with `--out`).

## Pipeline stages

### 1. `pipeline/script.py` — script.json → validated dict

- **No LLM call.** Reads the user-provided JSON and validates it against the schema.
- Schema:
  ```json
  {
    "hook":  {"text": "...", "search_query": "..."},
    "tips":  [
      {"text": "...", "search_query": "..."},
      {"text": "...", "search_query": "..."},
      {"text": "...", "search_query": "..."}
    ],
    "cta":   {"text": "...", "search_query": "..."}
  }
  ```
- Validation: top-level keys present; `hook`/`cta` are objects with non-empty `text` and `search_query`; `tips` is a list of exactly 3 entries with the same per-section shape. Any failure → `SystemExit` with a precise pointer to the failing field.
- Copies the validated JSON into `work/<ts>/script.json` for the run record.

Script *generation* itself lives outside the pipeline at `prompts/script-generation.md` — a reusable Markdown prompt with the schema, rules (30–45s spoken length, no medical-claim language, Pexels-friendly search queries), and two worked examples. The user pastes it into Claude Code (or any LLM), appends their topic, and saves the JSON output. Same content as the inline system prompt the earlier design used, but generation happens via chat instead of the Messages API — so the pipeline doesn't need Anthropic API credits.

### 2. `pipeline/tts.py` — script → voice.wav

- Uses `edge-tts` (free, no key, MS Edge speech endpoint).
- Voice: `en-US-AriaNeural` default, override with `--voice`.
- Synthesizes each section text separately, then concatenates with small inter-section silences (~150 ms) so whisper can still distinguish sections by silence gaps.
- Output: MP3 from edge-tts → convert to 16 kHz mono WAV via ffmpeg (whisper input format).
- Records each section's start time in `sections.json` (cumulative duration after each section's audio finishes).

### 3. `pipeline/transcribe.py` — voice.wav → word_timestamps.json

- Uses `faster-whisper` (CTranslate2 reimplementation), model `base`, device `cpu`, compute_type `int8`.
- `word_timestamps=True` produces per-word `(start, end, word)` from segments.
- Outputs flat list:
  ```json
  [{"start": 0.12, "end": 0.34, "word": "Turmeric"}, ...]
  ```
- If word count is 0, fail loud (means TTS produced silence).

### 4. `pipeline/footage.py` — script queries → clips/*.mp4

- For each of the 5 sections, GET `https://api.pexels.com/videos/search`:
  - `query=<section.search_query>`
  - `orientation=portrait`
  - `per_page=10`
- Pick the first result whose `duration` ≥ section duration (from `sections.json`). If none qualify, pick the longest.
- Download the `link` from the highest-resolution `video_files` entry where `height >= width` (portrait).
- Cache by SHA1 of the query string (`clips/<sha1>.mp4`) so re-runs don't re-download.
- If a query returns 0 hits, retry with the first two words of the query; if still empty, fail with the query in the error message.

### 5. `pipeline/captions.py` — word timestamps → captions.ass

- Emits an ASS subtitle file with **one word visible at a time** (no 3-word window — classic reel style).
- **Style** (TikTok/Reels caption look):
  - Bold yellow `#FFFF00` (ASS `&H0000FFFF`), font size ~95px
  - Font: `Arial Black` (always present on macOS). Swap to `Montserrat Black` or `Anton` by installing the font and editing the `Fontname` field in the ASS style row.
  - 1px black outline on the main text (libass `Outline=1`, `OutlineColour=black`).
  - Real Gaussian-blurred drop shadow via **two-layer trick**: for every word event, emit *two* Dialogue lines:
    - **Layer 0 (shadow):** `{\blur6\1c&H000000&\3c&H000000&\bord0\pos(544,1252)}` — black text, Gaussian blur σ=6, offset 4px down-right from the main text position.
    - **Layer 1 (main):** `{\pos(540,1248)\fscx80\fscy80\t(0,80,\fscx100\fscy100)}` — yellow text at the intended position, with a 80→100% scale transform over 80 ms ("pop-in" animation).
  - Center alignment (`\an5`), vertical position at **65% of frame height** (`y=1248` on a 1920-tall canvas).
- **Timing:** each pair of events starts at the current word's `start` and ends at the *next* word's `start` (so captions swap with no gap). The last word's events end at its own `end + 0.3s`.
- ASS doesn't natively support a Gaussian-blurred shadow as a single property — `\shad` is hard-edged. The two-layer trick is the standard libass workaround. File size grows ~2× but render quality is identical to a Photoshop-style blurred drop shadow.

### 5b. Outro card (extends captions.ass)

After the CTA voiceover ends, append a **2.5-second outro segment**:

- **Video segment:** solid `#111111` (1080×1920, 2.5 s, 30 fps) generated via `ffmpeg -f lavfi -i color=c=0x111111:s=1080x1920:d=2.5:r=30`. Appended to the concat list after the 5 body segments.
- **Text:** two-line message (default `"LIKE AND FOLLOW"` / `"FOR MORE"`), centered, larger font (~140 px), same bold yellow + blurred-shadow style as captions.
- **Animation:** `\fad(300,0)` — fade in over 300 ms, no fade out.
- Emitted as two more Dialogue events (shadow + main) in `captions.ass`, timed `[total_voice_duration, total_voice_duration + 2.5]`.

CLI flags:
- `--no-outro` — skip the outro segment entirely (video stops at the CTA).
- `--outro-text "LINE1|LINE2"` — override the text. `|` is the line separator.

When the outro is included, the voiceover WAV is padded with 2.5 s of silence via `apad=pad_dur=2.5` so the final audio track matches the video duration.
- Output: `captions.ass` in the work dir.

### 6. `pipeline/assemble.py` — final.mp4

For each section i:

1. **Aspect check**: probe the downloaded clip with `ffprobe`. Target aspect 9:16 ≈ 0.5625. Tolerance: `0.50 ≤ width/height ≤ 0.65` counts as "portrait enough" for crop-only.
2. **Crop-only path** (clip is portrait-enough):
   ```
   scale=1080:1920:force_original_aspect_ratio=increase,
   crop=1080:1920,
   trim=duration=<section_duration>,
   setpts=PTS-STARTPTS
   ```
3. **Blurred-background fallback** (clip not portrait-enough, e.g. landscape):
   ```
   [0:v]split=2[bg][fg];
   [bg]scale=1080:1920:force_original_aspect_ratio=increase,
        crop=1080:1920,
        gblur=sigma=30[bgblur];
   [fg]scale=1080:-2[fgscale];
   [bgblur][fgscale]overlay=(W-w)/2:(H-h)/2,
        trim=duration=<section_duration>,
        setpts=PTS-STARTPTS
   ```
   Foreground keeps its original aspect ratio centered; top/bottom filled with a heavily blurred copy of the same frame. Standard vertical-from-landscape technique.

Then:

4. Concat the 5 segments (concat demuxer with a manifest file, since filters differ per segment).
5. Audio:
   - Voiceover input: `voice.wav` at full volume.
   - If `--music PATH`: mix in via `amix=inputs=2:duration=first:weights=1 0.1`. (Weight `0.1` ≈ −20 dB on the music track relative to voice; verify empirically with `ffmpeg -filter_complex volumedetect` if it sounds off.)
   - If no music: voiceover only.
6. Burn captions: `subtitles=captions.ass:fontsdir=...` filter applied to the concatenated video.
7. Encode: `-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart`.
8. Output: `out/final.mp4` (or `--out`).

## CLI surface

```
python reel.py --script script.json [options]

Required:
  --script PATH            Path to the script JSON file. If absent, the CLI
                           prints the two-step workflow help and exits 1.

Options:
  --out PATH               Output file (default: out/final.mp4)
  --voice NAME             edge-tts voice (default: en-US-AriaNeural)
  --music PATH             Background music file; mixed at ~-20dB. Omit for no music.
  --no-outro               Skip the 2.5s outro card (default: outro included).
  --outro-text "L1|L2"     Override outro text. "|" is the line separator.
                           Default: "LIKE AND FOLLOW|FOR MORE".
  --dry-run                Validate script + Pexels search only. Skip TTS,
                           transcription, downloads, and render. Prints the script
                           and the chosen Pexels video URL/ID per section.
  --keep-work              Don't delete the work/<ts>/ dir after successful render.
```

### `--dry-run` behavior

Runs stages 1 and a *search-only* variant of stage 4:

1. Load and validate the script JSON (no LLM call).
2. For each section: hit Pexels search, parse the first result, but **do not download**.
3. Print:
   - The full script (hook + 3 tips + CTA), each with word count and estimated duration (140 wpm).
   - Per section: query, Pexels video ID, page URL, duration, dimensions.
4. Exit 0.

No TTS, no whisper, no ffmpeg, no disk writes beyond `script.json` (copied verbatim) and a `dry_run_report.json` in the work dir.

## Dependencies

`requirements.txt`:

```
edge-tts>=6.1.0
faster-whisper>=1.0.0
requests>=2.31.0
python-dotenv>=1.0.0
```

System dependencies (documented in README):
- `ffmpeg` (must be on PATH; both `ffmpeg` and `ffprobe`)
- Python 3.12 (faster-whisper's transitive `onnxruntime` dep lacks a 3.14 wheel as of this writing)

Explicitly **not** depending on: `anthropic` (no LLM API call from the pipeline), `moviepy` (too heavy, ffmpeg shells work fine), `openai-whisper` (slower; faster-whisper covers it), `torch` (faster-whisper uses CTranslate2 wheels).

## Configuration

`.env` loaded with `python-dotenv` at startup:

- `PEXELS_API_KEY` — required for footage search

Validated at startup, before any expensive work. Missing → friendly error pointing at `.env.example`.

## Error handling

Only at boundaries — internal stages trust each other:

| Boundary | Failure | Behavior |
|---|---|---|
| Startup | `--script` not provided | Print the two-step workflow help, exit 1 |
| Startup | Missing `PEXELS_API_KEY` | Exit 1 with "Set PEXELS_API_KEY in .env" |
| Script load | File missing | Exit 1 with the path |
| Script load | JSON parse failure | Exit 1 with `json.JSONDecodeError` location |
| Script load | Schema mismatch | Exit 1 with the failing field path |
| Pexels | 0 hits for query | Retry with first 2 words; still 0 → exit 1 with failing query |
| Pexels | HTTP error | Exit 1 with status + body |
| edge-tts | Network failure | Exit 1 with underlying error |
| Whisper | 0 words detected | Exit 1 (means TTS broke) |
| ffmpeg | Nonzero exit | Surface stderr, exit 1 |

No silent fallbacks, no swallowed exceptions. The pipeline either produces a valid MP4 or fails with a clear pointer to the broken stage.

## Testing strategy

Skipped for the first cut — the pipeline is mostly thin wrappers over external services where the failure modes are obvious (HTTP errors, missing files, ffmpeg errors). Each stage is runnable standalone:

```
python -m pipeline.footage <script.json>
# etc.
```

That's the manual test surface. Once the pipeline has been used a dozen times and the flaky spots are known, we'll add targeted tests there.

## Out of scope (for first cut)

- Multiple voices / character voiceovers
- AI-generated B-roll (Veo, Sora, etc.)
- Multi-language output
- Custom font selection (uses ffmpeg's default font search, README will note how to bundle a font if needed)
- Automatic upload to Facebook (we stop at the rendered file)
- Topic queueing / batch mode (one topic per invocation)
- Resume from a previous failed run (re-run is fast enough; `--keep-work` is the escape hatch for debugging)
