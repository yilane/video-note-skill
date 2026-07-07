"""本地音视频文件处理:类型判断 + ffmpeg 提取音频。"""
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".wma", ".opus"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".ts", ".m4v", ".wmv"}


def get_ffmpeg_bin() -> Optional[str]:
    """返回 ffmpeg 可执行路径(尊重 FFMPEG_BIN_PATH),没有则 None。"""
    env_path = os.environ.get("FFMPEG_BIN_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    return shutil.which("ffmpeg")


def ffmpeg_missing_message(action: str = "处理视频") -> str:
    """构造「未找到 ffmpeg」的报错信息,含当前平台的安装命令。"""
    if sys.platform == "win32":
        hint = (
            "  Windows: winget install ffmpeg\n"
            "         / choco install ffmpeg\n"
            "         / conda install ffmpeg"
        )
    elif sys.platform == "darwin":
        hint = "  macOS:   brew install ffmpeg\n         / conda install ffmpeg"
    else:
        hint = (
            "  Linux:   sudo apt install ffmpeg  (Debian/Ubuntu)\n"
            "         / sudo dnf install ffmpeg  (Fedora)\n"
            "         / conda install ffmpeg"
        )
    return (
        f"未找到 ffmpeg,无法{action}。请安装 ffmpeg:\n"
        f"{hint}\n"
        "  或设置 FFMPEG_BIN_PATH 环境变量指向 ffmpeg 可执行文件;\n"
        "  也可直接提供音频文件(.mp3/.m4a/.wav)绕过此步骤。"
    )


def is_audio(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def extract_audio(video_path: str, output_path: Optional[str] = None) -> str:
    """用 ffmpeg 从视频提取音频(mp3),返回音频文件路径。

    无 ffmpeg 或转换失败时抛 RuntimeError(含清晰中文原因 + 平台安装命令)。
    """
    ffmpeg = get_ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError(ffmpeg_missing_message("从视频文件提取音频"))

    if output_path is None:
        tmp_dir = tempfile.mkdtemp(prefix="video_note_")
        output_path = os.path.join(tmp_dir, "audio.mp3")

    cmd = [ffmpeg, "-y", "-i", video_path, "-vn", "-acodec", "libmp3lame", output_path]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"ffmpeg 提取音频失败(退出码 {e.returncode})。"
            f"stderr: {e.stderr.decode('utf-8', errors='ignore')[:500]}"
        ) from e

    return output_path
