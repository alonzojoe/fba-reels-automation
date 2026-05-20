"""Voiceover synthesis with Kokoro TTS.

The locked brand voice is a **blend** of three Kokoro voices, averaged in
embedding space: `af_alloy + am_echo + am_fenrir`. This blend was auditioned on
the Kokoro web demo and chosen for a warm-but-authoritative narrator quality.
Keep it consistent across every reel for audience recognition.

Speed defaults to 1.0 (Kokoro's natural pace, matches the kokoroai.org web
demo). Inter-section silences are tuned per boundary (400 ms after the hook,
250 ms between tips, 500 ms before the CTA) for editorial rhythm.

**Per-sentence synthesis for prosody:** each sentence inside a section is sent
to Kokoro as its OWN call, with a 180 ms silence between sentences. This gives
each `?` / `!` / `.` its own utterance envelope so questions actually rise and
exclamations actually emphasize — passing a question + statement as one Kokoro
call tends to flatten the rising contour. Sentences are split on `.`/`?`/`!`
followed by whitespace; the terminator stays attached to the preceding sentence.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

warnings.filterwarnings("ignore")

# Locked brand voice: blend of three Kokoro voices, equal weights.
# Override via CLI --voice "name" (single) or --voice "a,b,c" (comma-separated blend).
DEFAULT_VOICE_BLEND: list[str] = ["af_alloy", "am_echo", "am_fenrir"]
DEFAULT_VOICE: str = ",".join(DEFAULT_VOICE_BLEND)
DEFAULT_SPEED: float = 1.0

# Per-boundary inter-section silences. Index i is the gap AFTER section i.
# Order matches the canonical [hook, tip1, tip2, tip3, cta] sequence.
INTER_SECTION_SILENCES_S = [
    0.40,  # after hook    → before tip1   (longer pause sets up the tips)
    0.25,  # after tip1    → before tip2
    0.25,  # after tip2    → before tip3
    0.50,  # after tip3    → before CTA    (dramatic beat before the close)
]
INTER_SENTENCE_SILENCE_S = 0.18  # gap between sentences WITHIN one section
SAMPLE_RATE = 24000

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

_pipeline = None
_voice_cache: dict[str, torch.Tensor] = {}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


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
    """Resolve a voice spec to a torch tensor.

    `voice_spec` is either a single voice name (e.g. 'am_michael') or a
    comma-separated blend (e.g. 'af_alloy,am_echo,am_fenrir'). Multiple voices
    are blended by averaging their embedding tensors (equal weights). Loaded
    tensors are cached so repeated calls within one Python process don't hit
    the network or filesystem twice.
    """
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
    """Silence AFTER the given section (between section_idx and section_idx+1)."""
    if section_idx < len(INTER_SECTION_SILENCES_S):
        return INTER_SECTION_SILENCES_S[section_idx]
    return INTER_SECTION_SILENCES_S[-1]


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
) -> tuple[Path, list[dict]]:
    """Synthesize each section as ONE Kokoro call (preserves prosody context),
    concat with per-boundary inter-section silences, return a 16 kHz mono WAV.

    `voice` accepts a single name or comma-separated blend — see _load_voice_tensor.
    `print_input=True` dumps the exact strings sent to Kokoro for debugging.

    Returns (wav_path, [{'start': float, 'end': float}, ...] per section).
    """
    pipeline = _get_pipeline()
    voice_tensor = _load_voice_tensor(voice)
    sentence_silence = np.zeros(
        int(SAMPLE_RATE * INTER_SENTENCE_SILENCE_S), dtype=np.float32
    )

    section_arrays: list[np.ndarray] = []
    if print_input:
        print(
            "[tts] === text sent to Kokoro (one call per SENTENCE) ===",
            file=sys.stderr,
        )
    for i, section_text in enumerate(sections):
        sentences = _split_sentences(section_text) or [section_text]
        if print_input:
            print(
                f"[tts] section[{i}] split into {len(sentences)} sentence(s):",
                file=sys.stderr,
            )

        sentence_arrays: list[np.ndarray] = []
        for j, sentence in enumerate(sentences):
            if print_input:
                print(f"[tts]   sent[{i}.{j}]: {sentence!r}", file=sys.stderr)
            chunks: list[np.ndarray] = []
            for graphemes, phonemes, audio in pipeline(
                sentence, voice=voice_tensor, speed=speed,
            ):
                chunks.append(_to_float32(audio))
                if print_input:
                    print(
                        f"[tts]     chunk: graphemes={graphemes!r}  "
                        f"phonemes={phonemes!r}  samples={len(chunks[-1])}",
                        file=sys.stderr,
                    )
            if not chunks:
                raise RuntimeError(
                    f"Kokoro produced no audio for sentence: {sentence!r}"
                )
            sentence_arrays.append(np.concatenate(chunks))

        pieces: list[np.ndarray] = []
        for k, arr in enumerate(sentence_arrays):
            pieces.append(arr)
            if k < len(sentence_arrays) - 1:
                pieces.append(sentence_silence)
        section_arrays.append(np.concatenate(pieces))
    if print_input:
        print("[tts] === end Kokoro input dump ===", file=sys.stderr)

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
