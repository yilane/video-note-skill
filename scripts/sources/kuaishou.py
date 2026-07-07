"""快手云端 ASR。

移植自 BiliNote backend/app/transcriber/kuaishou.py,去除 logger/timeit/events 耦合。
免 API Key,仅需 requests。输入为本地音频文件路径。
比 bcut 更简单:单次 POST,无分片上传与轮询。作为 bcut 的备选。
"""
import os

import requests

from models import TranscriptResult, TranscriptSegment

API_URL = "https://ai.kuaishou.com/api/effects/subtitle_generate"


def transcript(file_path: str) -> TranscriptResult:
    """对本地音频文件执行快手 ASR,返回 TranscriptResult。失败抛 RuntimeError。"""
    with open(file_path, "rb") as f:
        file_binary = f.read()
    if not file_binary:
        raise RuntimeError(f"无法读取音频文件: {file_path}")

    files = [("file", (os.path.basename(file_path), file_binary, "audio/mpeg"))]
    resp = requests.post(API_URL, data={"typeId": "1"}, files=files, timeout=300)
    resp.raise_for_status()
    result = resp.json()

    if "data" not in result or result.get("code", 0) != 0:
        raise RuntimeError(f"快手 ASR 返回错误: {result.get('message', '未知错误')}")

    segments = []
    full_text = ""
    for u in result.get("data", {}).get("text", []):
        text = u.get("text", "").strip()
        segments.append(TranscriptSegment(
            start=float(u.get("start_time", 0)),
            end=float(u.get("end_time", 0)),
            text=text,
        ))
        full_text += text + " "

    return TranscriptResult(
        language="zh",
        full_text=full_text.strip(),
        segments=segments,
        source="kuaishou",
    )
