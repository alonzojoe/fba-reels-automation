"""Load and validate a reel script from a JSON file.

Schema (current): every section has `text` and `queries` (list of strings).
Back-compat: single-string `query` or `search_query` is accepted and normalized
to `queries: [<value>]`.

Punctuation validation: text fields are checked for malformed patterns that
break TTS prosody (comma splice with stranded `?`, missing terminal mark,
run-on sentences). Hard rejection for the first; warnings for the others.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_LEGACY_QUERY_KEYS = ("queries", "search_query", "query")

# Punctuation validation
_TERMINAL_PUNCT = (".", "!", "?", "—")
_RUNON_WORD_THRESHOLD = 25
# A sentence terminator for counting purposes (em-dash is mid-sentence)
_SENTENCE_SPLIT_RE = re.compile(r"(?:\.{2,}|[.!?])\s+")
# Inline bracket tags (legacy [soft]/[excited] cues) — stripped before validation
# so they don't get counted as text. Kokoro doesn't honor them and the script
# generator no longer emits them; this regex is just defensive cleanup.
_INLINE_CUE_RE = re.compile(r"\[[^\]]*\]\s*")


def load_script(path: Path) -> dict:
    """Read, validate, and normalize a script JSON file. Returns the parsed dict
    with every section guaranteed to have a non-empty `queries` list (and the
    legacy `search_query`/`query` aliases removed)."""
    if not path.exists():
        raise SystemExit(f"ERROR: script file not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR: script file is not valid JSON ({path}): {e}")

    _validate(data, path)
    _normalize(data)
    return data


def _fail(path: Path, msg: str) -> None:
    raise SystemExit(f"ERROR: invalid script ({path}): {msg}")


def _check_punctuation(path: Path, label: str, text: str) -> None:
    """Enforce the punctuation rules from prompts/script-generation.md.

    Hard rejects (raises SystemExit):
      - comma-splice with a stranded final `?`

    Warnings (print to stderr, don't reject):
      - missing terminal punctuation
      - individual sentences over RUNON_WORD_THRESHOLD words

    Sentence count is NOT capped — the conversational style explicitly uses
    many short fragments per section (e.g. `"Lemon water. First thing. Trust me."`).
    The run-on warning catches over-long individual sentences instead.
    """
    stripped = text.strip()
    # Strip legacy bracket tags (no longer used by the script generator) so they
    # don't get counted as spoken text.
    text_for_count = _INLINE_CUE_RE.sub("", stripped).strip()

    # Hard reject: comma + final `?` strongly suggests stranded question mark
    # ("Wake up with a sore throat, skip the pharmacy?").
    if "," in text_for_count and text_for_count.endswith("?"):
        _fail(
            path,
            f"{label}.text looks like a comma splice with a stranded '?' — "
            f'rewrite as two sentences. Got: {stripped!r}',
        )

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text_for_count) if s.strip()]

    # Warning: no terminal punctuation at all
    if not text_for_count.endswith(_TERMINAL_PUNCT):
        print(
            f"[script] WARN: {label}.text has no terminal punctuation; TTS prosody "
            f"may be flat. Got: {stripped!r}",
            file=sys.stderr,
        )

    # Warning: any individual sentence over the run-on threshold
    for sent in sentences:
        wc = len(sent.split())
        if wc > _RUNON_WORD_THRESHOLD:
            print(
                f"[script] WARN: {label}.text contains a {wc}-word sentence "
                f"(over {_RUNON_WORD_THRESHOLD}-word run-on threshold); "
                f"consider splitting. Sentence: {sent.strip()!r}",
                file=sys.stderr,
            )


def _validate_section(path: Path, label: str, sec: object) -> None:
    if not isinstance(sec, dict):
        _fail(path, f"{label!r} must be an object")
    if "text" not in sec or not isinstance(sec["text"], str) or not sec["text"].strip():
        _fail(path, f"{label}.text must be a non-empty string")

    _check_punctuation(path, label, sec["text"])

    # Optional pronunciation_hints: {word: phonetic_spelling}
    if "pronunciation_hints" in sec:
        hints = sec["pronunciation_hints"]
        if not isinstance(hints, dict):
            _fail(path, f"{label}.pronunciation_hints must be an object/dict")
        for k, v in hints.items():
            if not isinstance(k, str) or not k.strip():
                _fail(path, f"{label}.pronunciation_hints has an empty/non-string key")
            if not isinstance(v, str) or not v.strip():
                _fail(
                    path,
                    f"{label}.pronunciation_hints[{k!r}] must be a non-empty string",
                )

    # Find queries via any supported key
    qs = None
    for k in _LEGACY_QUERY_KEYS:
        if k in sec:
            qs = sec[k]
            break
    if qs is None:
        _fail(path, f"{label} must have one of: {', '.join(_LEGACY_QUERY_KEYS)}")

    if isinstance(qs, str):
        if not qs.strip():
            _fail(path, f"{label} query string is empty")
    elif isinstance(qs, list):
        if not qs:
            _fail(path, f"{label}.queries must be a non-empty list")
        for i, q in enumerate(qs):
            if not isinstance(q, str) or not q.strip():
                _fail(path, f"{label}.queries[{i}] must be a non-empty string")
    else:
        _fail(path, f"{label} queries must be a string or a list of strings")


def _validate(data: dict, path: Path) -> None:
    if not isinstance(data, dict):
        _fail(path, "top-level value must be an object")
    for key in ("hook", "tips", "cta"):
        if key not in data:
            _fail(path, f"missing top-level key: {key!r}")

    _validate_section(path, "hook", data["hook"])
    _validate_section(path, "cta", data["cta"])

    tips = data["tips"]
    if not isinstance(tips, list):
        _fail(path, "'tips' must be an array")
    if len(tips) != 3:
        _fail(path, f"'tips' must contain exactly 3 items, got {len(tips)}")
    for i, tip in enumerate(tips):
        _validate_section(path, f"tips[{i}]", tip)


def _normalize_section(sec: dict) -> None:
    """Coerce {query|search_query} → queries list; remove the legacy keys."""
    if "queries" in sec and isinstance(sec["queries"], list):
        # Already in canonical form. Strip legacy keys if present alongside.
        for k in ("search_query", "query"):
            sec.pop(k, None)
        return

    for k in _LEGACY_QUERY_KEYS:
        if k in sec:
            v = sec.pop(k)
            sec["queries"] = [v] if isinstance(v, str) else list(v)
            break

    # Drop any remaining legacy keys
    for k in ("search_query", "query"):
        sec.pop(k, None)


def _normalize(data: dict) -> None:
    _normalize_section(data["hook"])
    _normalize_section(data["cta"])
    for tip in data["tips"]:
        _normalize_section(tip)
