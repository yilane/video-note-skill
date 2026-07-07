"""URL 解析与平台检测。

移植自 BiliNote backend/app/utils/url_parser.py,新增 detect_platform()。
"""
import re
from typing import Optional

import requests


def detect_platform(url: str) -> Optional[str]:
    """判断 URL 属于哪个视频平台。

    返回 'youtube' / 'bilibili' / 'douyin' / 'kuaishou' / None。
    """
    if not url:
        return None
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "bilibili.com" in lower or "b23.tv" in lower:
        return "bilibili"
    if "douyin.com" in lower:
        return "douyin"
    if "kuaishou.com" in lower or "chenzhongtech.com" in lower:
        return "kuaishou"
    return None


def extract_video_id(url: str, platform: str) -> Optional[str]:
    """从 URL 提取视频 ID(BV 号 / YouTube 11 位 ID / 抖音数字 ID)。"""
    if platform == "bilibili":
        if "b23.tv" in url:
            resolved = resolve_bilibili_short_url(url)
            if resolved:
                url = resolved
        match = re.search(r"BV([0-9A-Za-z]+)", url)
        return f"BV{match.group(1)}" if match else None

    elif platform == "youtube":
        match = re.search(r"(?:v=|youtu\.be/|shorts/)([0-9A-Za-z_-]{11})", url)
        return match.group(1) if match else None

    elif platform == "douyin":
        match = re.search(r"/video/(\d+)", url)
        return match.group(1) if match else None

    return None


def resolve_bilibili_short_url(short_url: str) -> Optional[str]:
    """解析 b23.tv 短链,返回真实 URL。"""
    try:
        resp = requests.head(short_url, allow_redirects=True, timeout=10)
        return resp.url
    except requests.RequestException:
        return None


def extract_bilibili_p_number(url: str) -> Optional[int]:
    """从 B站分 P 视频 URL 提取 p 参数(从 1 开始)。非分 P 返回 None。"""
    if "b23.tv" in url:
        url = resolve_bilibili_short_url(url) or url

    match = re.search(r"[?&]p=(\d+)", url)
    if match:
        p = int(match.group(1))
        if p >= 1:
            return p

    match = re.search(r"/p(\d+)(?:/?$|\?|&)", url)
    if match:
        p_val = int(match.group(1))
        if p_val >= 1:
            return p_val

    return None
