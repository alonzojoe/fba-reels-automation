"""Final assembly: scale each clip to 1080x1920 (crop or blurred-bg fallback),
apply Ken Burns zoom on hook clips, chain sub-segments within each section with
varied xfade transitions (fade/zoom/slide), hard-cut between sections, burn the
captions with a bottom drawbox gradient during the outro overlay window, and mix
the audio (voice + optional looped background music with tail fade-out).

The outro is overlaid on the extended CTA footage — there is no separate solid
'outro card' segment any more."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

TARGET_W = 1080
TARGET_H = 1920
PORTRAIT_AR_MIN = 0.50
PORTRAIT_AR_MAX = 0.65

# Within-section xfade overlap (must match footage.XFADE_DURATION)
XFADE_DURATION = 0.15

# Ken Burns zoom for hook clips: scale from 1.0 → KEN_BURNS_END over clip duration
KEN_BURNS_END = 1.08

# Music mix
MUSIC_VOLUME = 0.05          # ~ -26 dB (kept low so the spoken CTA + outro land cleanly)
FADE_OUT_SECONDS = 1.5

# Outro gradient overlay (lower portion of frame, stacked-drawbox stepped gradient)
GRADIENT_BANDS = [
    # (y_top, height, alpha)  — y_top + height ≤ 1920
    (1100, 130, 0.05),
    (1230, 130, 0.12),
    (1360, 130, 0.22),
    (1490, 130, 0.32),
    (1620, 300, 0.42),
]

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run wrapper that surfaces stderr on nonzero exit."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {result.returncode})\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr (last 2000 chars):\n{result.stderr[-2000:]}"
        )
    return result


def _probe_aspect(clip: Path) -> float:
    out = subprocess.check_output(
        [
            FFPROBE, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(clip),
        ],
        text=True,
    )
    s = json.loads(out)["streams"][0]
    return s["width"] / s["height"]


def _probe_duration(clip: Path) -> float:
    out = subprocess.check_output(
        [
            FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(clip),
        ],
        text=True,
    )
    return float(out.strip())


def _ken_burns_suffix(duration: float) -> str:
    """A scale+crop pair that ramps the zoom from 1.0 to KEN_BURNS_END over `duration`."""
    z = f"(1+{(KEN_BURNS_END - 1.0):.4f}*t/{duration:.3f})"
    return (
        f"scale='floor({TARGET_W}*{z}/2)*2':'floor({TARGET_H}*{z}/2)*2':eval=frame,"
        f"crop={TARGET_W}:{TARGET_H}"
    )


def process_clip(
    clip: Path,
    duration: float,
    work_dir: Path,
    tag: str,
    kenburns: bool = False,
) -> Path:
    """Trim to `duration`, scale to 1080x1920 (crop-only for portrait, blurred-bg
    fallback otherwise), strip audio. If `kenburns` is True, ramp a 1.0→1.08
    zoom over the clip duration."""
    out = work_dir / f"seg_{tag}.mp4"
    aspect = _probe_aspect(clip)
    kb = "," + _ken_burns_suffix(duration) if kenburns else ""

    if PORTRAIT_AR_MIN <= aspect <= PORTRAIT_AR_MAX:
        vf = (
            f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H}{kb},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS"
        )
        cmd = [
            FFMPEG, "-y", "-i", str(clip),
            "-an", "-vf", vf,
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", "30",
            str(out),
        ]
    else:
        filter_complex = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H},gblur=sigma=30[bgblur];"
            f"[fg]scale={TARGET_W}:-2[fgscale];"
            f"[bgblur][fgscale]overlay=(W-w)/2:(H-h)/2{kb},"
            f"trim=duration={duration:.3f},setpts=PTS-STARTPTS"
        )
        cmd = [
            FFMPEG, "-y", "-i", str(clip),
            "-an", "-filter_complex", filter_complex,
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", "30",
            str(out),
        ]
    _run(cmd)
    return out


def _transition_for_cut(cut_idx: int) -> str:
    """Deterministic transition picker — 60% fade / 25% zoomin / 15% slide.

    cut_idx is the index of the cut (0 = transition between segment 0 and 1).
    Re-renders are stable because the choice is a pure function of the index.
    """
    bucket = cut_idx % 20
    if bucket < 12:
        return "fade"
    if bucket < 17:
        return "zoomin"
    return ("slideleft", "slideup", "slideright")[cut_idx % 3]


def render_section_with_xfade(
    sub_segments: list[tuple[Path, float]],
    work_dir: Path,
    section_idx: int,
    starting_cut_idx: int,
    kenburns: bool = False,
) -> tuple[Path, int]:
    """Process each sub-segment then chain with varied xfade transitions.

    `starting_cut_idx` is the global cut index of the FIRST transition in this
    section (so the variety pattern continues unbroken across sections).
    Returns (section_video_path, next_starting_cut_idx).
    """
    if len(sub_segments) == 1:
        clip, dur = sub_segments[0]
        out = process_clip(clip, dur, work_dir, f"s{section_idx}", kenburns=kenburns)
        return out, starting_cut_idx

    processed: list[tuple[Path, float]] = []
    for sub_idx, (clip, dur) in enumerate(sub_segments):
        out = process_clip(
            clip, dur, work_dir, f"s{section_idx}_{sub_idx}", kenburns=kenburns
        )
        processed.append((out, dur))

    inputs: list[str] = []
    for p, _ in processed:
        inputs += ["-i", str(p.resolve())]

    filter_parts: list[str] = []
    prev_label = "[0:v]"
    cumulative = processed[0][1]
    cut_idx = starting_cut_idx
    for i in range(1, len(processed)):
        out_label = f"[v{i}]"
        offset = cumulative - XFADE_DURATION
        transition = _transition_for_cut(cut_idx)
        filter_parts.append(
            f"{prev_label}[{i}:v]"
            f"xfade=transition={transition}:duration={XFADE_DURATION}:offset={offset:.3f}"
            f"{out_label}"
        )
        prev_label = out_label
        cumulative += processed[i][1] - XFADE_DURATION
        cut_idx += 1

    section_out = work_dir / f"section_{section_idx}.mp4"
    _run(
        [
            FFMPEG, "-y", *inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", prev_label,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-r", "30",
            str(section_out),
        ]
    )
    return section_out, cut_idx


def _concat_videos(segments: list[Path], work_dir: Path) -> Path:
    concat_txt = work_dir / "video_concat.txt"
    concat_txt.write_text(
        "\n".join(f"file '{s.resolve()}'" for s in segments) + "\n"
    )
    out = work_dir / "video_concat.mp4"
    _run(
        [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            str(out),
        ]
    )
    return out


def _gradient_filter(start_t: float, end_t: float) -> str:
    """Stacked-drawbox stepped vertical gradient at the bottom of the frame,
    only enabled during [start_t, end_t]. Approximates a smooth alpha ramp."""
    bands = []
    for y, h, a in GRADIENT_BANDS:
        bands.append(
            f"drawbox=x=0:y={y}:w={TARGET_W}:h={h}:color=black@{a:.2f}:t=fill:"
            f"enable='between(t,{start_t:.3f},{end_t:.3f})'"
        )
    return ",".join(bands)


def assemble(
    section_videos: list[Path],
    voice_wav: Path,
    captions_ass: Path,
    music_path: Path | None,
    out_path: Path,
    work_dir: Path,
    voice_pad_seconds: float,
    outro_overlay_start: float,
    outro_overlay_end: float,
) -> None:
    """Final pass: concat section videos, draw the bottom gradient during the
    outro window, burn captions, mix voice + optional looped/faded music."""
    concat = _concat_videos(section_videos, work_dir)
    total_dur = _probe_duration(concat)
    fade_start = max(0.0, total_dur - FADE_OUT_SECONDS)
    ass_basename = captions_ass.name  # captions.ass lives in work_dir; cwd=work_dir below

    # Only emit the bottom-gradient drawbox chain when there's an outro overlay
    # window to enable it during. Empty window → skip the gradient entirely.
    if outro_overlay_end > outro_overlay_start:
        video_chain_prefix = _gradient_filter(outro_overlay_start, outro_overlay_end) + ","
    else:
        video_chain_prefix = ""

    inputs: list[str] = ["-i", str(concat.resolve()), "-i", str(voice_wav.resolve())]
    if music_path is not None:
        inputs += ["-stream_loop", "-1", "-i", str(music_path.resolve())]

    voice_chain = (
        f"[1:a]apad=pad_dur={voice_pad_seconds:.3f}[va]"
        if voice_pad_seconds > 0
        else "[1:a]anull[va]"
    )

    if music_path is not None:
        filter_complex = (
            f"[0:v]{video_chain_prefix}subtitles={ass_basename}[vout];"
            f"{voice_chain};"
            f"[2:a]volume={MUSIC_VOLUME}[ma];"
            f"[va][ma]amix=inputs=2:duration=first:dropout_transition=0[mixed];"
            f"[mixed]afade=t=out:st={fade_start:.3f}:d={FADE_OUT_SECONDS:.3f}[aout]"
        )
    else:
        filter_complex = (
            f"[0:v]{video_chain_prefix}subtitles={ass_basename}[vout];"
            f"{voice_chain};"
            f"[va]afade=t=out:st={fade_start:.3f}:d={FADE_OUT_SECONDS:.3f}[aout]"
        )

    cmd = [
        FFMPEG, "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart",
        str(out_path.resolve()),
    ]
    _run(cmd, cwd=str(work_dir.resolve()))
