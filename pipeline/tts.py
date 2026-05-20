"""Voiceover synthesis via the ElevenLabs API.

Replaces the previous Kokoro engine. Each sentence is sent to ElevenLabs as
its own `text_to_speech.convert` call (returning MP3 bytes), saved to disk,
then stitched together with silence MP3s between segments and between sections.
The combined MP3 is finally converted to a 16 kHz mono WAV for faster-whisper.

Key features:
- Eight narrator voices selectable by friendly name (`liam`, `josh`, `charlie`,
  `callum`, `sam`, `brian`, `bill`, `adam`) or raw `voice_id` via the
  `--voice` CLI flag. Default: **Liam** — expressive American male.
- Model `eleven_multilingual_v2` — noticeably better emotional range and
  inflection than the cheaper turbo model. ~2× credit cost per character; at
  ~350 chars per reel that still leaves 12-15 reels on the 10K-char free tier.
- Same text preprocessing as before: bracket-tag stripping, abbreviation
  expansion (`5 mg` → "five milligrams"), integer-to-words (0–100), and
  optional per-section `pronunciation_hints` map.
- Same punctuation-driven prosody: each `.`/`?`/`!`/`...`/`—` segment is its
  own API call so punctuation actually drives intonation.
- Snappy Reels-tuned silences: `.` 200 ms, `?`/`!` 250 ms, `...` 400 ms,
  em-dash 200 ms. Section gaps tapered: hook→tip1 250 ms, tip→tip 150 ms,
  tip3→cta 300 ms.
- Speed/pacing is owned by ElevenLabs (controlled via `voice_settings.stability`
  and the model itself) — no `speed` multiplier any more.
- Pre-flight credit check + post-render credit usage via the ElevenLabs
  `user.get()` endpoint. Warns + prompts for confirmation if a single reel
  is estimated to exceed the remaining free-tier balance.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import num2words
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs


# ---------- Voice catalog ----------

# Friendly name (lowercase) → ElevenLabs voice_id. All free-tier-accessible.
# Names are matched case-insensitively in `resolve_voice`.
VOICES: dict[str, str] = {
    "liam":    "TX3LPaxmHKxFdv7VOQHJ",  # expressive American male — DEFAULT
    "josh":    "TxGEqnHWrfWFTfGW9XjX",  # deep, mature narrator
    "charlie": "IKne3meq5aSn9XLyUdCD",  # casual Australian male
    "callum":  "N2lVS1w4EtoT3dr4eOWO",  # intense, dramatic
    "sam":     "yoZ06aMxZJJ28mfd3POQ",  # raspy, real-sounding
    "brian":   "nPczCjzI2devNBz1zQrb",  # warm, mature
    "bill":    "pqHfZKP75CvOlQylNhV4",  # authoritative, deep
    "adam":    "pNInz6obpgDQGcFmaJgB",  # classic narrator
}
DEFAULT_VOICE: str = "liam"
DEFAULT_MODEL: str = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT: str = "mp3_44100_128"

# Expressive VoiceSettings tuned for narrator energy.
#   stability=0.35       — lower = more emotional variation per sentence
#   similarity_boost=0.80 — keep voice consistent across segments
#   style=0.55           — much higher = dramatic narrator energy
#   use_speaker_boost    — clarity over mic-presence
VOICE_SETTINGS = VoiceSettings(
    stability=0.35,
    similarity_boost=0.80,
    style=0.55,
    use_speaker_boost=True,
)


# ---------- Snappy Reels timings ----------

INTER_SECTION_SILENCES_S = [
    0.25,  # after hook → before tip1
    0.15,  # after tip1 → before tip2
    0.15,  # after tip2 → before tip3
    0.30,  # after tip3 → before CTA
]
PAUSE_BY_TERMINATOR_S: dict[str, float] = {
    ".":   0.20,
    "?":   0.25,
    "!":   0.25,
    "...": 0.40,
    "—":   0.20,
}
DEFAULT_PAUSE_S = 0.20

WHISPER_SAMPLE_RATE = 16000  # final WAV format for faster-whisper

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")


# ---------- Regex + abbreviation table ----------

_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]\s*")
_TERMINATOR_RE = re.compile(r"(\.{2,}|[.!?—])")
_NUMBER_RE = re.compile(r"\b\d+\b")
_ABBREVIATIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bDr\.\s+"), "Doctor "),
    (re.compile(r"\bMr\.\s+"), "Mister "),
    (re.compile(r"\bMrs\.\s+"), "Misses "),
    (re.compile(r"\bMs\.\s+"), "Miss "),
    (re.compile(r"(\d)\s*mg\b", re.IGNORECASE), r"\1 milligrams"),
    (re.compile(r"(\d)\s*ml\b", re.IGNORECASE), r"\1 milliliters"),
    (re.compile(r"(\d)\s*lb\b", re.IGNORECASE), r"\1 pounds"),
    (re.compile(r"(\d)\s*oz\b", re.IGNORECASE), r"\1 ounces"),
    (re.compile(r"%"), " percent"),
    (re.compile(r"\s+&\s+"), " and "),
]


# ---------- Client + credits ----------

_client: ElevenLabs | None = None
_silence_cache: dict[int, Path] = {}  # ms → path (per work_dir)


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        key = os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise SystemExit(
                "ERROR: ELEVENLABS_API_KEY not set.\n"
                "  Get a free key at https://elevenlabs.io/app/settings/api-keys\n"
                "  Then add to .env:  ELEVENLABS_API_KEY=your-key-here"
            )
        _client = ElevenLabs(api_key=key)
    return _client


def resolve_voice(voice: str) -> str:
    """Accept either a friendly name (case-insensitive) or a raw voice_id."""
    return VOICES.get(voice.lower(), voice)


_credit_warning_printed = False


def get_credit_balance() -> tuple[int | None, int | None]:
    """Return (used, limit) from the ElevenLabs subscription endpoint.

    Best-effort: requires the `user_read` permission on the API key. If the
    key lacks it (or any other error), we print ONE concise warning and
    keep returning (None, None) on subsequent calls without spamming.
    """
    global _credit_warning_printed
    try:
        info = _get_client().user.get()
        sub = getattr(info, "subscription", None)
        if sub is None:
            return None, None
        used = getattr(sub, "character_count", None)
        limit = getattr(sub, "character_limit", None)
        return used, limit
    except Exception as e:
        if not _credit_warning_printed:
            msg = str(e)
            if "missing_permissions" in msg or "user_read" in msg:
                print(
                    "[tts] (credit balance unavailable — API key lacks the "
                    "`user_read` permission; enable it at "
                    "https://elevenlabs.io/app/settings/api-keys to see "
                    "usage)",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[tts] (credit balance unavailable: "
                    f"{type(e).__name__})",
                    file=sys.stderr,
                )
            _credit_warning_printed = True
        return None, None


# ---------- Text preprocessing ----------

def _expand_abbreviations(text: str) -> str:
    for pat, repl in _ABBREVIATIONS:
        text = pat.sub(repl, text)
    return text


def _expand_numbers(text: str) -> str:
    def repl(m: re.Match) -> str:
        try:
            n = int(m.group())
        except ValueError:
            return m.group()
        if 0 <= n <= 100:
            return num2words.num2words(n)
        return m.group()
    return _NUMBER_RE.sub(repl, text)


def _apply_pronunciation_hints(text: str, hints: dict[str, str] | None) -> str:
    if not hints:
        return text
    for w, p in hints.items():
        text = re.sub(rf"\b{re.escape(w)}\b", p, text, flags=re.IGNORECASE)
    return text


def preprocess(text: str, hints: dict[str, str] | None) -> str:
    text = _BRACKET_TAG_RE.sub("", text)
    text = _expand_abbreviations(text)
    text = _expand_numbers(text)
    text = _apply_pronunciation_hints(text, hints)
    return text


# ---------- Segment parsing ----------

def _canonical_terminator(raw: str) -> str:
    if raw.startswith(".") and len(raw) >= 2:
        return "..."
    return raw


def parse_segments(text: str) -> list[dict]:
    """Split a section into per-sentence segments. Each dict has `text` (with
    trailing punctuation reattached for ElevenLabs prosody) and `terminator`
    (canonical: `.`, `?`, `!`, `...`, or `—`)."""
    text = _BRACKET_TAG_RE.sub("", text)
    parts = _TERMINATOR_RE.split(text)
    segments: list[dict] = []
    i = 0
    while i < len(parts):
        seg_text = re.sub(r"\s{2,}", " ", parts[i]).strip()
        raw_term = parts[i + 1] if i + 1 < len(parts) else None
        if not seg_text:
            i += 2
            continue
        if raw_term:
            spoken = seg_text + raw_term
            terminator = _canonical_terminator(raw_term)
        else:
            spoken = seg_text + "."
            terminator = "."
        segments.append({"text": spoken, "terminator": terminator})
        i += 2
    return segments


# ---------- Audio helpers (ffmpeg subprocess) ----------

def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            FFPROBE, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        text=True,
    )
    return float(out.strip())


def _silence_mp3(duration_s: float, work_dir: Path) -> Path:
    """Generate (and cache) a silence MP3 of the requested duration, matching
    ElevenLabs' 44.1kHz/128kbps stereo MP3 format so concat doesn't re-encode."""
    key = max(1, round(duration_s * 1000))
    cached = _silence_cache.get(key)
    if cached and cached.exists():
        return cached
    silence_dir = work_dir / "silence"
    silence_dir.mkdir(exist_ok=True)
    out = silence_dir / f"silence_{key}ms.mp3"
    subprocess.run(
        [
            FFMPEG, "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{duration_s:.3f}",
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(out),
        ],
        check=True, capture_output=True,
    )
    _silence_cache[key] = out
    return out


# ---------- ElevenLabs call ----------

def _tts_call(text: str, voice_id: str) -> bytes:
    """Single ElevenLabs text_to_speech.convert call. Returns MP3 bytes."""
    client = _get_client()
    audio_iter = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id=DEFAULT_MODEL,
        text=text,
        voice_settings=VOICE_SETTINGS,
        output_format=DEFAULT_OUTPUT_FORMAT,
    )
    return b"".join(audio_iter)


# ---------- Top-level synthesize ----------

def synthesize(
    sections: list[str],
    voice: str,
    work_dir: Path,
    print_input: bool = False,
    pronunciation_hints_by_section: list[dict[str, str]] | None = None,
) -> tuple[Path, list[dict]]:
    """Synthesize all sections via ElevenLabs and return (wav_path, section_bounds).

    Each sentence inside a section is its own API call, so punctuation cleanly
    drives prosody and silences are inserted between segments deterministically.
    """
    voice_id = resolve_voice(voice)
    voice_label = voice.lower() if voice.lower() in VOICES else f"voice_id={voice}"
    print(f"[tts] voice: {voice_label}  model: {DEFAULT_MODEL}", file=sys.stderr)

    hints_list = pronunciation_hints_by_section or [{}] * len(sections)
    if len(hints_list) < len(sections):
        hints_list = list(hints_list) + [{}] * (len(sections) - len(hints_list))

    # Preprocess all sections + parse into segments up front (lets us preview
    # total char count BEFORE we hit the API).
    preprocessed: list[list[dict]] = []
    total_chars_est = 0
    for i, raw in enumerate(sections):
        pre = preprocess(raw, hints_list[i])
        segs = parse_segments(pre)
        if not segs:
            raise RuntimeError(f"Section[{i}] produced 0 segments: {raw!r}")
        preprocessed.append(segs)
        total_chars_est += sum(len(s["text"]) for s in segs)

    # Credit pre-flight
    used_before, limit = get_credit_balance()
    if limit is not None and used_before is not None:
        remaining = limit - used_before
        print(
            f"[tts] credits: {used_before:,}/{limit:,} used "
            f"({remaining:,} chars remaining)",
            file=sys.stderr,
        )
        print(f"[tts] estimated for this reel: ~{total_chars_est:,} chars", file=sys.stderr)
        if total_chars_est > remaining:
            print(
                f"[tts] WARNING: estimated {total_chars_est:,} chars > "
                f"{remaining:,} remaining.",
                file=sys.stderr,
            )
            if sys.stdin.isatty():
                ans = input("Continue anyway? (y/N) ").strip().lower()
                if ans != "y":
                    raise SystemExit("Aborted (insufficient credits).")
            else:
                raise SystemExit(
                    "Aborted (insufficient credits, non-interactive). "
                    "Re-run from a TTY to override."
                )

    # Per-segment synthesis
    work_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    if print_input:
        print("[tts] === ElevenLabs input dump ===", file=sys.stderr)

    section_segment_paths: list[list[Path]] = []
    total_chars_sent = 0

    for i, segs in enumerate(preprocessed):
        seg_paths: list[Path] = []
        for j, seg in enumerate(segs):
            spoken = seg["text"]
            n_chars = len(spoken)
            total_chars_sent += n_chars
            preview = spoken if len(spoken) <= 50 else spoken[:50].rstrip() + "…"
            print(
                f"[tts]  s{i}.{j}  ({n_chars:>3} chars)  {preview!r}",
                file=sys.stderr,
            )
            if print_input:
                print(f"[tts]    full: {spoken!r}", file=sys.stderr)
            mp3_bytes = _tts_call(spoken, voice_id)
            out_path = segments_dir / f"s{i}_{j}.mp3"
            out_path.write_bytes(mp3_bytes)
            seg_paths.append(out_path)
        section_segment_paths.append(seg_paths)

    if print_input:
        print("[tts] === end input dump ===", file=sys.stderr)

    # Build concat list: alternate segment MP3 with appropriate silence
    concat_lines: list[str] = []
    per_segment_durations: list[list[float]] = []

    for i, (seg_paths, segs) in enumerate(zip(section_segment_paths, preprocessed)):
        section_durs: list[float] = []
        for j, (path, seg) in enumerate(zip(seg_paths, segs)):
            concat_lines.append(f"file '{path.resolve()}'")
            section_durs.append(_ffprobe_duration(path))
            if j < len(seg_paths) - 1:
                pause = PAUSE_BY_TERMINATOR_S.get(seg["terminator"], DEFAULT_PAUSE_S)
                concat_lines.append(f"file '{_silence_mp3(pause, work_dir).resolve()}'")
        per_segment_durations.append(section_durs)

        if i < len(section_segment_paths) - 1:
            gap = (
                INTER_SECTION_SILENCES_S[i]
                if i < len(INTER_SECTION_SILENCES_S)
                else INTER_SECTION_SILENCES_S[-1]
            )
            concat_lines.append(f"file '{_silence_mp3(gap, work_dir).resolve()}'")

    concat_txt = work_dir / "voice_concat.txt"
    concat_txt.write_text("\n".join(concat_lines) + "\n")

    voice_mp3 = work_dir / "voice.mp3"
    subprocess.run(
        [
            FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-c:a", "libmp3lame", "-b:a", "128k",
            str(voice_mp3),
        ],
        check=True, capture_output=True,
    )

    voice_wav = work_dir / "voice.wav"
    subprocess.run(
        [
            FFMPEG, "-y", "-i", str(voice_mp3),
            "-ar", str(WHISPER_SAMPLE_RATE), "-ac", "1",
            str(voice_wav),
        ],
        check=True, capture_output=True,
    )

    # Section bounds: cumulative time, excluding inter-section silence
    bounds: list[dict] = []
    t = 0.0
    for i, (seg_paths, segs) in enumerate(zip(section_segment_paths, preprocessed)):
        section_start = t
        for j, seg in enumerate(segs):
            t += per_segment_durations[i][j]
            if j < len(seg_paths) - 1:
                t += PAUSE_BY_TERMINATOR_S.get(seg["terminator"], DEFAULT_PAUSE_S)
        bounds.append({"start": section_start, "end": t})
        if i < len(section_segment_paths) - 1:
            t += (
                INTER_SECTION_SILENCES_S[i]
                if i < len(INTER_SECTION_SILENCES_S)
                else INTER_SECTION_SILENCES_S[-1]
            )

    # Post-render credit summary
    used_after, _limit_after = get_credit_balance()
    if used_after is not None and used_before is not None:
        delta = used_after - used_before
        print(
            f"[tts] credits used by this reel: {delta:,} chars  "
            f"(sent: {total_chars_sent:,})",
            file=sys.stderr,
        )
        if limit is not None:
            print(
                f"[tts] credits remaining: {limit - used_after:,}/{limit:,}",
                file=sys.stderr,
            )

    return voice_wav, bounds


def section_gap_seconds(section_idx: int) -> float:
    """Used by reel.py to align the video timeline with the inter-section silences."""
    if section_idx < len(INTER_SECTION_SILENCES_S):
        return INTER_SECTION_SILENCES_S[section_idx]
    return INTER_SECTION_SILENCES_S[-1]
