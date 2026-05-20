#!/usr/bin/env python3
"""Naturalness A/B test for Kokoro TTS.

Synthesizes the same hook with four progressively more "natural" variations
so the diff between baseline and full naturalness can be heard side-by-side:

    1. baseline      — plain text, no special punctuation, no hints, no cues
    2. punctuation   — `?` + `...` + period-driven sentence breaks
    3. phonetic      — adds a pronunciation_hints map for a hard word
    4. cues          — adds inline [soft] / [excited] emotional cues

Outputs land at  auditions/naturalness_<n>.wav  using the LOCKED brand
voice + speed from pipeline/tts.py, so you're hearing the same voice that
the production renders use.

Run with:

    .venv/bin/python scripts/naturalness_test.py
"""
from __future__ import annotations

import os

# Kokoro + faster-whisper OpenMP coexistence (matches reel.py).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import shutil
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# Make `pipeline` importable when running from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import tts  # noqa: E402


VARIATIONS: list[dict] = [
    {
        "label": "baseline",
        "text": "Wake up tired every day. Try this remedy. It works.",
        "hints": {},
    },
    {
        "label": "punctuation",
        "text": "Wake up tired every day? Try this remedy... It works.",
        "hints": {},
    },
    {
        "label": "phonetic",
        "text": "Try turmeric tea every morning... It works.",
        "hints": {"turmeric": "ter-mer-ik"},
    },
    {
        "label": "cues",
        "text": "[soft] Wake up tired every day? [excited] Try this... it works!",
        "hints": {},
    },
]


def main() -> None:
    out_dir = ROOT / "auditions"
    out_dir.mkdir(exist_ok=True)
    work_root = ROOT / "work" / ".naturalness_test"
    work_root.mkdir(parents=True, exist_ok=True)

    for i, v in enumerate(VARIATIONS, start=1):
        work = work_root / f"v{i}_{v['label']}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir()

        print(f"\n=== variation {i} — {v['label']} ===")
        print(f"  text:  {v['text']!r}")
        print(f"  hints: {v['hints']!r}")

        wav, bounds = tts.synthesize(
            sections=[v["text"]],
            voice=tts.DEFAULT_VOICE,
            work_dir=work,
            speed=tts.DEFAULT_SPEED,
            print_input=True,
            pronunciation_hints_by_section=[v["hints"]],
        )

        target = out_dir / f"naturalness_{i}_{v['label']}.wav"
        shutil.copy(str(wav), str(target))
        print(f"  → {target.relative_to(ROOT)}  ({bounds[0]['end']:.2f}s)")

    print()
    print(f"Audition files written to {out_dir.relative_to(ROOT)}/")
    print("Compare in order: 1 → 2 → 3 → 4 should sound progressively more human.")


if __name__ == "__main__":
    main()
