from pydantic import BaseModel
from typing import Optional
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING_SCRIPT = "generating_script"
    SYNTHESIZING_VOICE = "synthesizing_voice"
    COMPOSING_VIDEO = "composing_video"
    COMPLETED = "completed"
    FAILED = "failed"


class ScriptSegment(BaseModel):
    start_time: float
    end_time: float
    text: str


class GenerateRequest(BaseModel):
    video_filename: str
    style: str = "normal"  # normal, humorous, suspense


class TaskInfo(BaseModel):
    task_id: str
    status: TaskStatus
    progress: int = 0
    message: str = ""
    video_filename: Optional[str] = None
    script: Optional[list[ScriptSegment]] = None
    output_filename: Optional[str] = None
    error: Optional[str] = None
