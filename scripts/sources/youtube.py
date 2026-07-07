"""YouTube 字幕直取,基于 youtube-transcript-api。

移植自 BiliNote backend/app/downloaders/youtube_subtitle.py。
免 API Key;国内需代理(透传 proxy 参数或 HTTPS_PROXY 环境变量)。
"""
import re
from typing import List, Optional

from youtube_transcript_api import YouTubeTranscriptApi

from models import TranscriptResult, TranscriptSegment

DEFAULT_LANGS = ["zh-Hans", "zh", "zh-CN", "zh-TW", "en", "en-US", "ja"]


def fetch(url_or_id: str, langs: Optional[List[str]] = None, proxy: Optional[str] = None) -> Optional[TranscriptResult]:
    """获取 YouTube 字幕,返回 TranscriptResult;无字幕返回 None。"""
    if langs is None:
        langs = DEFAULT_LANGS

    video_id = _extract_id(url_or_id)
    api = _build_api(proxy)

    transcript_list = api.list(video_id)

    # 优先人工字幕,其次自动生成,最后任意可用
    transcript = None
    try:
        transcript = transcript_list.find_manually_created_transcript(langs)
    except Exception:
        try:
            transcript = transcript_list.find_generated_transcript(langs)
        except Exception:
            for t in transcript_list:
                transcript = t
                break

    if not transcript:
        return None

    fetched = transcript.fetch()
    segments = []
    for snippet in fetched:
        if isinstance(snippet, dict):
            text = snippet.get("text", "").strip()
            start = float(snippet.get("start", 0))
            duration = float(snippet.get("duration", 0))
        else:
            text = str(snippet).strip()
            start, duration = 0.0, 0.0
        if not text:
            continue
        segments.append(TranscriptSegment(start=start, end=start + duration, text=text))

    if not segments:
        return None

    return TranscriptResult(
        language=transcript.language_code,
        full_text=" ".join(s.text for s in segments),
        segments=segments,
        source="youtube_transcript_api",
    )


def _extract_id(url_or_id: str) -> str:
    """接受完整 URL、短链或 11 位 video id。"""
    match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([0-9A-Za-z_-]{11})", url_or_id)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url_or_id):
        return url_or_id
    return url_or_id  # 兜底,交给 API 报错


def _build_api(proxy: Optional[str]) -> YouTubeTranscriptApi:
    if proxy:
        try:
            import requests
            session = requests.Session()
            session.proxies = {"http": proxy, "https": proxy}
            return YouTubeTranscriptApi(http_client=session)
        except Exception:
            pass
    return YouTubeTranscriptApi()
