import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
FRONTEND_DIR = BASE_DIR / "frontend"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_AUTH_TOKEN", "")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "") or "claude-sonnet-4-6-20250514"

TTS_VOICE = "zh-CN-XiaoxiaoNeural"
TTS_RATE = "+0%"

MAX_KEYFRAMES = 8
VIDEO_MAX_SIZE_MB = 500

SUBTITLE_FONT_SIZE = 24
SUBTITLE_FONT_COLOR = "&H00FFFFFF"
