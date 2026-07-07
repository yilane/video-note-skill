#!/usr/bin/env python3
"""extract_screenshots.py —— 把笔记 Markdown 里的 *Screenshot-[mm:ss] 标记替换为真实截图。

用法:
  python extract_screenshots.py <笔记.md> <视频文件或URL> [-o 输出.md] [--img-dir 目录]

视频可为本地文件路径或 URL(URL 自动下载)。需 ffmpeg;标记解析见 screenshot_marker.py。
"""
import argparse
import os
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from screenshot_marker import extract_screenshot_timestamps  # noqa: E402
import audio  # noqa: E402  (复用 get_ffmpeg_bin)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把笔记里的 *Screenshot-[mm:ss] 标记替换为真实截图。"
    )
    parser.add_argument("markdown", help="笔记 Markdown 文件路径")
    parser.add_argument("video", help="视频文件路径,或视频 URL(自动下载)")
    parser.add_argument("-o", "--output", help="输出 Markdown 路径(默认覆盖原文件)")
    parser.add_argument("--img-dir", help="截图保存目录(默认 md 同级 images/)")
    args = parser.parse_args()

    with open(args.markdown, "r", encoding="utf-8") as f:
        md = f.read()

    markers = extract_screenshot_timestamps(md)
    if not markers:
        print("[extract_screenshots] 未找到 *Screenshot-[mm:ss] 标记,无需处理。", file=sys.stderr)
        return 0

    video_path = _resolve_video(args.video)
    md_dir = os.path.dirname(os.path.abspath(args.markdown))
    img_dir = args.img_dir or os.path.join(md_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    result_md = md
    done = 0
    for i, (marker, total_seconds) in enumerate(markers):
        try:
            img_path = _screenshot(video_path, img_dir, total_seconds, i)
            rel = os.path.relpath(img_path, md_dir).replace("\\", "/")
            result_md = result_md.replace(marker, f"![截图 @{_fmt(total_seconds)}]({rel})")
            print(f"[extract_screenshots] {marker} -> {rel}", file=sys.stderr)
            done += 1
        except Exception as e:
            print(f"[extract_screenshots] 截图失败 {marker}: {e}(保留占位)", file=sys.stderr)

    out_path = args.output or args.markdown
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result_md)
    print(f"[extract_screenshots] 完成: {done}/{len(markers)} 处 -> {out_path}", file=sys.stderr)
    return 0


def _resolve_video(video_arg: str) -> str:
    """视频为本地路径直接用;为 URL 则下载。"""
    if os.path.exists(video_arg):
        return video_arg
    from downloader import download_video  # 延迟 import
    print(f"[extract_screenshots] 视频为 URL,下载中: {video_arg}", file=sys.stderr)
    return download_video(video_arg)


def _screenshot(video_path: str, img_dir: str, timestamp: int, index: int) -> str:
    """用 ffmpeg 在 timestamp 处截单帧,返回图片路径。"""
    ffmpeg = audio.get_ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError(audio.ffmpeg_missing_message("生成截图"))
    filename = f"screenshot_{index:03d}_{uuid.uuid4().hex[:8]}.jpg"
    out = os.path.join(img_dir, filename)
    cmd = [ffmpeg, "-ss", str(timestamp), "-i", video_path, "-frames:v", "1", "-q:v", "2", out, "-y"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 退出码 {r.returncode}")
    return out


def _fmt(seconds: int) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


if __name__ == "__main__":
    sys.exit(main())
