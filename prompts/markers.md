# 标记协议:时间戳跳转与截图

笔记里有两类时间戳标记,**处理方式不同**,务必区分。

## 1. 原片跳转 —— 仅在有视频 URL 时添加,直接输出最终格式(不用占位符)

为章节标注可跳转的时间戳。**仅当用户提供可跳转的视频 URL(B站/YouTube)时才加**;本地文件或不支持跳转的平台**不加任何时间戳**。

Claude 生成笔记时**直接写出最终格式**(这只是文本生成,无需占位符,也无需后处理):

- **B站 URL** → 章节标题后加 `[mm:ss](https://www.bilibili.com/video/{BV号}?t={总秒数})`
  - 例:`## 实操演示 [03:10](https://www.bilibili.com/video/BV1xxx?t=190)`
- **YouTube URL** → `[mm:ss](https://youtu.be/{id}?t={总秒数}s)`
- **本地文件 / 无 URL / 不支持跳转的平台** → **完全不加时间戳**

> ⚠️ 不要写 `*Content-[mm:ss]` 这种占位符——它是早期协议的残留,容易泄漏到成品里。直接写最终链接即可。

时间换算:`mm:ss` → 总秒数 = `mm*60 + ss`,用于跳转参数 `t`。

## 2. 截图占位 `*Screenshot-[mm:ss]` —— 用占位符(脚本后处理)

截图必须由 ffmpeg 完成(Claude 无法截视频帧),所以这里**必须用占位符**,由 `extract_screenshots.py` 后处理替换为真实图片。

- **格式**:`*Screenshot-[mm:ss]`(mm/ss 两位数),如 `*Screenshot-[02:45]`,单独成行
- **位置**:视觉演示、代码讲解、UI 交互、操作步骤等章节的末尾
- **使用判断**:仅在视觉内容真正有助于理解时使用;纯口播段落不强插
- **前提**:需要有视频文件(本地视频,或可下载的 URL)。无视频文件时不加
- **强制**:`detailed` / `tutorial` 风格默认带截图标记(教程类需要视觉辅助)

后处理:`python extract_screenshots.py <笔记.md> <视频文件或URL>` 把 `*Screenshot-[mm:ss]` 替换为 `![截图 @mm:ss](images/screenshot_xxx.jpg)`。无 ffmpeg 或某帧失败时保留占位。
