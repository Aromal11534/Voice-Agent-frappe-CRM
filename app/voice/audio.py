"""
Audio processing utilities.

Handles resampling between Exotel's 8kHz telephony format
and Sarvam's preferred 16kHz format.

Also handles chunking audio into Exotel-compatible sizes
(multiples of 320 bytes).
"""

from __future__ import annotations

import audioop
import logging
import struct

logger = logging.getLogger(__name__)


class StreamingResampler:
    """Preserve rate-conversion state across adjacent telephony frames."""

    def __init__(self, input_rate: int = 8000, output_rate: int = 16000) -> None:
        self.input_rate = input_rate
        self.output_rate = output_rate
        self._state = None

    def process(self, pcm_bytes: bytes) -> bytes:
        if not pcm_bytes:
            return b""
        converted, self._state = audioop.ratecv(
            pcm_bytes, 2, 1, self.input_rate, self.output_rate, self._state
        )
        return converted


# ── Resampling ──────────────────────────────────────────────


def upsample_8k_to_16k(pcm_8k: bytes) -> bytes:
    """
    Upsample 8kHz 16-bit mono PCM to 16kHz.

    Used when forwarding Exotel audio to Sarvam STT.

    Args:
        pcm_8k: Raw PCM bytes at 8kHz, 16-bit signed, mono.

    Returns:
        Raw PCM bytes at 16kHz, 16-bit signed, mono.
    """
    if not pcm_8k:
        return b""

    try:
        # audioop.ratecv(fragment, width, nchannels, inrate, outrate, state)
        # width=2 for 16-bit, nchannels=1 for mono
        resampled, _state = audioop.ratecv(
            pcm_8k,
            2,      # sample width in bytes (16-bit = 2)
            1,      # mono
            8000,   # input sample rate
            16000,  # output sample rate
            None,   # state (None for first call)
        )
        return resampled
    except Exception:
        logger.exception("AUDIO  Failed to upsample 8k→16k")
        return pcm_8k  # Return original as fallback


def downsample_16k_to_8k(pcm_16k: bytes) -> bytes:
    """
    Downsample 16kHz 16-bit mono PCM to 8kHz.

    Used when forwarding Sarvam TTS audio back to Exotel.

    Args:
        pcm_16k: Raw PCM bytes at 16kHz, 16-bit signed, mono.

    Returns:
        Raw PCM bytes at 8kHz, 16-bit signed, mono.
    """
    if not pcm_16k:
        return b""

    try:
        resampled, _state = audioop.ratecv(
            pcm_16k,
            2,      # 16-bit
            1,      # mono
            16000,  # input
            8000,   # output
            None,
        )
        return resampled
    except Exception:
        logger.exception("AUDIO  Failed to downsample 16k→8k")
        return pcm_16k


# ── Chunking ────────────────────────────────────────────────


def chunk_audio(
    audio_bytes: bytes,
    chunk_size: int = 320,
    padding_byte: bytes = b"\xff",
) -> list[bytes]:
    """
    Split μ-law audio bytes into chunks suitable for Exotel streaming.

    Exotel requires audio chunks to be multiples of 320 bytes.
    Default chunk_size=320 gives 40ms chunks at 8kHz/8-bit μ-law.

    Args:
        audio_bytes: Raw PCM audio bytes.
        chunk_size: Size of each chunk in bytes (must be multiple of 320).

    Returns:
        List of byte chunks, each exactly chunk_size bytes
        (last chunk padded with silence if needed).
    """
    if not audio_bytes:
        return []

    chunks = []
    for i in range(0, len(audio_bytes), chunk_size):
        chunk = audio_bytes[i: i + chunk_size]

        # Pad last chunk with silence if undersized
        if len(chunk) < chunk_size:
            chunk = chunk + padding_byte * (chunk_size - len(chunk))

        chunks.append(chunk)

    return chunks


# ── PCM Linear16 ↔ mulaw conversion ────────────────────────


def linear16_to_mulaw(pcm_linear16: bytes) -> bytes:
    """Convert 16-bit linear PCM to 8-bit mu-law."""
    try:
        return audioop.lin2ulaw(pcm_linear16, 2)
    except Exception:
        logger.exception("AUDIO  Failed to convert linear16→mulaw")
        return pcm_linear16


def mulaw_to_linear16(pcm_mulaw: bytes) -> bytes:
    """Convert 8-bit mu-law to 16-bit linear PCM."""
    try:
        return audioop.ulaw2lin(pcm_mulaw, 2)
    except Exception:
        logger.exception("AUDIO  Failed to convert mulaw→linear16")
        return pcm_mulaw


# ── Silence generation ──────────────────────────────────────


def generate_silence(duration_ms: int, sample_rate: int = 8000) -> bytes:
    """
    Generate silent PCM audio of the specified duration.

    Args:
        duration_ms: Duration in milliseconds.
        sample_rate: Sample rate in Hz.

    Returns:
        Raw 16-bit mono PCM silence bytes.
    """
    num_samples = int(sample_rate * duration_ms / 1000)
    return struct.pack(f"<{num_samples}h", *([0] * num_samples))
