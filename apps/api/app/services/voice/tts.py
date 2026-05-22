"""Text-to-speech wrapper around Piper.

Models lazily download from huggingface.co/rhasspy/piper-voices into
`settings.voice_model_cache_dir / "piper"` on first call. Default voice
is `en_US-amy-medium` (~60MB, 22050Hz int16 PCM).

The wrapper owns one `PiperVoice` per instance. Hold one per worker
process; ONNX model load is expensive.

Inference is synchronous ONNX work, so `synthesize` and `stream`
offload to a thread via `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from piper import PiperVoice

from app.config import get_settings

_HF_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _voice_url_parts(voice_name: str) -> tuple[str, str, str, str]:
    """Decompose `en_US-amy-medium` → ('en', 'en_US', 'amy', 'medium')."""
    locale, speaker, quality = voice_name.split("-")
    lang = locale.split("_")[0]
    return lang, locale, speaker, quality


class PiperTTS:
    """Local Piper synthesizer. Lazy-loads the voice model on first call."""

    def __init__(
        self,
        *,
        voice: str | None = None,
        download_dir: Path | None = None,
    ) -> None:
        settings = get_settings()
        self._voice_name = voice or settings.piper_voice
        self._download_dir = download_dir or (settings.voice_model_cache_dir / "piper")
        self._voice: PiperVoice | None = None
        self._load_lock = threading.Lock()

    @property
    def sample_rate(self) -> int:
        """Native sample rate of the loaded voice (22050 for *-medium)."""
        if self._voice is None:
            return 22050
        return int(self._voice.config.sample_rate)

    def _ensure_model_files(self) -> tuple[Path, Path]:
        onnx = self._download_dir / f"{self._voice_name}.onnx"
        cfg = self._download_dir / f"{self._voice_name}.onnx.json"
        if onnx.exists() and cfg.exists():
            return onnx, cfg

        self._download_dir.mkdir(parents=True, exist_ok=True)
        lang, locale, speaker, quality = _voice_url_parts(self._voice_name)
        base = f"{_HF_BASE_URL}/{lang}/{locale}/{speaker}/{quality}"
        for src_url, dst in [
            (f"{base}/{self._voice_name}.onnx", onnx),
            (f"{base}/{self._voice_name}.onnx.json", cfg),
        ]:
            if dst.exists():
                continue
            with httpx.stream("GET", src_url, follow_redirects=True, timeout=300.0) as r:
                r.raise_for_status()
                with open(dst, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=1 << 16):
                        f.write(chunk)
        return onnx, cfg

    def _load(self) -> PiperVoice:
        if self._voice is not None:
            return self._voice
        with self._load_lock:
            if self._voice is None:
                onnx, cfg = self._ensure_model_files()
                self._voice = PiperVoice.load(onnx, config_path=cfg)
        return self._voice

    async def synthesize(self, text: str) -> bytes:
        """Synthesize `text` to a single PCM int16 bytes payload."""
        chunks: list[bytes] = []
        async for chunk in self.stream(text):
            chunks.append(chunk)
        return b"".join(chunks)

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield PCM int16 chunks as Piper produces them.

        Each chunk is a complete int16 PCM segment at `self.sample_rate`.
        Empty / whitespace-only text yields nothing.
        """
        if not text.strip():
            return
        voice = await asyncio.to_thread(self._load)
        chunks = await asyncio.to_thread(self._synthesize_all, voice, text)
        for chunk in chunks:
            yield chunk

    @staticmethod
    def _synthesize_all(voice: PiperVoice, text: str) -> list[bytes]:
        return [bytes(chunk.audio_int16_bytes) for chunk in voice.synthesize(text)]
