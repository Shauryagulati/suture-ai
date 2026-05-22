"""WhisperSTT wrapper tests.

Fast (non-slow) tests cover the wrapper's PCM→float32 conversion,
empty-input handling, and lazy-load behavior with a mocked
WhisperModel. Slow tests (gated under `pytest -m slow`, runnable via
`make eval-voice`) exercise actual model download + inference.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.services.voice import stt as stt_module
from app.services.voice.stt import WhisperSTT

pytestmark = pytest.mark.asyncio


# ── Fast tests (no model download) ────────────────────────────────────


async def test_transcribe_empty_bytes_returns_empty_string() -> None:
    s = WhisperSTT()
    assert await s.transcribe_pcm16(b"") == ""


async def test_transcribe_empty_array_returns_empty_string() -> None:
    s = WhisperSTT()
    assert await s.transcribe(np.array([], dtype=np.float32)) == ""


async def test_pcm16_to_float32_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wrapper converts int16 PCM bytes to float32 in [-1, 1] before inference."""
    s = WhisperSTT()
    captured: dict[str, Any] = {}

    def fake_transcribe_sync(self_: WhisperSTT, audio: np.ndarray) -> str:
        captured["audio"] = audio
        return "ok"

    monkeypatch.setattr(WhisperSTT, "_transcribe_sync", fake_transcribe_sync)
    pcm = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16).tobytes()
    text = await s.transcribe_pcm16(pcm)

    assert text == "ok"
    audio = captured["audio"]
    assert audio.dtype == np.float32
    assert audio.shape == (5,)
    # 16384/32768 ≈ 0.5
    assert audio[0] == pytest.approx(0.0)
    assert audio[1] == pytest.approx(0.5, abs=1e-3)
    assert audio[2] == pytest.approx(-0.5, abs=1e-3)


async def test_concurrent_calls_share_loaded_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lazy-load fires once across concurrent transcribes — no duplicate loads."""
    load_count = 0

    class FakeModel:
        def transcribe(self, *_args: Any, **_kwargs: Any) -> tuple[list[Any], dict[str, Any]]:
            return ([], {})

    def fake_init(*_a: Any, **_kw: Any) -> FakeModel:
        nonlocal load_count
        load_count += 1
        return FakeModel()

    monkeypatch.setattr(stt_module, "WhisperModel", fake_init)
    s = WhisperSTT()
    await asyncio.gather(
        s.transcribe(np.ones(16000, dtype=np.float32)),
        s.transcribe(np.ones(16000, dtype=np.float32)),
        s.transcribe(np.ones(16000, dtype=np.float32)),
    )
    assert load_count == 1


# ── Slow tests (real model + real audio) ──────────────────────────────


@pytest.fixture(scope="session")
def hello_wav() -> Path:
    """Render 'Hello there, please book me an appointment.' to a 16kHz mono WAV.

    Uses macOS `say` + ffmpeg; skips the test if neither is on PATH.
    Cached in a tmpdir for the pytest session.
    """
    if shutil.which("say") is None or shutil.which("ffmpeg") is None:
        pytest.skip("requires macOS `say` and `ffmpeg` to render the test clip")
    out_dir = Path(tempfile.mkdtemp(prefix="suture-stt-fixture-"))
    aiff = out_dir / "hello.aiff"
    wav = out_dir / "hello.wav"
    subprocess.run(
        ["say", "-o", str(aiff), "Hello there, please book me an appointment."],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(wav)],
        check=True,
        capture_output=True,
    )
    return wav


def _read_wav_pcm16(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000
        assert w.getsampwidth() == 2
        return w.readframes(w.getnframes())


@pytest.mark.slow
async def test_transcribe_silence_returns_empty_or_short() -> None:
    """1s of silence should not produce hallucinated transcripts."""
    s = WhisperSTT()
    silence = np.zeros(16000, dtype=np.int16).tobytes()
    text = await s.transcribe_pcm16(silence)
    assert len(text) <= 10, f"silence transcribed to suspiciously long text: {text!r}"


@pytest.mark.slow
async def test_transcribe_hello_clip(hello_wav: Path) -> None:
    """End-to-end: real Whisper on a synthesized speech clip."""
    s = WhisperSTT()
    pcm = _read_wav_pcm16(hello_wav)
    text = await s.transcribe_pcm16(pcm)
    lower = text.lower()
    assert any(word in lower for word in ("hello", "appointment", "book", "there")), (
        f"transcript missed every expected word: {text!r}"
    )
