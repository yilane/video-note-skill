#!/usr/bin/env python3
"""fetch_transcript.py —— video-note skill 的转录获取入口。

智能路由:
  - 本地音频文件(.mp3/.m4a/.wav 等) → bcut 云端 ASR(可 --asr kuaishou)
  - 本地视频文件(.mp4/.mkv 等)     → ffmpeg 提取音频 → ASR
  - YouTube URL                    → youtube-transcript-api 字幕直取
  - B站 URL                        → B站 player API 字幕直取
  - 抖音 URL                      → 下载音频 → ASR
  - 其他平台 / 无字幕              → 报错引导(留待 L2 的下载能力)

stdout 输出 TranscriptResult JSON(含 segment_text 字段)。
失败时非零退出码 + stderr 中文说明。
"""
import argparse
import json
import os
import sys
from typing import Optional

# 注入 scripts/ 目录到 sys.path,使 `from models` / `from sources` 在任意 cwd 下可用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保 stdout/stderr 用 UTF-8,避免 Windows 控制台默认 GBK 导致中文/JSON 乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import audio  # noqa: E402
from models import TranscriptResult  # noqa: E402
from url_parser import detect_platform  # noqa: E402
from sources import youtube, bilibili, bcut, kuaishou, douyin  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="获取视频/音频的转录文本(字幕直取或云端 ASR)。",
    )
    parser.add_argument("input", help="视频 URL(YouTube/B站/抖音)或本地音视频文件路径")
    parser.add_argument("-o", "--output", help="额外把 JSON 保存到该文件")
    parser.add_argument("--asr", choices=["bcut", "kuaishou"], default="bcut",
                        help="音频 ASR 引擎(默认 bcut)")
    parser.add_argument("--bili-cookie", help="B站 SESSDATA cookie(AI 字幕);默认读 BILI_SESSDATA")
    parser.add_argument("--douyin-cookie", help="抖音 cookie 兜底;默认读 DOUYIN_COOKIE")
    parser.add_argument("--browser-cookie", choices=["auto", "chrome", "edge", "firefox"], default="auto",
                        help="抖音需要 fresh cookie 时自动从浏览器读取(默认 auto: Chrome→Edge)")
    parser.add_argument("--no-browser-cookie", action="store_true",
                        help="禁用抖音浏览器 cookie 自动读取")
    parser.add_argument("--proxy", help="代理 URL;默认读 HTTPS_PROXY/HTTP_PROXY")
    args = parser.parse_args()

    proxy = args.proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    bili_cookie = args.bili_cookie or os.environ.get("BILI_SESSDATA")
    douyin_cookie = args.douyin_cookie or os.environ.get("DOUYIN_COOKIE")

    try:
        result = _route(
            args.input,
            asr=args.asr,
            bili_cookie=bili_cookie,
            douyin_cookie=douyin_cookie,
            use_browser_cookie=not args.no_browser_cookie,
            browser_cookie=args.browser_cookie,
            proxy=proxy,
        )
    except RuntimeError as e:
        print(f"[fetch_transcript] 失败: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # 兜底:网络异常、第三方库报错等
        print(f"[fetch_transcript] 错误: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if result is None:
        print(f"[fetch_transcript] 未能获取转录文本: {args.input}", file=sys.stderr)
        print("  可能原因:该视频无字幕 / 需要登录(B站 AI 字幕需 BILI_SESSDATA)/ 平台暂不支持。",
              file=sys.stderr)
        print("  建议:提供本地音频文件,或手动导出字幕(.srt)后再生成笔记。", file=sys.stderr)
        return 1

    output = result.to_dict()
    output["segment_text"] = result.to_segment_text()
    payload = json.dumps(output, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"[fetch_transcript] 已保存到 {args.output}", file=sys.stderr)

    print(payload)  # stdout:纯 JSON
    return 0


def _route(input_arg: str, asr: str, bili_cookie: Optional[str], proxy: Optional[str],
           douyin_cookie: Optional[str] = None, use_browser_cookie: bool = True,
           browser_cookie: Optional[str] = "auto") -> Optional[TranscriptResult]:
    # ① 本地文件
    if os.path.exists(input_arg):
        return _route_file(input_arg, asr)

    # ② URL
    lowered = input_arg.lower()
    if lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("www."):
        platform = detect_platform(input_arg)
        if platform == "youtube":
            result = youtube.fetch(input_arg, proxy=proxy)
            if result is None:
                print("[fetch_transcript] YouTube 无可用字幕,fallback 到下载音频→ASR", file=sys.stderr)
                result = _fallback_download_asr(input_arg, asr, proxy)
            if result is None:
                raise RuntimeError(
                    "YouTube 字幕获取与音频下载均失败(可能被反爬、地区限制或无字幕)。"
                    "可配置代理(HTTPS_PROXY)重试,或改用 baoyu-youtube-transcript skill。"
                )
            return result
        if platform == "bilibili":
            result = bilibili.fetch(input_arg, cookie=bili_cookie)
            if result is None:
                print("[fetch_transcript] B站无可用字幕,fallback 到下载音频→ASR", file=sys.stderr)
                result = _fallback_download_asr(input_arg, asr, proxy, cookie=bili_cookie)
            if result is None:
                raise RuntimeError(
                    "B站字幕获取与音频下载均失败:可能无字幕、需登录(BILI_SESSDATA)或被风控。"
                )
            return result
        if platform == "douyin":
            print("[fetch_transcript] 抖音暂不支持字幕直取,下载音频→ASR", file=sys.stderr)
            result = _douyin_download_asr(
                input_arg,
                asr,
                proxy,
                cookie=douyin_cookie,
                use_browser_cookie=use_browser_cookie,
                browser_cookie=browser_cookie,
            )
            if result is None:
                raise RuntimeError(
                    "抖音音频下载或 ASR 失败:可能链接失效、视频需要登录、被风控或接口参数已变化。"
                    "可设置 DOUYIN_COOKIE 后重试。"
                )
            return result
        raise RuntimeError(
            f"暂不支持平台 [{platform or '未知'}] 的自动转录。"
            "已支持:YouTube / B站(URL 字幕直取 + 下载兜底)、抖音(下载音频 + ASR)、本地音视频文件(云端 ASR)。"
            "可提供字幕文件(.srt)或本地音频。"
        )

    raise RuntimeError(
        f"无法识别输入: {input_arg}\n应为视频 URL(http(s)://...)或本地存在的文件路径。"
    )


def _fallback_download_asr(url: str, asr: str, proxy: Optional[str],
                           cookie: Optional[str] = None) -> Optional[TranscriptResult]:
    """字幕直取失败时,用 yt-dlp 下载音频走云端 ASR。需 yt-dlp;失败返回 None。"""
    try:
        from downloader import download_audio  # 延迟 import:无 yt-dlp 时不影响字幕路径
    except Exception as e:
        print(f"[fetch_transcript] 下载兜底不可用(未装 yt-dlp?): {e}", file=sys.stderr)
        return None
    try:
        info = download_audio(url, cookie=cookie, proxy=proxy)
    except RuntimeError as e:
        print(f"[fetch_transcript] 下载音频失败: {e}", file=sys.stderr)
        return None
    audio_path = info["audio_path"]
    if asr == "kuaishou":
        return kuaishou.transcript(audio_path)
    return bcut.transcript(audio_path)


def _douyin_download_asr(url: str, asr: str, proxy: Optional[str],
                         cookie: Optional[str] = None, use_browser_cookie: bool = True,
                         browser_cookie: Optional[str] = "auto") -> Optional[TranscriptResult]:
    """下载抖音音频走云端 ASR。失败返回 None。"""
    try:
        info = douyin.download_audio(
            url,
            cookie=cookie,
            proxy=proxy,
            use_browser_cookie=use_browser_cookie,
            browser_cookie=browser_cookie,
        )
    except RuntimeError as e:
        print(f"[fetch_transcript] 下载抖音音频失败: {e}", file=sys.stderr)
        return None
    audio_path = info["audio_path"]
    if asr == "kuaishou":
        return kuaishou.transcript(audio_path)
    return bcut.transcript(audio_path)


def _route_file(path: str, asr: str) -> TranscriptResult:
    audio_path = path
    if audio.is_video(path):
        audio_path = audio.extract_audio(path)  # 无 ffmpeg 时抛 RuntimeError
    elif not audio.is_audio(path):
        ext = os.path.splitext(path)[1]
        raise RuntimeError(
            f"不支持的文件类型: {ext}\n"
            "支持音频: .mp3 .m4a .wav .aac .flac .ogg;视频: .mp4 .mkv .mov .webm 等(需 ffmpeg)。"
        )

    if asr == "kuaishou":
        return kuaishou.transcript(audio_path)
    return bcut.transcript(audio_path)


if __name__ == "__main__":
    sys.exit(main())
