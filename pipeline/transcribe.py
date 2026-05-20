"""Word-level transcription with faster-whisper."""
from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel("base", device="cpu", compute_type="int8")
    return _model


def transcribe(wav_path: Path) -> list[dict]:
    """Return per-word timestamps: [{'start': float, 'end': float, 'word': str}, ...]."""
    model = _get_model()
    segments, _info = model.transcribe(
        str(wav_path),
        word_timestamps=True,
        language="en",
    )

    words: list[dict] = []
    for seg in segments:
        if seg.words is None:
            continue
        for w in seg.words:
            cleaned = w.word.strip()
            if not cleaned:
                continue
            words.append(
                {
                    "start": float(w.start),
                    "end": float(w.end),
                    "word": cleaned,
                }
            )

    if not words:
        raise RuntimeError("faster-whisper produced 0 words — TTS may have failed.")

    return words
