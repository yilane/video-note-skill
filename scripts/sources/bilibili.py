"""B站字幕直取,通过官方 player API。

移植自 BiliNote backend/app/downloaders/bilibili_subtitle.py。
免 API Key;AI 字幕需 SESSDATA cookie(人工字幕不需要)。
"""
from typing import Optional

import requests

from models import TranscriptResult, TranscriptSegment
from url_parser import extract_video_id, extract_bilibili_p_number, resolve_bilibili_short_url

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
API_VIEW = "https://api.bilibili.com/x/web-interface/view"
API_PLAYER = "https://api.bilibili.com/x/player/wbi/v2"


def fetch(video_url: str, cookie: Optional[str] = None) -> Optional[TranscriptResult]:
    """获取 B站字幕,返回 TranscriptResult;无字幕或需登录返回 None。"""
    headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com"}
    if cookie:
        headers["Cookie"] = cookie

    if "b23.tv" in video_url:
        video_url = resolve_bilibili_short_url(video_url) or video_url

    bvid = extract_video_id(video_url, "bilibili")
    if not bvid:
        return None

    p = extract_bilibili_p_number(video_url)
    cid = _get_cid(bvid, p, headers)
    if not cid:
        return None

    subtitles = _list_subtitles(bvid, cid, headers)
    if not subtitles:
        return None

    track = _pick(subtitles)
    if not track or not track.get("subtitle_url"):
        return None  # 字幕轨存在但无 url,通常需要 SESSDATA 登录态

    lan = track.get("lan") or "zh"
    body = _fetch_body(track["subtitle_url"], headers)
    if not body:
        return None

    segments = []
    for item in body:
        text = (item.get("content") or "").strip()
        if not text:
            continue
        segments.append(TranscriptSegment(
            start=float(item.get("from", 0)),
            end=float(item.get("to", 0)),
            text=text,
        ))

    if not segments:
        return None

    return TranscriptResult(
        language=lan,
        full_text=" ".join(s.text for s in segments),
        segments=segments,
        source="bilibili_player_api",
    )


def _get_cid(bvid: str, p: Optional[int], headers: dict) -> Optional[int]:
    params = {"bvid": bvid}
    if p is not None and p >= 1:
        params["p"] = p
    try:
        resp = requests.get(API_VIEW, params=params, headers=headers, timeout=10)
        data = resp.json()
    except Exception:
        return None
    if data.get("code") != 0:
        return None
    pages = data.get("data", {}).get("pages", [])
    if pages:
        idx = (p - 1) if (p is not None and 1 <= p <= len(pages)) else 0
        cid = pages[idx].get("cid")
        return int(cid) if cid else None
    cid = data.get("data", {}).get("cid")
    return int(cid) if cid else None


def _list_subtitles(bvid: str, cid: int, headers: dict) -> list:
    try:
        resp = requests.get(API_PLAYER, params={"bvid": bvid, "cid": cid}, headers=headers, timeout=10)
        data = resp.json()
    except Exception:
        return []
    if data.get("code") != 0:
        return []
    return data.get("data", {}).get("subtitle", {}).get("subtitles", []) or []


def _pick(subtitles: list) -> Optional[dict]:
    """优先级:人工中文 > AI 中文 > 任意中文 > 任意非空。"""
    if not subtitles:
        return None

    def is_zh(s: dict) -> bool:
        lan = (s.get("lan") or "").lower()
        return lan.startswith("zh") or lan == "ai-zh"

    for s in subtitles:  # 人工中文(ai_type 为空视为人工)
        if is_zh(s) and not s.get("ai_type"):
            return s
    for s in subtitles:  # AI 中文
        if is_zh(s):
            return s
    return subtitles[0]  # 任意非空


def _fetch_body(subtitle_url: str, headers: dict) -> Optional[list]:
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url
    try:
        resp = requests.get(subtitle_url, headers=headers, timeout=15)
        return resp.json().get("body") or []
    except Exception:
        return None
