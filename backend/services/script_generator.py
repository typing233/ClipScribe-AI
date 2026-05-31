import json

import anthropic

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, CLAUDE_MODEL
from backend.models import ScriptSegment

STYLE_PROMPTS = {
    "normal": "请用客观、清晰、专业的语气进行解说，像一个纪录片旁白。",
    "humorous": "请用幽默风趣、轻松调侃的语气进行解说，适当加入网络用语让观众发笑。",
    "suspense": "请用悬疑紧张的语气进行解说，制造悬念，吸引观众注意力。",
}


def _generate_fallback_script(video_info: dict, style: str) -> list[ScriptSegment]:
    """Generate placeholder script segments based on video timing when API is unavailable."""
    duration = video_info["duration"]
    keyframe_times = video_info.get("keyframe_times", [])

    if len(keyframe_times) < 2:
        num_segments = max(1, int(duration // 5))
        seg_dur = duration / num_segments
        keyframe_times = [round(i * seg_dur, 2) for i in range(num_segments)]
        keyframe_times.append(round(duration, 2))

    style_texts = {
        "normal": [
            "画面缓缓展开，镜头对准了主要场景",
            "紧接着，新的画面映入眼帘，情节开始推进",
            "随着镜头的切换，故事进入了新的阶段",
            "画面中的细节暗示着接下来的发展走向",
            "场景再次变换，人物关系逐渐明朗",
            "此刻的画面充满了戏剧张力",
            "镜头推近，情绪开始变得紧张起来",
            "最终，画面定格在这一瞬间，意味深长",
        ],
        "humorous": [
            "好家伙，这一开场就知道不简单",
            "你看这个画面，是不是有点不对劲",
            "接下来发生的事，让人直呼离谱",
            "啊这，这剧情我是没想到的",
            "导演你出来，我保证不打你",
            "看到这里我直接笑喷了",
            "家人们谁懂啊，这什么展开",
            "就这？就这？行吧算你有本事",
        ],
        "suspense": [
            "注意看，这个画面暗藏玄机",
            "一切看似平静，但危险正在逼近",
            "没有人知道，接下来将发生什么",
            "画面中有一个细节，大多数人都没注意到",
            "真相往往隐藏在最不起眼的地方",
            "事情开始变得不对劲了",
            "所有线索都指向一个令人毛骨悚然的答案",
            "谜底即将揭晓，但结果可能出乎所有人意料",
        ],
    }

    texts = style_texts.get(style, style_texts["normal"])

    segments = []
    for i in range(len(keyframe_times) - 1):
        start = keyframe_times[i]
        end = keyframe_times[i + 1]
        text = texts[i % len(texts)]
        segments.append(ScriptSegment(start_time=start, end_time=end, text=text))

    if not segments:
        segments.append(ScriptSegment(
            start_time=0.0, end_time=duration, text="这段视频的内容引人入胜，值得细细品味。"
        ))

    return segments


async def generate_script(
    keyframes_b64: list[str], video_info: dict, style: str
) -> list[ScriptSegment]:
    """Call Claude API with keyframes to generate commentary script."""
    if not ANTHROPIC_API_KEY:
        return _generate_fallback_script(video_info, style)

    client_kwargs = {"api_key": ANTHROPIC_API_KEY}
    if ANTHROPIC_BASE_URL:
        client_kwargs["base_url"] = ANTHROPIC_BASE_URL

    try:
        client = anthropic.Anthropic(**client_kwargs)
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

        block = response.content[0] if response.content else None
        if not block or not hasattr(block, "text") or not block.text:
            raise RuntimeError("Empty response from LLM")
        response_text = block.text.strip()

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

    except Exception as e:
        print(f"[ScriptGenerator] API call failed: {e}, using fallback")
        return _generate_fallback_script(video_info, style)
