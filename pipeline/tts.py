"""Voiceover synthesis with Kokoro TTS — naturalness-tuned.

Naturalness layers applied in order, per section:

1. **Bracket stripping**: any `[...]` tags are deleted before parsing.
   Kokoro v1.0 does NOT support cues like `[soft]`/`[whisper]` (verified —
   it pronounces them as words). If a script contains them anyway, they're
   silently removed so the literal bracketed text never reaches Kokoro.

2. **Abbreviation + number expansion** (`5 mg` → `five milligrams`, `Dr.` →
   `Doctor`, `5` → `five`, etc.) so Kokoro reads them like a human would.

3. **Pronunciation hints**: per-section `{word: phonetic}` map, applied as a
   word-boundary substitution before TTS. Useful for `turmeric` → `ter-mer-ik`,
   `ashwagandha` → `ash-wah-gahn-duh`, etc.

4. **Segment parsing**: each section is split at sentence terminators
   (`.`, `?`, `!`, `...`, `—`). Each segment is sent to Kokoro as its OWN
   call so punctuation drives prosody (questions actually rise, etc.).
   Variable silence between segments by terminator:
     - `.`   → 500 ms
     - `?` / `!` → 600 ms
     - `...` → 800 ms
     - `—`   → 200 ms

The locked brand voice is a blend of three Kokoro voices, averaged in
embedding space: `af_alloy + am_echo + am_fenrir`. Speed defaults to 0.88
(deliberate narrator pace). Inter-section silences are 600 ms across the
board so the editorial rhythm has room to breathe.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import num2words
import numpy as np
import soundfile as sf
import torch

warnings.filterwarnings("ignore")

# Locked brand voice
DEFAULT_VOICE_BLEND: list[str] = ["af_alloy", "am_echo", "am_fenrir"]
DEFAULT_VOICE: str = ",".join(DEFAULT_VOICE_BLEND)
DEFAULT_SPEED: float = 0.88

# Uniform inter-section silence (600 ms after every section boundary).
INTER_SECTION_SILENCES_S = [0.60, 0.60, 0.60, 0.60]

# Pause in seconds AFTER a segment ending in each terminator
PAUSE_BY_TERMINATOR_S: dict[str, float] = {
    ".":   0.50,
    "?":   0.60,
    "!":   0.60,
    "...": 0.80,
    "—":   0.20,
}
DEFAULT_PAUSE_S = 0.50  # if a segment has no terminator (final segment of section)

SAMPLE_RATE = 24000

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

_pipeline = None
_voice_cache: dict[str, torch.Tensor] = {}

# Pre-compiled regexes
# Bracket tags ([soft], [excited], etc.) are stripped silently — Kokoro v1.0
# does not honor them; if they reach Kokoro the literal word inside gets spoken.
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]\s*")
# Terminator match: `...` (2+ periods), or a single `.!?—`. Greedy on periods.
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


# ---------- Pipeline + voice loading ----------

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        print(
            f"[tts] Initializing Kokoro TTS (voice: {DEFAULT_VOICE}, speed: {DEFAULT_SPEED}).\n"
            "      First run downloads ~330MB model + spaCy data (1-2 min).",
            file=sys.stderr,
        )
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _pipeline


def _load_voice_tensor(voice_spec: str) -> torch.Tensor:
    if voice_spec in _voice_cache:
        return _voice_cache[voice_spec]
    pipeline = _get_pipeline()
    names = [n.strip() for n in voice_spec.split(",") if n.strip()]
    if not names:
        raise ValueError(f"Empty voice spec: {voice_spec!r}")
    if len(names) == 1:
        tensor = pipeline.load_single_voice(names[0])
    else:
        tensors = [pipeline.load_single_voice(n) for n in names]
        tensor = torch.mean(torch.stack(tensors), dim=0)
        print(
            f"[tts] Blending {len(names)} voices with equal weights: "
            f"{', '.join(names)}",
            file=sys.stderr,
        )
    _voice_cache[voice_spec] = tensor
    return tensor


def section_gap_seconds(section_idx: int) -> float:
    if section_idx < len(INTER_SECTION_SILENCES_S):
        return INTER_SECTION_SILENCES_S[section_idx]
    return INTER_SECTION_SILENCES_S[-1]


# ---------- Text preprocessing ----------

def _expand_abbreviations(text: str) -> str:
    for pat, repl in _ABBREVIATIONS:
        text = pat.sub(repl, text)
    return text


def _expand_numbers(text: str) -> str:
    """Convert standalone integers up to 100 into words (per the project rule)."""
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
    for word, phon in hints.items():
        text = re.sub(
            rf"\b{re.escape(word)}\b", phon, text, flags=re.IGNORECASE
        )
    return text


def preprocess(text: str, hints: dict[str, str] | None) -> str:
    """Run all text preprocessing (numbers, abbreviations, pronunciation hints)."""
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
    """Split a section into TTS segments.

    Each segment dict carries:
      - text:       the trimmed spoken text, ending with its punctuation
      - terminator: canonical terminator (`.`, `?`, `!`, `...`, or `—`)

    Any `[...]` bracket tags are stripped silently up front — Kokoro v1.0 does
    not honor them; if left in, the literal word inside would be spoken aloud.
    """
    # Strip any bracket tags before parsing
    text = _BRACKET_TAG_RE.sub("", text)

    # Split with capture so terminators are preserved in the result list
    parts = _TERMINATOR_RE.split(text)
    # parts = [text0, term0, text1, term1, ..., trailing_or_empty]

    segments: list[dict] = []
    i = 0
    while i < len(parts):
        raw_text = parts[i]
        raw_terminator = parts[i + 1] if i + 1 < len(parts) else None
        terminator = _canonical_terminator(raw_terminator) if raw_terminator else None

        seg_text = re.sub(r"\s{2,}", " ", raw_text).strip()
        if not seg_text:
            i += 2
            continue

        # Reattach the terminator so Kokoro sees punctuation-driven intonation cues
        if terminator:
            spoken = seg_text + terminator
        else:
            spoken = seg_text + "."
            terminator = "."  # treat as period for pause lookup

        segments.append({
            "text": spoken,
            "terminator": terminator,
        })
        i += 2

    return segments


# ---------- Synthesis ----------

def _to_float32(audio) -> np.ndarray:
    if hasattr(audio, "detach"):
        audio = audio.detach()
    if hasattr(audio, "cpu"):
        audio = audio.cpu()
    if hasattr(audio, "numpy"):
        audio = audio.numpy()
    arr = np.asarray(audio)
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32, copy=False)
    return arr


def synthesize(
    sections: list[str],
    voice: str,
    work_dir: Path,
    speed: float = DEFAULT_SPEED,
    print_input: bool = False,
    pronunciation_hints_by_section: list[dict[str, str]] | None = None,
) -> tuple[Path, list[dict]]:
    """Synthesize sections with naturalness preprocessing + per-segment TTS.

    `pronunciation_hints_by_section[i]` is the optional `{word: phonetic}` map
    applied to section i before TTS. Missing entries default to no hints.

    Returns (wav_path, [{'start', 'end'} per section]).
    """
    pipeline = _get_pipeline()
    voice_tensor = _load_voice_tensor(voice)

    hints_list = pronunciation_hints_by_section or [{}] * len(sections)
    if len(hints_list) < len(sections):
        hints_list = list(hints_list) + [{}] * (len(sections) - len(hints_list))

    if print_input:
        print("[tts] === text sent to Kokoro (one call per SEGMENT) ===", file=sys.stderr)

    section_arrays: list[np.ndarray] = []
    for i, section_text in enumerate(sections):
        pre = preprocess(section_text, hints_list[i])
        segments = parse_segments(pre)
        if not segments:
            raise RuntimeError(
                f"Section[{i}] produced 0 segments. Raw: {section_text!r}"
            )

        if print_input:
            print(
                f"[tts] section[{i}]  preprocessed: {pre!r}  "
                f"→ {len(segments)} segment(s)",
                file=sys.stderr,
            )

        segment_arrays: list[np.ndarray] = []
        for j, seg in enumerate(segments):
            if print_input:
                print(
                    f"[tts]   seg[{i}.{j}]: {seg['text']!r}  "
                    f"term={seg['terminator']!r}",
                    file=sys.stderr,
                )
            chunks: list[np.ndarray] = []
            for graphemes, phonemes, audio in pipeline(
                seg["text"], voice=voice_tensor, speed=speed,
            ):
                chunks.append(_to_float32(audio))
                if print_input:
                    print(
                        f"[tts]     chunk: graphemes={graphemes!r}  "
                        f"phonemes={phonemes!r}  samples={len(chunks[-1])}",
                        file=sys.stderr,
                    )
            if not chunks:
                raise RuntimeError(f"Kokoro produced no audio for segment: {seg!r}")
            segment_arrays.append(np.concatenate(chunks))

        # Concat segments with punctuation-driven silences
        pieces: list[np.ndarray] = []
        for j, (arr, seg) in enumerate(zip(segment_arrays, segments)):
            pieces.append(arr)
            if j < len(segment_arrays) - 1:
                pause = PAUSE_BY_TERMINATOR_S.get(seg["terminator"], DEFAULT_PAUSE_S)
                pieces.append(np.zeros(int(SAMPLE_RATE * pause), dtype=np.float32))
        section_arrays.append(np.concatenate(pieces))

    if print_input:
        print("[tts] === end Kokoro input dump ===", file=sys.stderr)

    # Inter-section silences (per-boundary)
    durations = [len(a) / SAMPLE_RATE for a in section_arrays]
    pieces: list[np.ndarray] = []
    for i, arr in enumerate(section_arrays):
        pieces.append(arr)
        if i < len(section_arrays) - 1:
            gap = section_gap_seconds(i)
            pieces.append(np.zeros(int(SAMPLE_RATE * gap), dtype=np.float32))
    full_audio = np.concatenate(pieces)

    raw_wav = work_dir / "voice_24k.wav"
    sf.write(str(raw_wav), full_audio, SAMPLE_RATE)

    combined_wav = work_dir / "voice.wav"
    subprocess.run(
        [
            FFMPEG, "-y", "-i", str(raw_wav),
            "-ar", "16000", "-ac", "1",
            str(combined_wav),
        ],
        check=True, capture_output=True,
    )

    bounds: list[dict] = []
    t = 0.0
    for i, dur in enumerate(durations):
        bounds.append({"start": t, "end": t + dur})
        t += dur
        if i < len(durations) - 1:
            t += section_gap_seconds(i)
    return combined_wav, bounds
