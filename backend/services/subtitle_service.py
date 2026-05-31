from pathlib import Path

import pysrt

from backend.services.tts_service import AudioSegment


def generate_subtitles(audio_segments: list[AudioSegment], output_dir: Path) -> Path:
    """Generate SRT subtitle file aligned with audio timing."""
    subs = pysrt.SubRipFile()
    current_time = 0.0

    for seg in audio_segments:
        start = current_time
        end = current_time + seg.duration

        sub = pysrt.SubRipItem(
            index=seg.index + 1,
            start=pysrt.SubRipTime(seconds=start),
            end=pysrt.SubRipTime(seconds=end),
            text=seg.text,
        )
        subs.append(sub)
        current_time = end

    subtitle_path = output_dir / "subtitles.srt"
    subs.save(str(subtitle_path), encoding="utf-8")
    return subtitle_path
