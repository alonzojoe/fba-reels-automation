#!/usr/bin/env python3
"""Voice comparison test — same hook, every voice in the catalog.

Generates one MP3 per voice in `tts.VOICES` using the LOCKED production
voice settings + model from pipeline/tts.py. Drops outputs at
    auditions/elevenlabs_<voice_name>.mp3
so they can be played back-to-back.

Run with:
    .venv/bin/python scripts/voice_comparison.py
"""
from __future__ import annotations

import os

# Match reel.py's defensive OpenMP settings (faster-whisper is imported elsewhere)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from pipeline import tts  # noqa: E402


# Canonical comparison text — same one across every voice.
TEST_TEXT = (
    "Waking up tired every morning? "
    "Here are three boosts that actually work. "
    "Save this... your body will thank you."
)


def main() -> None:
    out_dir = ROOT / "auditions"
    out_dir.mkdir(exist_ok=True)

    used_before, limit = tts.get_credit_balance()
    if used_before is not None and limit is not None:
        print(
            f"Credits before:  {used_before:>5,} / {limit:,}  "
            f"({limit - used_before:,} remaining)"
        )

    print(f"Model:      {tts.DEFAULT_MODEL}")
    print(f"Settings:   stability={tts.VOICE_SETTINGS.stability}, "
          f"style={tts.VOICE_SETTINGS.style}, "
          f"similarity_boost={tts.VOICE_SETTINGS.similarity_boost}")
    print(f"Test text ({len(TEST_TEXT)} chars):")
    print(f"  {TEST_TEXT!r}")
    print()

    chars_sent = 0
    for name, voice_id in tts.VOICES.items():
        marker = "*" if name == tts.DEFAULT_VOICE else " "
        print(f" {marker} {name:<8}  ({voice_id})  ...", end=" ", flush=True)
        mp3_bytes = tts._tts_call(TEST_TEXT, voice_id)
        chars_sent += len(TEST_TEXT)
        out_path = out_dir / f"elevenlabs_{name}.mp3"
        out_path.write_bytes(mp3_bytes)
        sz_kb = len(mp3_bytes) / 1024
        print(f"→ {out_path.relative_to(ROOT)}  ({sz_kb:.1f} KB)")

    print()
    print(f"Total chars sent: {chars_sent:,} across {len(tts.VOICES)} voices")

    used_after, _ = tts.get_credit_balance()
    if used_after is not None and used_before is not None:
        delta = used_after - used_before
        print(f"Credits used by this run: {delta:,} chars")
    if used_after is not None and limit is not None:
        print(f"Credits remaining:        {limit - used_after:>5,} / {limit:,}")

    print()
    print(f"Listen in order. Default is marked with *: '{tts.DEFAULT_VOICE}'.")


if __name__ == "__main__":
    main()
