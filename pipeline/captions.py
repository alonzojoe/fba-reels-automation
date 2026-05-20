"""Word-by-word ASS captions plus an in-footage outro overlay.

All text (body captions + outro) uses a single `text_color` (default #00FF66).
Each word event is a (shadow, main) pair giving a real Gaussian-blurred drop
shadow under the colored text — libass doesn't expose a one-shot blurred shadow,
so we layer a `\\blur6` black copy under the main word.

The outro sits in the lower-third (y=1500) so a bottom drawbox gradient in
assemble.py can darken the area behind it without affecting body captions.
"""
from __future__ import annotations

# Frame geometry
FRAME_W = 1080
FRAME_H = 1920

# Body caption positioning
CAPTION_X = FRAME_W // 2          # 540 (horizontal center)
CAPTION_Y = int(FRAME_H * 0.65)   # 1248 (65% from top)
SHADOW_DX = 4
SHADOW_DY = 4
SHADOW_BLUR = 6
POPIN_MS = 80

# Outro positioning (lower-third — classic Reels CTA placement)
OUTRO_DURATION = 2.5
OUTRO_FONTSIZE = 140
OUTRO_FADE_IN_MS = 300
OUTRO_X = FRAME_W // 2
OUTRO_Y = 1500                    # ~78% from top
DEFAULT_OUTRO_TEXT = "LIKE AND FOLLOW|FOR MORE"

# Default brand text color: vibrant green, on-brand for health/wellness niche
DEFAULT_TEXT_COLOR = "#00FF66"

BLACK_INLINE = "&H000000&"


def hex_to_ass_inline(hex_color: str) -> str:
    """'#RRGGBB' → ASS '&HBBGGRR&' inline override."""
    h = hex_color.lstrip("#")
    if len(h) != 6 or not all(c in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"Expected #RRGGBB, got {hex_color!r}")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{b}{g}{r}&".upper()


def hex_to_ass_style(hex_color: str) -> str:
    """'#RRGGBB' → ASS style-row '&H00BBGGRR' (alpha 00 = opaque)."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def _style_row(fontname: str, primary_color: str) -> str:
    primary = hex_to_ass_style(primary_color)
    # Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,
    #         OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,
    #         ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,
    #         Alignment, MarginL, MarginR, MarginV, Encoding
    return (
        f"Style: Default,{fontname},95,"
        f"{primary},{primary},&H00000000,&H00000000,"
        f"1,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1"
    )


def _ass_header(fontname: str, primary_color: str) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {FRAME_W}\n"
        f"PlayResY: {FRAME_H}\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{_style_row(fontname, primary_color)}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _ts(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
    )


def _word_events(word: str, start: float, end: float) -> list[str]:
    """(shadow, main) Dialogue pair for one word. Color comes from the style row."""
    text = _escape(word)
    shadow_overrides = (
        f"{{\\blur{SHADOW_BLUR}"
        f"\\1c{BLACK_INLINE}\\3c{BLACK_INLINE}\\bord0"
        f"\\pos({CAPTION_X + SHADOW_DX},{CAPTION_Y + SHADOW_DY})}}"
    )
    main_overrides = (
        f"{{\\pos({CAPTION_X},{CAPTION_Y})"
        f"\\fscx80\\fscy80\\t(0,{POPIN_MS},\\fscx100\\fscy100)}}"
    )
    ts_start, ts_end = _ts(start), _ts(end)
    shadow = f"Dialogue: 0,{ts_start},{ts_end},Default,,0,0,0,,{shadow_overrides}{text}"
    main = f"Dialogue: 1,{ts_start},{ts_end},Default,,0,0,0,,{main_overrides}{text}"
    return [shadow, main]


def _outro_events(outro_text: str, start: float, end: float) -> list[str]:
    """Two-line outro at the lower-third, with fade-in. Same color as captions."""
    lines = [_escape(line.strip()) for line in outro_text.split("|") if line.strip()]
    ass_text = r"\N".join(lines)

    ts_start, ts_end = _ts(start), _ts(end)
    shadow_overrides = (
        f"{{\\blur{SHADOW_BLUR}"
        f"\\1c{BLACK_INLINE}\\3c{BLACK_INLINE}\\bord0"
        f"\\pos({OUTRO_X + SHADOW_DX},{OUTRO_Y + SHADOW_DY})"
        f"\\fs{OUTRO_FONTSIZE}\\fad({OUTRO_FADE_IN_MS},0)}}"
    )
    main_overrides = (
        f"{{\\pos({OUTRO_X},{OUTRO_Y})"
        f"\\fs{OUTRO_FONTSIZE}\\fad({OUTRO_FADE_IN_MS},0)}}"
    )
    shadow = f"Dialogue: 0,{ts_start},{ts_end},Default,,0,0,0,,{shadow_overrides}{ass_text}"
    main = f"Dialogue: 1,{ts_start},{ts_end},Default,,0,0,0,,{main_overrides}{ass_text}"
    return [shadow, main]


def build_ass(
    words: list[dict],
    total_duration: float,
    outro_text: str | None = DEFAULT_OUTRO_TEXT,
    outro_duration: float = OUTRO_DURATION,
    text_color: str = DEFAULT_TEXT_COLOR,
    fontname: str = "Arial Black",
) -> str:
    """Build the ASS subtitle file.

    All text uses `text_color` (default green #00FF66). The outro is appended
    starting at total_duration and lasts outro_duration; it sits at the
    lower-third position so a drawbox gradient in assemble.py can darken
    behind it.
    """
    out: list[str] = [_ass_header(fontname, text_color)]
    n = len(words)
    for i, w in enumerate(words):
        start = w["start"]
        end = words[i + 1]["start"] if i < n - 1 else w["end"] + 0.3
        end = min(end, total_duration)
        if end <= start:
            continue
        out.extend(_word_events(w["word"], start, end))

    if outro_text:
        out.extend(_outro_events(outro_text, total_duration, total_duration + outro_duration))

    return "\n".join(out) + "\n"
