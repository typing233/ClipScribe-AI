import asyncio
import subprocess
from pathlib import Path
from dataclasses import dataclass

import edge_tts

from backend.config import TTS_VOICE, TTS_RATE
from backend.models import ScriptSegment


@dataclass
class AudioSegment:
    index: int
    text: str
    audio_path: Path
    duration: float
    original_start: float
    original_end: float


async def synthesize_speech(
    segments: list[ScriptSegment], output_dir: Path
) -> list[AudioSegment]:
    """Generate TTS audio for each script segment."""
    audio_segments = []

    for i, seg in enumerate(segments):
        audio_path = output_dir / f"tts_{i:03d}.mp3"

        communicate = edge_tts.Communicate(
            text=seg.text,
            voice=TTS_VOICE,
            rate=TTS_RATE,
        )
        await communicate.save(str(audio_path))

        duration = _get_audio_duration(audio_path)

        audio_segments.append(AudioSegment(
            index=i,
            text=seg.text,
            audio_path=audio_path,
            duration=duration,
            original_start=seg.start_time,
            original_end=seg.end_time,
        ))

    return audio_segments


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio duration using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 3.0
