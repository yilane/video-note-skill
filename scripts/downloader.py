"""yt-dlp 音频/视频下载封装。

移植自 BiliNote bilibili_downloader.py + youtube_downloader.py,去除项目耦合。
- B站自动应用 dm_img patch 绕过 412(见 bili_patch.py)
- cookie 从 BILI_COOKIE(完整)或 BILI_SESSDATA 注入,B站需 Referer
- 代理从 proxy 参数或 HTTPS_PROXY 注入
"""
import os
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
                   browser_cookie: Optional[str] = "auto") -> dict:
    """下载音频(mp3,64kbps),返回 {audio_path, video_id, title, duration}。

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
        )

    output_dir = output_dir or tempfile.mkdtemp(prefix="video_note_dl_")
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
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
    audio_path = os.path.join(output_dir, f"{video_id}.mp3")
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
                   browser_cookie: Optional[str] = "auto") -> str:
    """下载视频(mp4),返回视频路径。供截图用。失败抛 RuntimeError。"""
    if detect_platform(url) == "douyin":
        return douyin.download_video(
            url,
            output_dir=output_dir,
            cookie=cookie,
            proxy=proxy,
            use_browser_cookie=use_browser_cookie,
            browser_cookie=browser_cookie,
        )

    output_dir = output_dir or tempfile.mkdtemp(prefix="video_note_dl_")
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": "bv*[ext=mp4]/bestvideo+bestaudio/best",
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
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
    video_path = os.path.join(output_dir, f"{video_id}.mp4")
    if not os.path.exists(video_path):
        raise RuntimeError(f"下载后未找到视频文件: {video_path}")
    return video_path


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
