import uuid
import asyncio
import traceback
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import aiofiles

from backend.config import UPLOAD_DIR, OUTPUT_DIR, FRONTEND_DIR, VIDEO_MAX_SIZE_MB
from backend.models import TaskInfo, TaskStatus, GenerateRequest
from backend.services.video_analyzer import analyze_video
from backend.services.script_generator import generate_script
from backend.services.tts_service import synthesize_speech
from backend.services.subtitle_service import generate_subtitles
from backend.services.video_composer import compose_video

app = FastAPI(title="ClipScribe-AI", version="1.0.0")

tasks: dict[str, TaskInfo] = {}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".webm"):
        raise HTTPException(400, f"Unsupported video format: {ext}")

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / filename

    size = 0
    async with aiofiles.open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > VIDEO_MAX_SIZE_MB * 1024 * 1024:
                await f.close()
                filepath.unlink(missing_ok=True)
                raise HTTPException(413, "File too large")
            await f.write(chunk)

    return {"filename": filename, "size": size}


@app.post("/api/generate")
async def generate(request: GenerateRequest):
    video_path = UPLOAD_DIR / request.video_filename
    if not video_path.exists():
        raise HTTPException(404, "Video file not found")

    task_id = uuid.uuid4().hex[:12]
    task = TaskInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_filename=request.video_filename,
    )
    tasks[task_id] = task

    asyncio.create_task(_run_pipeline(task_id, video_path, request.style))
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@app.get("/api/script/{task_id}")
async def get_script(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.script:
        raise HTTPException(400, "Script not yet generated")
    return {"script": task.script}


@app.get("/api/download/{task_id}")
async def download_video(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.COMPLETED or not task.output_filename:
        raise HTTPException(400, "Video not ready")

    output_path = OUTPUT_DIR / task_id / task.output_filename
    if not output_path.exists():
        raise HTTPException(404, "Output file not found")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"clipscribe_{task_id}.mp4",
    )


async def _run_pipeline(task_id: str, video_path: Path, style: str):
    task = tasks[task_id]
    task_dir = OUTPUT_DIR / task_id
    task_dir.mkdir(exist_ok=True)

    try:
        task.status = TaskStatus.ANALYZING
        task.progress = 10
        task.message = "正在分析视频..."
        keyframes, video_info = await asyncio.to_thread(
            analyze_video, video_path, task_dir
        )

        task.status = TaskStatus.GENERATING_SCRIPT
        task.progress = 30
        task.message = "正在生成解说文案..."
        script_segments = await generate_script(keyframes, video_info, style)
        task.script = script_segments

        task.status = TaskStatus.SYNTHESIZING_VOICE
        task.progress = 50
        task.message = "正在合成配音..."
        audio_segments = await synthesize_speech(script_segments, task_dir)

        task.progress = 70
        task.message = "正在生成字幕..."
        subtitle_path = generate_subtitles(audio_segments, task_dir)

        task.status = TaskStatus.COMPOSING_VIDEO
        task.progress = 80
        task.message = "正在合成最终视频..."
        output_filename = await asyncio.to_thread(
            compose_video, video_path, audio_segments, subtitle_path, task_dir
        )

        task.output_filename = output_filename
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.message = "生成完成！"

    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
        task.message = f"生成失败: {str(e)}"
        traceback.print_exc()


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
