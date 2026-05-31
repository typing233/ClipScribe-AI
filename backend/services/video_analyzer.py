import base64
from pathlib import Path

import cv2
import numpy as np

from backend.config import MAX_KEYFRAMES


def analyze_video(video_path: Path, output_dir: Path) -> tuple[list[str], dict]:
    """Extract keyframes and metadata from video.

    Returns (keyframes_base64_list, video_info_dict).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0

    interval = max(1, frame_count // MAX_KEYFRAMES)
    keyframes_b64 = []
    keyframe_times = []

    for i in range(MAX_KEYFRAMES):
        frame_idx = i * interval
        if frame_idx >= frame_count:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        scale = min(1.0, 720.0 / max(width, height))
        if scale < 1.0:
            frame = cv2.resize(frame, None, fx=scale, fy=scale)

        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        b64 = base64.b64encode(buffer).decode("utf-8")
        keyframes_b64.append(b64)
        keyframe_times.append(round(frame_idx / fps, 2))

        frame_path = output_dir / f"keyframe_{i:02d}.jpg"
        cv2.imwrite(str(frame_path), frame)

    cap.release()

    video_info = {
        "duration": round(duration, 2),
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "frame_count": frame_count,
        "keyframe_times": keyframe_times,
    }

    return keyframes_b64, video_info
