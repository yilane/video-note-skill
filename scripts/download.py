#!/usr/bin/env python3
"""download.py —— video-note skill 的独立下载入口。

只把视频(mp4)或音频(mp3)下载到本地,不生成笔记。与 fetch_transcript.py(只提取
文案)对等。底层复用 downloader.download_video / download_audio:
  - B站:yt-dlp + 自动 dm_img patch(绕 412)+ cookie + Referer
  - 抖音:douyin.download_video(无水印最高码率)/ download_audio
  - YouTube / 其他 yt-dlp 支持的平台同样可用

stdout 打印最终文件的绝对路径(一行,便于脚本拼接);过程信息走 stderr。
失败时非零退出码 + stderr 中文说明。
"""
import argparse
import os
import sys

# 注入 scripts/ 目录到 sys.path,使 `from downloader` 在任意 cwd 下可用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 确保 stdout/stderr 用 UTF-8,避免 Windows 控制台默认 GBK 导致中文/路径乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from downloader import download_audio, download_video, fetch_title, sanitize_filename  # noqa: E402
from url_parser import detect_platform  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只下载视频(mp4)或音频(mp3)到本地,不生成笔记。",
    )
    parser.add_argument("url", help="视频 URL(B站 / 抖音 / YouTube 等)")
    parser.add_argument("-o", "--output-dir", help="输出目录;默认当前工作目录")
    parser.add_argument("-O", "--output-name",
                        help="输出文件名(不含扩展名);默认用视频标题,取不到则用 video_id")
    parser.add_argument("--audio", action="store_true", help="只下载音频(mp3)")
    parser.add_argument("--bili-cookie", help="B站 cookie;默认读 BILI_COOKIE / BILI_SESSDATA")
    parser.add_argument("--douyin-cookie", help="抖音 cookie 兜底;默认读 DOUYIN_COOKIE")
    parser.add_argument("--browser-cookie", choices=["auto", "chrome", "edge", "firefox"], default="auto",
                        help="抖音需要 fresh cookie 时自动从浏览器读取(默认 auto: Chrome→Edge)")
    parser.add_argument("--no-browser-cookie", action="store_true",
                        help="禁用抖音浏览器 cookie 自动读取")
    parser.add_argument("--proxy", help="代理 URL;默认读 HTTPS_PROXY/HTTP_PROXY")
    args = parser.parse_args()

    # 仅接受 URL(下载场景下本地文件无意义)
    lowered = args.url.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("www.")):
        print(f"[download] 输入不是 URL: {args.url}\n应为视频 URL(http(s)://...)。",
              file=sys.stderr)
        return 1

    platform = detect_platform(args.url)
    if platform not in ("bilibili", "douyin", "youtube"):
        print(f"[download] 未识别平台 [{platform or '未知'}],将尝试 yt-dlp 通用下载。",
              file=sys.stderr)

    output_dir = os.path.abspath(args.output_dir or os.getcwd())
    os.makedirs(output_dir, exist_ok=True)

    proxy = args.proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    # 按平台选 cookie;不显式传时底层会自行读取对应环境变量
    cookie = args.bili_cookie if platform == "bilibili" else args.douyin_cookie
    use_browser_cookie = not args.no_browser_cookie

    # 确定文件名(不含扩展名):用户指定 > 视频标题(清洗)> None(底层回退 video_id)
    output_name = sanitize_filename(args.output_name) if args.output_name else None
    if output_name is None:
        print("[download] 正在获取视频标题用于命名…", file=sys.stderr)
        output_name = fetch_title(
            args.url,
            cookie=cookie,
            proxy=proxy,
            use_browser_cookie=use_browser_cookie,
            browser_cookie=args.browser_cookie,
        )
        if output_name:
            print(f"[download] 将以「{output_name}」命名", file=sys.stderr)
        else:
            print("[download] 未能获取标题,回退使用 video_id 命名", file=sys.stderr)

    try:
        if args.audio:
            info = download_audio(
                args.url,
                output_dir=output_dir,
                cookie=cookie,
                proxy=proxy,
                use_browser_cookie=use_browser_cookie,
                browser_cookie=args.browser_cookie,
                output_name=output_name,
            )
            path = info["audio_path"]
        else:
            path = download_video(
                args.url,
                output_dir=output_dir,
                cookie=cookie,
                proxy=proxy,
                use_browser_cookie=use_browser_cookie,
                browser_cookie=args.browser_cookie,
                output_name=output_name,
            )
    except RuntimeError as e:
        print(f"[download] 下载失败: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[download] 错误: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    abs_path = os.path.abspath(path)
    print(abs_path)  # stdout:最终文件绝对路径(一行)
    print(f"[download] 完成: {abs_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
