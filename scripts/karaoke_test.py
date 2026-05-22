#!/usr/bin/env python3
"""Karaoke caption smoke test.

Synthesizes a short sentence via ElevenLabs (using the locked brand voice
+ settings), runs faster-whisper on the resulting audio to get word
timestamps, builds the karaoke-style ASS via captions.build_ass, and
renders a single MP4 over a solid #111111 background so the new caption
style can be inspected end-to-end without a full reel pipeline run.

Output: debug/karaoke_test.mp4

Run with:
    .venv/bin/python scripts/karaoke_test.py
"""
from __future__ import annotations

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

from pipeline import captions, transcribe, tts  # noqa: E402


TEST_TEXT = "Take a cold shower for thirty seconds."

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")


def _probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    )
    return float(out.strip())


def main() -> None:
    debug_dir = ROOT / "debug"
    debug_dir.mkdir(exist_ok=True)
    work_dir = ROOT / "work" / ".karaoke_test"
    if work_dir.exists():
        import shutil
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    print(f"Test text:  {TEST_TEXT!r}")

    print("[1/4] Synthesizing with ElevenLabs...")
    voice_wav, bounds = tts.synthesize([TEST_TEXT], tts.DEFAULT_VOICE, work_dir)
    voice_duration = _probe_duration(voice_wav)
    print(f"  → {voice_wav.relative_to(ROOT)}  ({voice_duration:.2f}s)")

    print("[2/4] Transcribing with faster-whisper...")
    words = transcribe.transcribe(voice_wav)
    print(f"  → {len(words)} words timestamped:")
    for w in words:
        print(f"      {w['start']:5.2f}s – {w['end']:5.2f}s   {w['word']!r}")

    print("[3/4] Building karaoke ASS...")
    ass_text = captions.build_ass(words, total_duration=voice_duration + 0.5)
    captions_path = work_dir / "captions.ass"
    captions_path.write_text(ass_text)
    print(f"  → {captions_path.relative_to(ROOT)}")
    phrase_count = sum(1 for line in ass_text.splitlines() if line.startswith("Dialogue:")) // 2
    print(f"  → {phrase_count} phrase(s) in ASS output")

    print("[4/4] Rendering test MP4...")
    out_path = debug_dir / "karaoke_test.mp4"
    duration = voice_duration + 0.5  # small tail
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x111111:s=1080x1920:d={duration:.2f}:r=30",
            "-i", str(voice_wav.resolve()),
            "-filter_complex", f"[0:v]subtitles={captions_path.name}[vout]",
            "-map", "[vout]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            str(out_path.resolve()),
        ],
        check=True, capture_output=True,
        cwd=str(work_dir.resolve()),
    )

    sz = out_path.stat().st_size
    print()
    print(f"→ {out_path.relative_to(ROOT)}  ({sz / 1024:.1f} KB, {duration:.2f}s)")


if __name__ == "__main__":
    main()
