"""Speech-to-text wrapper around faster-whisper.

Models lazily download on first use into `settings.voice_model_cache_dir`
(default `./data/voice-models/`). The default model is `base.en` (~145MB,
roughly 0.3x realtime on a modern Mac CPU) — small enough for local dev,
large enough to give clean transcripts of conversational speech.

The wrapper owns one `WhisperModel` per instance. Hold one per worker
process; instantiating many will exhaust memory.

Inference is synchronous CTranslate2 work, so `transcribe()` and
`transcribe_pcm16()` offload to a thread via `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from app.config import get_settings


class WhisperSTT:
    """Local Whisper transcriber. Lazy-loads the model on first call."""

    def __init__(
        self,
        *,
        model: str | None = None,
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: Path | None = None,
    ) -> None:
        settings = get_settings()
        self._model_name = model or settings.whisper_model
        self._device = device
        self._compute_type = compute_type
        self._download_root = download_root or settings.voice_model_cache_dir
        self._model: WhisperModel | None = None
        self._load_lock = threading.Lock()

    def _load(self) -> WhisperModel:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:
                self._download_root.mkdir(parents=True, exist_ok=True)
                self._model = WhisperModel(
                    self._model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                    download_root=str(self._download_root),
                )
        return self._model

    async def transcribe_pcm16(self, pcm16_mono_16khz: bytes) -> str:
        """Transcribe int16 mono PCM at 16kHz. Empty bytes return ''."""
        if not pcm16_mono_16khz:
            return ""
        audio = np.frombuffer(pcm16_mono_16khz, dtype=np.int16).astype(np.float32) / 32768.0
        return await self.transcribe(audio)

    async def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe a float32 mono numpy array sampled at 16kHz.

        Returns the concatenated text of all segments. Returns '' if
        Whisper found no speech.
        """
        if audio.size == 0:
            return ""
        return await asyncio.to_thread(self._transcribe_sync, audio)

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        model = self._load()
        segments, _info = model.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments).strip()
