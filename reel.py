#!/usr/bin/env python3
"""Render a faceless health/home-remedies vertical Facebook Reel from a script JSON.

Voice: hardcoded to Kokoro `am_michael` for brand consistency. Override with
--voice only when prototyping. All on-screen text shares one `--text-color`.
The outro is overlaid on extended CTA footage with a bottom gradient — no
separate solid card.
"""
from __future__ import annotations

import os

# Kokoro (via torch) and faster-whisper (via ctranslate2) both link libiomp5.
# Without these env vars, loading both in one process triggers an OpenMP
# double-init segfault. Set BEFORE any pipeline imports.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from pipeline import assemble, captions, footage, script, transcribe, tts

SECTION_LABELS = ["hook", "tip1", "tip2", "tip3", "cta"]
BG_MUSIC_DIR = Path("bg-music")
BG_MUSIC_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

SCRIPT_MISSING_HELP = """\
ERROR: --script is required.

This pipeline doesn't call any LLM API directly. Generate the script first,
then pass it in via --script.

Step 1 — Generate a script:
  Open prompts/script-generation.md, copy its contents into Claude Code
  (claude.ai/code), and append your topic. Save the JSON output to
  script.json (or any filename you prefer).

  Alternatively, write the JSON manually following the schema documented at
  the top of prompts/script-generation.md.

Step 2 — Render the reel:
  python3 reel.py --script script.json
"""


