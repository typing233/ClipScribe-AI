import subprocess
from pathlib import Path

from backend.services.tts_service import AudioSegment


def compose_video(
    video_path: Path,
    audio_segments: list[AudioSegment],
    subtitle_path: Path,
    output_dir: Path,
) -> str:
    """Compose final video: trim clips, mix audio, overlay subtitles."""
    total_audio_duration = sum(seg.duration for seg in audio_segments)
    concat_audio_path = output_dir / "full_narration.mp3"
    _concat_audio_files(audio_segments, concat_audio_path)

    trimmed_video_path = output_dir / "trimmed.mp4"
    _trim_video(video_path, total_audio_duration, trimmed_video_path)

    output_filename = "output.mp4"
    output_path = output_dir / output_filename

    has_audio = _has_audio_stream(trimmed_video_path)
    subtitle_path_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")

    if has_audio:
        audio_filter = (
            f"[0:a]volume=0.15[bg];"
            f"[1:a]volume=1.0[narr];"
            f"[bg][narr]amix=inputs=2:duration=longest[aout]"
        )
    else:
        audio_filter = "[1:a]volume=1.0[aout]"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(trimmed_video_path),
        "-i", str(concat_audio_path),
        "-filter_complex",
        (
            f"{audio_filter};"
            f"[0:v]subtitles='{subtitle_path_escaped}':force_style="
            f"'FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"Outline=2,MarginV=30'[vout]"
        ),
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        fallback_path = _compose_without_subtitles(
            trimmed_video_path, concat_audio_path, has_audio, output_dir
        )
        if fallback_path:
            return fallback_path.name
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")

    return output_filename


def _compose_without_subtitles(
    video_path: Path, audio_path: Path, has_audio: bool, output_dir: Path
) -> Path | None:
    """Fallback: compose without subtitle filter if subtitles filter fails."""
    output_path = output_dir / "output.mp4"

    if has_audio:
        audio_filter = "[0:a]volume=0.15[bg];[1:a]volume=1.0[narr];[bg][narr]amix=inputs=2:duration=longest[aout]"
    else:
        audio_filter = "[1:a]volume=1.0[aout]"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg fallback also failed: {result.stderr[-500:]}")
    return output_path


def _has_audio_stream(video_path: Path) -> bool:
    """Check if video file has an audio stream."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    return "audio" in result.stdout


def _concat_audio_files(audio_segments: list[AudioSegment], output_path: Path):
    """Concatenate all TTS audio files into one."""
    list_file = output_path.parent / "audio_list.txt"
    with open(list_file, "w") as f:
        for seg in audio_segments:
            f.write(f"file '{seg.audio_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Audio concat failed: {result.stderr[-300:]}")


def _trim_video(video_path: Path, target_duration: float, output_path: Path):
    """Trim or loop video to match audio duration."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-t", str(target_duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Video trim failed: {result.stderr[-300:]}")
