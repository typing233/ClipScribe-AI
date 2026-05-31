import subprocess
from pathlib import Path

from backend.services.tts_service import AudioSegment

SPEED_LOWER = 0.5
SPEED_UPPER = 2.0


def compose_video(
    video_path: Path,
    audio_segments: list[AudioSegment],
    subtitle_path: Path,
    output_dir: Path,
) -> str:
    """Compose final video by cutting per-segment clips, aligning durations, then merging."""
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    aligned_clips: list[Path] = []
    for seg in audio_segments:
        clip_path = clips_dir / f"clip_{seg.index:03d}.mp4"
        _extract_and_align_clip(
            video_path, seg.original_start, seg.original_end,
            seg.duration, clip_path,
        )
        aligned_clips.append(clip_path)

    concat_video_path = output_dir / "concat_video.mp4"
    _concat_video_clips(aligned_clips, concat_video_path)

    concat_audio_path = output_dir / "full_narration.mp3"
    _concat_audio_files(audio_segments, concat_audio_path)

    output_filename = "output.mp4"
    output_path = output_dir / output_filename

    has_audio = _has_audio_stream(concat_video_path)

    # Try subtitle methods in order; fail the task if none work
    errors: list[str] = []

    # Method 1: subtitles filter with absolute path
    err = _compose_with_subtitles_filter(
        concat_video_path, concat_audio_path, subtitle_path,
        has_audio, output_path,
    )
    if err is None:
        return output_filename
    errors.append(f"subtitles filter: {err}")

    # Method 2: burn subtitles via drawtext (no libass dependency)
    err = _compose_with_drawtext(
        concat_video_path, concat_audio_path, subtitle_path,
        has_audio, output_path,
    )
    if err is None:
        return output_filename
    errors.append(f"drawtext: {err}")

    raise RuntimeError(
        "字幕合成失败，无法生成带字幕的视频。\n" + "\n".join(errors)
    )


def _compose_with_subtitles_filter(
    video_path: Path, audio_path: Path, subtitle_path: Path,
    has_audio: bool, output_path: Path,
) -> str | None:
    """Try composing with the ASS/SRT subtitles filter. Returns None on success, error string on failure."""
    # Use absolute path and escape for ffmpeg filter syntax
    sub_abs = str(subtitle_path.resolve())
    sub_escaped = sub_abs.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    if has_audio:
        audio_filter = (
            "[0:a]volume=0.15[bg];"
            "[1:a]volume=1.0[narr];"
            "[bg][narr]amix=inputs=2:duration=longest[aout]"
        )
    else:
        audio_filter = "[1:a]volume=1.0[aout]"

    filter_complex = (
        f"{audio_filter};"
        f"[0:v]subtitles='{sub_escaped}':force_style="
        f"'FontName=sans-serif,FontSize=22,PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,Outline=2,MarginV=30'[vout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return result.stderr[-500:]
    return None


def _compose_with_drawtext(
    video_path: Path, audio_path: Path, subtitle_path: Path,
    has_audio: bool, output_path: Path,
) -> str | None:
    """Burn subtitles using drawtext filter (doesn't require libass). Returns None on success."""
    import pysrt

    subs = pysrt.open(str(subtitle_path), encoding="utf-8")
    if not subs:
        return "Empty subtitle file"

    # Build drawtext filter chain from SRT entries
    drawtext_filters = []
    for sub in subs:
        start_sec = (sub.start.hours * 3600 + sub.start.minutes * 60
                     + sub.start.seconds + sub.start.milliseconds / 1000.0)
        end_sec = (sub.end.hours * 3600 + sub.end.minutes * 60
                   + sub.end.seconds + sub.end.milliseconds / 1000.0)

        # Escape text for drawtext: single quotes and backslashes
        text = sub.text.replace("\\", "\\\\").replace("'", "'\\''")
        text = text.replace(":", "\\:").replace("%", "%%")

        dt = (
            f"drawtext=text='{text}':"
            f"fontsize=22:fontcolor=white:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=h-60:"
            f"enable='between(t,{start_sec:.3f},{end_sec:.3f})'"
        )
        drawtext_filters.append(dt)

    video_filter = ",".join(drawtext_filters)

    if has_audio:
        audio_filter = (
            "[0:a]volume=0.15[bg];"
            "[1:a]volume=1.0[narr];"
            "[bg][narr]amix=inputs=2:duration=longest[aout]"
        )
        filter_complex = f"{audio_filter};[0:v]{video_filter}[vout]"
    else:
        audio_filter = "[1:a]volume=1.0[aout]"
        filter_complex = f"{audio_filter};[0:v]{video_filter}[vout]"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return result.stderr[-500:]
    return None


def _extract_and_align_clip(
    video_path: Path, start: float, end: float,
    target_duration: float, output_path: Path,
):
    """Extract a clip from [start, end] and adjust its duration to match target_duration."""
    clip_duration = end - start
    if clip_duration <= 0:
        clip_duration = 0.1

    ratio = clip_duration / target_duration

    if SPEED_LOWER <= ratio <= SPEED_UPPER:
        _extract_with_speed(video_path, start, end, ratio, output_path)
    elif ratio < SPEED_LOWER:
        _extract_with_freeze(video_path, start, end, target_duration, output_path)
    else:
        _extract_with_speed(video_path, start, end, SPEED_UPPER, output_path)


def _extract_with_speed(
    video_path: Path, start: float, end: float,
    speed: float, output_path: Path,
):
    """Extract clip and adjust speed so video duration = (end-start)/speed."""
    setpts = f"PTS/{speed}" if speed != 1.0 else "PTS"

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-to", str(end),
        "-i", str(video_path),
        "-filter:v", f"setpts={setpts}",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"Speed-adjust clip [{start}-{end}] failed: {result.stderr[-300:]}"
        )


def _extract_with_freeze(
    video_path: Path, start: float, end: float,
    target_duration: float, output_path: Path,
):
    """Extract clip at normal speed, then freeze the last frame to reach target_duration."""
    clip_duration = end - start
    pad_duration = target_duration - clip_duration
    if pad_duration < 0:
        pad_duration = 0

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start), "-to", str(end),
        "-i", str(video_path),
        "-filter:v", f"tpad=stop_mode=clone:stop_duration={pad_duration}",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-r", "25",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        _extract_freeze_fallback(video_path, start, end, target_duration, output_path)


def _extract_freeze_fallback(
    video_path: Path, start: float, end: float,
    target_duration: float, output_path: Path,
):
    """Fallback: slow down to minimum speed to fill as much as possible."""
    speed = max(SPEED_LOWER, (end - start) / target_duration)
    _extract_with_speed(video_path, start, end, speed, output_path)


def _concat_video_clips(clips: list[Path], output_path: Path):
    """Concatenate aligned video clips into one continuous video."""
    list_file = output_path.parent / "video_list.txt"
    with open(list_file, "w") as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-r", "25",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Video concat failed: {result.stderr[-300:]}")


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
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Audio concat failed: {result.stderr[-300:]}")
