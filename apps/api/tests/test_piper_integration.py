"""PiperTTS wrapper tests.

Fast tests (no model download) cover the URL decomposition, empty-input
handling, lazy-load behavior, and download dispatch via a mocked
PiperVoice + httpx transport. Slow tests (gated under `pytest -m slow`)
exercise the real download + synthesis pipeline.
"""

from __future__ import annotations

import asyncio
import struct
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.services.voice import tts as tts_module
from app.services.voice.tts import PiperTTS, _voice_url_parts

# ── Fast tests ────────────────────────────────────────────────────────


def test_voice_url_parts_amy_medium() -> None:
    assert _voice_url_parts("en_US-amy-medium") == ("en", "en_US", "amy", "medium")


def test_voice_url_parts_other_locale() -> None:
    assert _voice_url_parts("de_DE-thorsten-low") == ("de", "de_DE", "thorsten", "low")


@pytest.mark.asyncio
async def test_stream_empty_text_yields_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    t = PiperTTS()
    # _load must not be called for whitespace-only input.
    monkeypatch.setattr(
        PiperTTS, "_load", lambda self: pytest.fail("_load must not run for empty text")
    )
    chunks = [c async for c in t.stream("   ")]
    assert chunks == []
    assert await t.synthesize("") == b""


@pytest.mark.asyncio
async def test_synthesize_concatenates_stream_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """synthesize() = b''.join(stream chunks)."""

    class FakeVoice:
        config = type("Cfg", (), {"sample_rate": 22050})()

    monkeypatch.setattr(PiperTTS, "_load", lambda self: FakeVoice())
    monkeypatch.setattr(
        PiperTTS,
        "_synthesize_all",
        staticmethod(lambda voice, text: [b"\x01\x02", b"\x03\x04", b"\x05\x06"]),
    )
    t = PiperTTS()
    assert await t.synthesize("hi") == b"\x01\x02\x03\x04\x05\x06"


@pytest.mark.asyncio
async def test_concurrent_streams_share_loaded_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple concurrent stream() calls must trigger PiperVoice.load exactly once."""
    load_count = 0

    class FakeVoice:
        config = type("Cfg", (), {"sample_rate": 22050})()

    def fake_load(model_path: Any, *, config_path: Any = None, **_kw: Any) -> FakeVoice:
        nonlocal load_count
        load_count += 1
        return FakeVoice()

    monkeypatch.setattr(PiperTTS, "_ensure_model_files", lambda self: (Path("x"), Path("y")))
    fake_pv = type("FakePV", (), {"load": staticmethod(fake_load)})
    monkeypatch.setattr(tts_module, "PiperVoice", fake_pv)
    monkeypatch.setattr(
        PiperTTS, "_synthesize_all", staticmethod(lambda voice, text: [b"chunk"])
    )

    t = PiperTTS()
    await asyncio.gather(
        t.synthesize("a"),
        t.synthesize("b"),
        t.synthesize("c"),
    )
    assert load_count == 1


def test_ensure_model_files_skips_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If both .onnx + .onnx.json exist, no HTTP request is made."""
    (tmp_path / "en_US-amy-medium.onnx").write_bytes(b"fake-onnx")
    (tmp_path / "en_US-amy-medium.onnx.json").write_text("{}")

    def boom(*_a: Any, **_kw: Any) -> Any:
        pytest.fail("httpx.stream must not be called when files exist")

    monkeypatch.setattr(httpx, "stream", boom)
    t = PiperTTS(download_dir=tmp_path)
    onnx, cfg = t._ensure_model_files()
    assert onnx.read_bytes() == b"fake-onnx"
    assert cfg.read_text() == "{}"


def test_ensure_model_files_downloads_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing files trigger one HTTP GET per file with the right URL pattern."""
    seen_urls: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self, chunk_size: int = 0) -> Any:
            yield b"fake-body"

    class FakeContextManager:
        def __init__(self, url: str) -> None:
            seen_urls.append(url)
            self.resp = FakeResponse()

        def __enter__(self) -> FakeResponse:
            return self.resp

        def __exit__(self, *_args: Any) -> None:
            pass

    def fake_stream(method: str, url: str, **_kw: Any) -> FakeContextManager:
        return FakeContextManager(url)

    monkeypatch.setattr(httpx, "stream", fake_stream)
    t = PiperTTS(download_dir=tmp_path)
    onnx, cfg = t._ensure_model_files()

    assert onnx.read_bytes() == b"fake-body"
    assert cfg.read_bytes() == b"fake-body"
    assert any("en/en_US/amy/medium/en_US-amy-medium.onnx" in u for u in seen_urls)
    assert any("en/en_US/amy/medium/en_US-amy-medium.onnx.json" in u for u in seen_urls)


# ── Slow tests (real download + synthesis) ────────────────────────────


@pytest.mark.slow
@pytest.mark.asyncio
async def test_synthesize_returns_pcm() -> None:
    t = PiperTTS()
    audio = await t.synthesize("Hello, this is Suture calling.")
    # 22050Hz int16 mono — even a 2-second clip is >>10KB.
    assert len(audio) > 10_000, f"unexpectedly short audio: {len(audio)} bytes"
    # int16 = 2-byte samples; length must be even.
    assert len(audio) % 2 == 0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_synthesize_empty_returns_empty() -> None:
    """Whitespace yields zero bytes even after the voice is loaded."""
    t = PiperTTS()
    await t.synthesize("warmup")  # trigger lazy load
    assert await t.synthesize("") == b""
    assert await t.synthesize("   \n  ") == b""


@pytest.mark.slow
@pytest.mark.asyncio
async def test_stream_yields_multiple_chunks_for_long_text() -> None:
    """Long input produces multiple AudioChunks (per Piper's sentence segmenter)."""
    t = PiperTTS()
    chunks = [
        c
        async for c in t.stream(
            "Hello. This is Suture calling about your appointment. "
            "We have Tuesday at three, or Wednesday at ten. "
            "Which works better for you?"
        )
    ]
    assert len(chunks) >= 2
    # First chunk should be valid PCM int16 (even byte count).
    assert all(len(c) % 2 == 0 for c in chunks)
    # Decoding a couple of samples should give reasonable int16 values.
    first_samples = struct.unpack_from(f"<{min(8, len(chunks[0]) // 2)}h", chunks[0])
    assert all(-32768 <= v <= 32767 for v in first_samples)
