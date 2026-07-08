"""video-note skill 的转录源子包。

各模块提供统一的 fetch / transcript 接口,返回 models.TranscriptResult:
- youtube:   fetch(url_or_id, proxy=None) -> TranscriptResult | None
- bilibili:  fetch(url, cookie=None)       -> TranscriptResult | None
- douyin:    download_audio/download_video -> 本地文件
- bcut:      transcript(file_path)         -> TranscriptResult
- kuaishou:  transcript(file_path)         -> TranscriptResult
"""
