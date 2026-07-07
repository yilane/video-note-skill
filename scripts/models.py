"""转录结果数据结构。

移植自 BiliNote backend/app/models/transcriber_model.py,去除外部依赖,
仅用标准库 dataclasses。
"""
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class TranscriptSegment:
    start: float  # 开始时间(秒)
    end: float    # 结束时间(秒)
    text: str


@dataclass
class TranscriptResult:
    language: Optional[str]
    full_text: str
    segments: List[TranscriptSegment]
    raw: Optional[dict] = None
    source: Optional[str] = None  # 标记来源,如 'bilibili_player_api' / 'bcut'

    def to_dict(self) -> dict:
        return asdict(self)

    def to_segment_text(self) -> str:
        """转成 `mm:ss - 文本` 格式,每段一行,供笔记提示词使用。"""
        return "\n".join(f"{_fmt_time(s.start)} - {s.text}" for s in self.segments)


def _fmt_time(seconds: float) -> str:
    """秒数 → mm:ss;超过 1 小时用 h:mm:ss。"""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
