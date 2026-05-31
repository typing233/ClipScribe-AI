import json

import anthropic

from backend.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from backend.models import ScriptSegment

STYLE_PROMPTS = {
    "normal": "请用客观、清晰、专业的语气进行解说，像一个纪录片旁白。",
    "humorous": "请用幽默风趣、轻松调侃的语气进行解说，适当加入网络用语让观众发笑。",
    "suspense": "请用悬疑紧张的语气进行解说，制造悬念，吸引观众注意力。",
}


async def generate_script(
    keyframes_b64: list[str], video_info: dict, style: str
) -> list[ScriptSegment]:
    """Call Claude API with keyframes to generate commentary script."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    duration = video_info["duration"]
    keyframe_times = video_info["keyframe_times"]

    style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["normal"])

    content = []
    content.append({
        "type": "text",
        "text": (
            f"以下是一段影视片段的关键帧截图（共{len(keyframes_b64)}张），"
            f"视频总时长为{duration}秒。\n"
            f"关键帧对应的时间点：{keyframe_times}\n\n"
            f"请你为这段视频生成一段影视解说文案。{style_instruction}\n\n"
            "要求：\n"
            "1. 将解说分成多个片段，每段对应视频的一个时间区间\n"
            "2. 每段解说文字控制在15-40字之间，适合语音朗读\n"
            "3. 解说要贴合画面内容，有故事性和吸引力\n"
            "4. 时间区间要覆盖整个视频，且不重叠\n\n"
            "请严格按照以下JSON格式输出（不要输出其他内容）：\n"
            "```json\n"
            "[\n"
            '  {"start_time": 0.0, "end_time": 5.0, "text": "解说文字"},\n'
            '  {"start_time": 5.0, "end_time": 10.0, "text": "解说文字"}\n'
            "]\n"
            "```"
        ),
    })

    for i, b64 in enumerate(keyframes_b64):
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": content}],
    )

    response_text = response.content[0].text.strip()

    json_start = response_text.find("[")
    json_end = response_text.rfind("]") + 1
    if json_start == -1 or json_end == 0:
        raise RuntimeError(f"Failed to parse script from LLM response: {response_text[:200]}")

    raw_segments = json.loads(response_text[json_start:json_end])

    segments = []
    for seg in raw_segments:
        segments.append(ScriptSegment(
            start_time=float(seg["start_time"]),
            end_time=float(seg["end_time"]),
            text=seg["text"],
        ))

    if not segments:
        raise RuntimeError("LLM returned empty script")

    return segments
