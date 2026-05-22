"""Karaoke-style ASS captions.

The full phrase (~5-7 words) appears on screen with every word in white;
as the voice speaks each word, that word flips to the brand color (default
green #00FF66) and stays highlighted for the rest of the phrase. When the
phrase ends, the line clears and the next phrase appears.

Rendering tricks:
- libass karaoke `\\k` tags drive the per-word color change: SecondaryColour
  (white) → PrimaryColour (green) at each word's spoken time. Already-flipped
  words stay in PrimaryColour for the remainder of the event.
- Real Gaussian-blurred drop shadow via the two-layer approach: a parallel
  Dialogue at the same time range renders the plain phrase in `\\blur6` black
  text, positioned 4px down-right behind the main layer. (libass doesn't
  expose a single-property blurred shadow.)
- 2px black outline on the main text for contrast on any footage.

Phrases are grouped from whisper word timestamps via `group_words_into_phrases`
— see that function for the break-priority rules.
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

# Default brand text color: vibrant green, on-brand for health/wellness niche
DEFAULT_TEXT_COLOR = "#00FF66"

BLACK_INLINE = "&H000000&"

# Karaoke phrase grouping + timing
KARAOKE_MAX_WORDS_PER_PHRASE = 7   # never put more than this on screen at once
KARAOKE_MIN_WORDS_FOR_WEAK_BREAK = 3  # don't trigger comma/gap breaks before this many
KARAOKE_BIG_GAP_S = 0.50           # speaker pause large enough to end a phrase
KARAOKE_LOOKAHEAD_S = 0.15         # phrase appears this long BEFORE first word
KARAOKE_TAIL_S = 0.10              # phrase holds this long AFTER last word


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
    # Karaoke caption style:
    #   PrimaryColour   = the brand color (green by default) — applied to a
    #                     word AFTER libass walks past its \\k tag
    #   SecondaryColour = white — applied to a word BEFORE its \\k tag fires
    #   OutlineColour   = black, Outline thickness 2 (heavier for contrast on
    #                     any footage)
    #   Shadow = 0 — we render the drop shadow as a separate \\blur layer
    primary = hex_to_ass_style(primary_color)
    white = hex_to_ass_style("#FFFFFF")
    # Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,
    #         OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,
    #         ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,
    #         Alignment, MarginL, MarginR, MarginV, Encoding
    return (
        f"Style: Default,{fontname},95,"
        f"{primary},{white},&H00000000,&H00000000,"
        f"1,0,0,0,100,100,0,0,1,2,0,5,0,0,0,1"
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


def group_words_into_phrases(
    words: list[dict],
    max_words: int = KARAOKE_MAX_WORDS_PER_PHRASE,
    min_words_for_weak_break: int = KARAOKE_MIN_WORDS_FOR_WEAK_BREAK,
    big_gap_s: float = KARAOKE_BIG_GAP_S,
) -> list[list[dict]]:
    """Group whisper word-timestamped output into karaoke phrases.

    Breaks the stream on (in priority order):
      - any word ending with `.` `?` `!`  (always — sentence terminator)
      - reaching `max_words` items in the current phrase
      - word ending with `,` once `min_words_for_weak_break` is reached
      - time gap to next word ≥ `big_gap_s` once `min_words_for_weak_break` reached

    Returns a list of phrases; each phrase is a list of word dicts in order.
    """
    if not words:
        return []
    phrases: list[list[dict]] = []
    current: list[dict] = []
    for i, w in enumerate(words):
        current.append(w)
        stripped = w["word"].strip()
        next_gap = (
            words[i + 1]["start"] - w["end"]
            if i + 1 < len(words) else float("inf")
        )
        strong = stripped.endswith((".", "?", "!"))
        at_max = len(current) >= max_words
        weak = (
            len(current) >= min_words_for_weak_break
            and (stripped.endswith(",") or next_gap >= big_gap_s)
        )
        if strong or at_max or weak:
            phrases.append(current)
            current = []
    if current:
        phrases.append(current)
    return phrases


def _karaoke_phrase_events(
    phrase_words: list[dict],
    prev_event_end: float,
    total_duration: float | None = None,
) -> tuple[list[str], float]:
    """Emit (shadow, main) Dialogue lines for one karaoke phrase.

    The main layer carries one `\\kXX` tag per word — libass renders the
    text in SecondaryColour (white) until each word's cumulative \\k time
    elapses, at which point that word flips to PrimaryColour (green) and
    stays there for the rest of the event. Already-spoken words remain
    highlighted.

    The shadow layer is a parallel Dialogue at the same start/end with a
    `\\blur` black render of the same phrase (no karaoke tags) offset
    SHADOW_DX/DY pixels, giving the Gaussian-blurred drop shadow effect.

    `prev_event_end` is the end time of the previous phrase's event — used
    to clamp the lookahead so consecutive phrases don't overlap visually.

    Returns (events, this_event_end).
    """
    first = phrase_words[0]
    last = phrase_words[-1]
    event_start = max(first["start"] - KARAOKE_LOOKAHEAD_S, prev_event_end + 0.01)
    event_start = max(event_start, 0.0)
    event_end = last["end"] + KARAOKE_TAIL_S
    if total_duration is not None:
        event_end = min(event_end, total_duration)
    if event_end <= event_start:
        return [], prev_event_end

    # Karaoke text — for each word, \k<wait_cs> precedes it; libass holds the
    # word in SecondaryColour for that many centiseconds, then flips it to
    # PrimaryColour (where it stays for the remainder of the event).
    karaoke_parts: list[str] = []
    prev_t = event_start
    for w in phrase_words:
        wait_cs = max(0, int(round((w["start"] - prev_t) * 100)))
        karaoke_parts.append(f"{{\\k{wait_cs}}}{_escape(w['word'])}")
        prev_t = w["start"]
    karaoke_text = " ".join(karaoke_parts)

    # Shadow: no karaoke timing, just blurred black phrase
    shadow_text = " ".join(_escape(w["word"]) for w in phrase_words)

    ts_start, ts_end = _ts(event_start), _ts(event_end)

    shadow_overrides = (
        f"{{\\blur{SHADOW_BLUR}"
        f"\\1c{BLACK_INLINE}\\2c{BLACK_INLINE}\\3c{BLACK_INLINE}\\bord0"
        f"\\pos({CAPTION_X + SHADOW_DX},{CAPTION_Y + SHADOW_DY})}}"
    )
    main_overrides = f"{{\\pos({CAPTION_X},{CAPTION_Y})}}"

    shadow = (
        f"Dialogue: 0,{ts_start},{ts_end},Default,,0,0,0,,"
        f"{shadow_overrides}{shadow_text}"
    )
    main = (
        f"Dialogue: 1,{ts_start},{ts_end},Default,,0,0,0,,"
        f"{main_overrides}{karaoke_text}"
    )
    return [shadow, main], event_end


def build_ass(
    words: list[dict],
    total_duration: float,
    outro_text: str | None = None,
    outro_duration: float = 0.0,
    text_color: str = DEFAULT_TEXT_COLOR,
    fontname: str = "Arial Black",
) -> str:
    """Build the karaoke-style ASS subtitle file.

    Each word's start time (from whisper) controls when it flips from white
    to `text_color` (default green). Phrases are grouped from the word stream
    via `group_words_into_phrases`; each phrase emits a shadow+main Dialogue
    pair.

    `outro_text` and `outro_duration` are kept in the signature for
    back-compat but no longer produce any events — the renderer dropped the
    outro overlay several iterations ago. The CTA text in the script now
    contains the follow-call directly.
    """
    out: list[str] = [_ass_header(fontname, text_color)]
    phrases = group_words_into_phrases(words)
    prev_event_end = 0.0
    for phrase in phrases:
        events, prev_event_end = _karaoke_phrase_events(
            phrase, prev_event_end, total_duration=total_duration
        )
        out.extend(events)
    return "\n".join(out) + "\n"
