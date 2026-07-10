"""yt-dlp 音频/视频下载封装。

移植自 BiliNote bilibili_downloader.py + youtube_downloader.py,去除项目耦合。
- B站自动应用 dm_img patch 绕过 412(见 bili_patch.py)
- cookie 从 BILI_COOKIE(完整)或 BILI_SESSDATA 注入,B站需 Referer
- 代理从 proxy 参数或 HTTPS_PROXY 注入
"""
import os
import re
import sys
import tempfile
from typing import Optional

import yt_dlp

from bili_patch import apply_bilibili_dm_img_patch
from sources import douyin
from url_parser import detect_platform

# 模块加载时应用 B站 patch(幂等、防御性)
apply_bilibili_dm_img_patch()


def download_audio(url: str, output_dir: Optional[str] = None, cookie: Optional[str] = None,
                   proxy: Optional[str] = None, use_browser_cookie: bool = True,
                   browser_cookie: Optional[str] = "auto",
                   output_name: Optional[str] = None) -> dict:
    """下载音频(mp3,64kbps),返回 {audio_path, video_id, title, duration}。

    output_name 指定时,文件名用 ``<output_name>.<ext>``;否则回退 ``<id>.<ext>``。
    失败抛 RuntimeError。
    """
    if detect_platform(url) == "douyin":
        return douyin.download_audio(
            url,
            output_dir=output_dir,
            cookie=cookie,
            proxy=proxy,
            use_browser_cookie=use_browser_cookie,
            browser_cookie=browser_cookie,
            output_name=output_name,
        )

    output_dir = output_dir or tempfile.mkdtemp(prefix="video_note_dl_")
    os.makedirs(output_dir, exist_ok=True)

    tmpl_stem = output_name or "%(id)s"
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(output_dir, f"{tmpl_stem}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "64"}
        ],
    }
    _apply_common_opts(ydl_opts, url, cookie, proxy)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        raise RuntimeError(f"yt-dlp 下载音频失败: {e}") from e

    video_id = info.get("id")
    audio_path = os.path.join(output_dir, f"{output_name or video_id}.mp3")
    if not os.path.exists(audio_path):
        raise RuntimeError(f"下载后未找到音频文件: {audio_path}")
    return {
        "audio_path": audio_path,
        "video_id": video_id,
        "title": info.get("title"),
        "duration": info.get("duration", 0),
    }


def download_video(url: str, output_dir: Optional[str] = None, cookie: Optional[str] = None,
                   proxy: Optional[str] = None, use_browser_cookie: bool = True,
                   browser_cookie: Optional[str] = "auto",
                   output_name: Optional[str] = None) -> str:
    """下载视频(mp4),返回视频路径。供截图用。失败抛 RuntimeError。

    output_name 指定时,文件名用 ``<output_name>.<ext>``;否则回退 ``<id>.<ext>``。
    """
    if detect_platform(url) == "douyin":
        return douyin.download_video(
            url,
            output_dir=output_dir,
            cookie=cookie,
            proxy=proxy,
            use_browser_cookie=use_browser_cookie,
            browser_cookie=browser_cookie,
            output_name=output_name,
        )

    output_dir = output_dir or tempfile.mkdtemp(prefix="video_note_dl_")
    os.makedirs(output_dir, exist_ok=True)

    tmpl_stem = output_name or "%(id)s"
    ydl_opts = {
        "format": "bv*[ext=mp4]/bestvideo+bestaudio/best",
        "outtmpl": os.path.join(output_dir, f"{tmpl_stem}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    _apply_common_opts(ydl_opts, url, cookie, proxy)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        raise RuntimeError(f"yt-dlp 下载视频失败: {e}") from e

    video_id = info.get("id")
    video_path = os.path.join(output_dir, f"{output_name or video_id}.mp4")
    if not os.path.exists(video_path):
        raise RuntimeError(f"下载后未找到视频文件: {video_path}")
    return video_path


def fetch_title(url: str, cookie: Optional[str] = None, proxy: Optional[str] = None,
                use_browser_cookie: bool = True,
                browser_cookie: Optional[str] = "auto") -> Optional[str]:
    """获取视频标题并清洗为可用文件名。失败返回 None(调用方回退到 video_id)。

    - 抖音:走 douyin.fetch_video_info 取 item_title / desc
    - 其他(B站/YouTube 等):走 yt-dlp extract_info(download=False)取 title
    """
    if detect_platform(url) == "douyin":
        try:
            detail = douyin.fetch_video_info(
                url, cookie=cookie, proxy=proxy,
                use_browser_cookie=use_browser_cookie, browser_cookie=browser_cookie,
            )
            return sanitize_filename(detail.get("item_title") or detail.get("desc"))
        except Exception as e:
            print(f"[downloader] 获取抖音标题失败,将回退 video_id 命名: {e}", file=sys.stderr)
            return None

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
    }
    _apply_common_opts(ydl_opts, url, cookie, proxy)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[downloader] 获取标题失败,将回退 video_id 命名: {e}", file=sys.stderr)
        return None
    return sanitize_filename(info.get("title"))


def sanitize_filename(name: Optional[str]) -> Optional[str]:
    """清洗为安全的 Windows 文件名(不含扩展名)。

    去掉非法字符 ``\\ / : * ? " < > |``,折叠空白,去掉首尾空白/点,截断到 80 字符。
    结果为空则返回 None。
    """
    if not name:
        return None
    cleaned = re.sub(r'[\\/:*?"<>|]', "", str(name))
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".").strip()
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip()
    return cleaned or None


def _apply_common_opts(ydl_opts: dict, url: str, cookie: Optional[str], proxy: Optional[str]) -> None:
    platform = detect_platform(url)
    if platform == "bilibili":
        ydl_opts["http_headers"] = {"Referer": "https://www.bilibili.com"}

    cookie = cookie or os.environ.get("BILI_COOKIE")
    if not cookie:
        sessdata = os.environ.get("BILI_SESSDATA")
        if sessdata:
            cookie = f"SESSDATA={sessdata}"
    if cookie:
        ydl_opts["cookiefile"] = _write_netscape_cookie(cookie, platform)

    if proxy:
        ydl_opts["proxy"] = proxy


def _write_netscape_cookie(cookie_str: str, platform: Optional[str]) -> str:
    """把 'k=v; k2=v2' 形式 cookie 写成 Netscape 格式文件,返回路径。"""
    domain = {
        "bilibili": ".bilibili.com",
        "youtube": ".youtube.com",
    }.get(platform, ".com")
    lines = ["# Netscape HTTP Cookie File\n"]
    for pair in cookie_str.split("; "):
        if "=" in pair:
            k, v = pair.split("=", 1)
            lines.append(f"{domain}\tTRUE\t/\tFALSE\t0\t{k}\t{v}\n")
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.writelines(lines)
    tmp.close()
    return tmp.name
