"""截图标记解析。移植自 BiliNote backend/app/utils/screenshot_marker.py。"""
import re
from typing import List, Tuple


def extract_screenshot_timestamps(markdown: str) -> List[Tuple[str, int]]:
    """从 Markdown 提取 *Screenshot-[mm:ss] 标记,返回 [(原始标记字符串, 总秒数)]。

    兼容 LLM 常用的星号包裹(如 `*Screenshot-[01:23]`、`**Screenshot-[01:23]**`)。
    """
    pattern = r"(\**Screenshot-(?:\[(\d{2}):(\d{2})\]|(\d{2}):(\d{2}))\**)"
    results: List[Tuple[str, int]] = []
    for match in re.finditer(pattern, markdown):
        mm = match.group(2) or match.group(4)
        ss = match.group(3) or match.group(5)
        total_seconds = int(mm) * 60 + int(ss)
        results.append((match.group(1), total_seconds))
    return results