def pick_random_music(bg_dir: Path) -> Path | None:
    if not bg_dir.exists():
        return None
    candidates = [
        f for f in bg_dir.iterdir()
        if f.is_file() and f.suffix.lower() in BG_MUSIC_EXTS
    ]
    if not candidates:
        return None
    return random.choice(candidates)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description=(
            "Render a faceless health/remedies vertical Facebook Reel from a script JSON."
        ),
    )
    parser.add_argument(
        "--script", default=None,
        help="Path to the script JSON file (required). See prompts/script-generation.md.",
    )
    parser.add_argument(
        "--out", default="out/final.mp4",
        help="Output MP4 path (default: out/final.mp4)",
    )
    parser.add_argument(
        "--voice", default=tts.DEFAULT_VOICE,
        help=(
            "Kokoro voice. Accepts a single name (am_michael) or a comma-separated "
            f"blend (af_alloy,am_echo,am_fenrir). Default is the locked brand "
            f"blend: {tts.DEFAULT_VOICE}. Override only when prototyping."
        ),
    )
    parser.add_argument(
        "--speed", type=float, default=tts.DEFAULT_SPEED,
        help=(
            f"Speech speed multiplier (Kokoro default 1.0). "
            f"Default: {tts.DEFAULT_SPEED} (locked brand pace)."
        ),
    )
    parser.add_argument(
        "--music", default=None,
        help=f"Background music file (overrides auto-pick from {BG_MUSIC_DIR}/).",
    )
    parser.add_argument(
        "--no-music", action="store_true",
        help=f"Explicitly skip music even if {BG_MUSIC_DIR}/ has files.",
    )
    parser.add_argument(
        "--no-outro", action="store_true",
        help=(
            "Skip the spoken outro line at the end of the CTA "
            '(default: appends "Like and follow for more." to the CTA voiceover).'
        ),
    )
    parser.add_argument(
        "--outro-text", default=captions.DEFAULT_OUTRO_TEXT,
        help=(
            f'Spoken outro line, appended to the CTA voiceover. Use "|" as a '
            f'line separator (joined with a space when spoken). '
            f'Default: "{captions.DEFAULT_OUTRO_TEXT}".'
        ),
    )
    parser.add_argument(
        "--text-color", default=captions.DEFAULT_TEXT_COLOR,
        help=(
            "Color (hex #RRGGBB) for ALL on-screen text — body captions and outro. "
            f"Default: {captions.DEFAULT_TEXT_COLOR} (vibrant green, on-brand for health/wellness)."
        ),
    )
    parser.add_argument(
        "--print-tts-input", action="store_true",
        help=(
            "Dump the EXACT strings (and Kokoro grapheme/phoneme output) sent to "
            "TTS per section. Useful for debugging punctuation/prosody issues."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate script + Pexels search only. No TTS/transcription/render.",
    )
    parser.add_argument(
        "--keep-work", action="store_true",
        help="Keep the work/<ts>/ directory after success.",
    )
    args = parser.parse_args()

    if not args.script:
        print(SCRIPT_MISSING_HELP)
        sys.exit(1)

    pexels_key = os.environ.get("PEXELS_API_KEY")
    if not pexels_key:
        sys.exit("ERROR: PEXELS_API_KEY not set. Copy .env.example to .env and fill it in.")

    if args.no_music:
        music_path: Path | None = None
        music_status = "skipped (--no-music)"
    elif args.music:
        music_path = Path(args.music)
        if not music_path.exists():
            sys.exit(f"ERROR: music file not found: {music_path}")
        music_status = f"explicit: {music_path}"
    else:
        music_path = pick_random_music(BG_MUSIC_DIR)
        if music_path:
            music_status = f"auto-picked from {BG_MUSIC_DIR}/: {music_path.name}"
        else:
            music_status = f"skipped ({BG_MUSIC_DIR}/ empty or missing)"

    script_path = Path(args.script)
    print(f"[reel] script: {script_path}")
    script_data = script.load_script(script_path)

    ts = time.strftime("%Y%m%d_%H%M%S")
    work_dir = Path("work") / ts
    work_dir.mkdir(parents=True, exist_ok=True)
    print(f"[reel] work dir: {work_dir}")
    print(
        f"[reel] voice: {args.voice} @ {args.speed}  music: {music_status}  "
        f"text-color: {args.text_color}"
    )
    (work_dir / "script.json").write_text(json.dumps(script_data, indent=2))

    include_spoken_outro = not args.no_outro
    outro_text = args.outro_text if include_spoken_outro else None

    section_texts = [
        script_data["hook"]["text"],
        *(t["text"] for t in script_data["tips"]),
        script_data["cta"]["text"],
    ]
    sections_meta = [
        script_data["hook"],
        *script_data["tips"],
        script_data["cta"],
    ]

    # Append the outro line to the CTA voiceover so the body captions naturally
    # show "Like and follow for more" word-by-word as the voice says it — no
    # separate big-text overlay is needed.
    if outro_text:
        spoken_outro = " ".join(p.strip() for p in outro_text.split("|") if p.strip())
        spoken_outro = spoken_outro.capitalize() + "."
        cta = section_texts[-1].strip()
        if cta and not cta.endswith((".", "!", "?")):
            cta += "."
        section_texts[-1] = (cta + " " + spoken_outro).strip()

    word_count = sum(len(t.split()) for t in section_texts)
    est_seconds = word_count / 140 * 60
    print(f"[1/6] Script loaded: {word_count} words (~{est_seconds:.0f}s spoken @ 140 wpm)")
    for label, text in zip(SECTION_LABELS, section_texts):
        print(f"      [{label}] {text}")

    if args.dry_run:
        print("\n[dry-run] Planning cuts + searching Pexels (no downloads)...")
        # Rough section durations from word count for the dry-run plan
        est_voice_durations = [len(t.split()) * 60 / 140 for t in section_texts]
        # CTA extends to include outro overlay time
        video_durations = list(est_voice_durations)
        if include_outro:
            video_durations[-1] += outro_duration
        results = footage.search_only(pexels_key, sections_meta, video_durations)
        (work_dir / "dry_run_report.json").write_text(json.dumps(results, indent=2))
        print("\n[dry-run report]")
        total_cuts = 0
        for label, r in zip(SECTION_LABELS, results):
            qs = r["section"].get("queries", [])
            print(f"  [{label}] queries={qs!r}")
            if "error" in r:
                print(f"        ERROR: {r['error']}")
                continue
            sub_durs = r["sub_durations"]
            tag = " (hook — fast cuts + Ken Burns)" if r.get("is_hook") else ""
            print(f"        cuts: {len(sub_durs)}  durations: {sub_durs}{tag}")
            total_cuts += len(sub_durs)
            for c in r["clips"]:
                print(
                    f"          - video_id={c['video_id']}  {c['duration']}s  "
                    f"{c['width']}x{c['height']}"
                )
                print(f"            {c['video_url']}")
        print(f"\n  Total clip cuts planned: {total_cuts}")
        print(f"\n[reel] Dry run complete. Work dir: {work_dir}")
        return

    # Per-section pronunciation hints (optional in script JSON)
    pronunciation_hints = [
        sec.get("pronunciation_hints", {}) for sec in sections_meta
    ]

    print(f"[2/6] Synthesizing voiceover with Kokoro TTS ({args.voice} @ {args.speed})...")
    voice_wav, section_bounds = tts.synthesize(
        section_texts, args.voice, work_dir,
        speed=args.speed, print_input=args.print_tts_input,
        pronunciation_hints_by_section=pronunciation_hints,
    )
    (work_dir / "sections.json").write_text(json.dumps(section_bounds, indent=2))
    total_voice_duration = section_bounds[-1]["end"]
    print(f"      Voiceover: {total_voice_duration:.1f}s")

    print("[3/6] Extracting word timestamps with faster-whisper...")
    words = transcribe.transcribe(voice_wav)
    (work_dir / "words.json").write_text(json.dumps(words, indent=2))
    print(f"      {len(words)} words timestamped")

    print("[4/6] Planning cuts + downloading stock footage from Pexels...")
    voice_section_durations = [b["end"] - b["start"] for b in section_bounds]
    # Video timeline must match the audio timeline: each non-last section's
    # video continues playing through that section's per-boundary inter-section
    # silence. No visual outro extension — the video ends when the voice ends.
    video_section_durations = list(voice_section_durations)
    for i in range(len(video_section_durations) - 1):
        video_section_durations[i] += tts.section_gap_seconds(i)

    sub_segments = footage.fetch_clips(
        pexels_key, sections_meta, video_section_durations, work_dir
    )
    sub_counts = [
        len(footage.split_section_into_subs(d, is_hook=(i == 0)))
        for i, d in enumerate(video_section_durations)
    ]
    # Group sub-segments by section using the known per-section sub-counts
    grouped: list[list[tuple[Path, float]]] = []
    idx = 0
    for count in sub_counts:
        grouped.append([(p, d) for (p, d, _si) in sub_segments[idx:idx + count]])
        idx += count
    total_cuts = sum(sub_counts)
    hook_cuts = sub_counts[0]
    print(
        f"      {total_cuts} clip cuts across {len(grouped)} sections "
        f"(cuts per section: {sub_counts})  hook: {hook_cuts} fast cuts"
    )

    print("[5/6] Building captions (ASS)...")
    # No visual outro overlay — the spoken outro is captured by the body
    # word captions when the voice says "Like and follow for more".
    ass_content = captions.build_ass(
        words,
        total_voice_duration,
        outro_text=None,
        outro_duration=0.0,
        text_color=args.text_color,
    )
    captions_path = work_dir / "captions.ass"
    captions_path.write_text(ass_content)

    print("[6/6] Assembling final MP4 with ffmpeg...")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Render each section as its own xfade chain (Ken Burns + variety transitions
    # within the hook section; standard cuts elsewhere). Hard cut between sections.
    section_videos: list[Path] = []
    cut_idx = 0
    for section_idx, subs in enumerate(grouped):
        is_hook = section_idx == 0
        section_video, cut_idx = assemble.render_section_with_xfade(
            subs, work_dir, section_idx,
            starting_cut_idx=cut_idx, kenburns=is_hook,
        )
        section_videos.append(section_video)

    assemble.assemble(
        section_videos,
        voice_wav,
        captions_path,
        music_path,
        out_path,
        work_dir,
        voice_pad_seconds=0.0,
        outro_overlay_start=0.0,
        outro_overlay_end=0.0,
    )

    print(f"\n[reel] Done! Output: {out_path}")

    if args.keep_work:
        print(f"[reel] Work dir preserved: {work_dir}")
    else:
        shutil.rmtree(work_dir)


if __name__ == "__main__":
    main()
