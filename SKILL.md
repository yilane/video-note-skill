---
name: video-note
description: 把视频/音频转换成结构化的中文 Markdown 笔记。可自动从视频 URL(B站/YouTube 等)或本地音视频文件获取转录(字幕直取,无字幕则下载音频走云端 ASR),由 Claude 生成多风格笔记(详细记录、小红书爆款、学术、教程等),并支持带时间戳的原片跳转标记和自动嵌入真实截图。当用户提供视频链接、字幕文件(.srt/.vtt/.txt)、本地音视频、或粘贴转录文本,并要求"做笔记/总结/整理/学习笔记/视频笔记/划重点/精简/拆解"时使用此 skill。即使用户只说"帮我把这个视频整理一下""这个视频讲了啥",只要意图是从视频内容生成笔记或摘要,都应触发。
---

# Video Note

将视频整理为结构化的中文 Markdown 笔记,可自动获取转录、生成笔记、嵌入截图。核心能力是**提示词工程**——由 Claude 自身完成笔记生成,不调用任何外部 LLM 服务,不需要 API Key。

## 前置依赖

首次使用自动转录 / 下载 / 截图前,安装 Python 依赖:

```bash
pip install -r {baseDir}/scripts/requirements.txt
```

- `requests`、`youtube-transcript-api`、`yt-dlp`(纯 Python,免 API Key)
- 系统 `ffmpeg`:**仅**本地视频转录、截图需要(YouTube/B站字幕直取、本地音频 ASR **不需要**)。安装:
  - Windows:`winget install ffmpeg` / `choco install ffmpeg` / `conda install ffmpeg`
  - macOS:`brew install ffmpeg` / `conda install ffmpeg`
  - Linux:`sudo apt install ffmpeg` / `sudo dnf install ffmpeg` / `conda install ffmpeg`
  - 或设置 `FFMPEG_BIN_PATH` 指向已有的 ffmpeg
- 可选环境变量:`HTTPS_PROXY`(YouTube/下载代理)、`BILI_COOKIE` 或 `BILI_SESSDATA`(B站登录态)
- Windows 下若 `python` 不可用,改用 `py`

## 输入形式

skill 接受三种输入:

1. **直接粘贴的转录 / 字幕文本** —— 最轻量、首选
2. **字幕文件**(`.srt` / `.vtt` / `.txt`) —— 读取后转为分段文本
3. **视频 URL**(B站 / YouTube 等)或**本地音视频文件** —— 自动转录

## 工作流

### 第 1 步:获取转录文本

优先用脚本自动获取:`{baseDir}/scripts/fetch_transcript.py`。

- **YouTube / B站 URL**,或**本地音视频文件** → 运行:
  ```bash
  python {baseDir}/scripts/fetch_transcript.py '<url-或-文件路径>'
  ```
  智能路由:**YouTube/B站 先试字幕直取,无字幕则自动下载音频走 bcut 云端 ASR**(B站自动应用 dm_img patch 绕过 412 风控);本地音频直接 bcut ASR;本地视频先 ffmpeg 提取音频再 ASR。**stdout 输出 JSON**,取 `segment_text` 字段(已是 `mm:ss - 文本` 格式)用于第 2 步。
- **`.srt` / `.vtt` / `.txt` 字幕文件**,或**粘贴的转录文本** → 不经脚本,直接整理为分段(见 `references/data-contract.md`)。
- **不支持的输入**(抖音等平台) → 脚本非零退出并在 stderr 给出引导;据此告知用户。

可选参数:`--asr kuaishou`(换快手 ASR)、`--bili-cookie <s>`、`--proxy <url>`、`-o <path>`。

> YouTube 若被反爬,可改用 `baoyu-youtube-transcript` skill 兜底。

### 第 2 步:规范分段文本

脚本输出已含 `segment_text`;手动文本按 `references/data-contract.md` 整理为 `mm:ss - 文本` 格式。

### 第 3 步:选择风格

默认 **`detailed`**。按用户意图或内容类型选择(定义在 `prompts/styles/`):

| 风格 | 适用场景 | 触发词 |
|---|---|---|
| `detailed`(默认) | 通用详细记录 | "详细/完整/全量记录" |
| `minimal` | 精简抓重点 | "精简/简短/重点/太长不看" |
| `xiaohongshu` | 小红书爆款 | "小红书/种草/爆款/发小红书" |
| `academic` | 学术/技术讲座 | "学术/论文/讲座/研究" |
| `tutorial` | 操作教程 | "教程/演示/实操/怎么操作" |
| `life_journal` | 生活 Vlog | "生活/vlog/感悟/日常" |
| `task_oriented` | 任务/待办 | "任务/待办/行动项/todo" |
| `business` | 商业分析 | "商业/行业/市场/分析" |
| `meeting_minutes` | 会议纪要 | "会议/纪要/访谈/对谈" |

用户未明确指定时,按内容类型推断(操作演示→`tutorial`、讲座→`academic`、会议对谈→`meeting_minutes` 等)。`tutorial` / `detailed` 风格默认带截图标记。

### 第 4 步:组合提示词并生成笔记

按顺序叠加:`prompts/base.md`(填入分段文本)+ `prompts/styles/<style>.md` + `prompts/markers.md`(若要跳转/截图)+ 用户额外要求。直接输出最终 Markdown,不要输出提示词原文。

### 第 5 步:后处理

- 笔记开头加来源(若提供 URL):`> 来源:{url}`
- 原片跳转时间戳:已在第 4 步按 `prompts/markers.md` 直接输出(有视频 URL→可点击跳转链接;本地文件/无 URL→**不加时间戳**),无需后处理
- `*Screenshot-[mm:ss]`:**需要真实截图时进入第 6 步**;否则保留占位

### 第 6 步:嵌入真实截图(可选)

若笔记含 `*Screenshot-[mm:ss]` 且有视频文件/URL:

```bash
python {baseDir}/scripts/extract_screenshots.py '<笔记.md>' '<视频文件或URL>'
```

脚本用 ffmpeg 按时间戳截图,把标记替换为 `![](images/screenshot_xxx.jpg)`,就地更新笔记(或 `-o` 另存)。视频可为本地路径或 URL(URL 自动下载)。无 ffmpeg 或某帧失败时保留占位。

## 输出规范

- **中文**撰写;专有名词 / 技术术语 / 品牌名 / 人名保留**英文**
- 仅返回 Markdown,**不要**包在代码块里
- 编号标题用 `1\. **内容**`(加反斜杠)或 `## 1. 内容`,避免被误解析为有序列表
- 数学公式用 LaTeX(`$...$` 或 `$$...$$`)
- 末尾可加 `## AI 总结`(若用户要 summary 或风格适用)

## 标记协议(简述)

让 Claude 在 Markdown 中输出约定占位符,供后续替换:

- **原片跳转**:仅在有视频 URL(B站/YouTube)时,章节标题后直接输出可点击链接 `[mm:ss](平台URL?t=秒)`;本地文件/无 URL **不加时间戳**(详见 `prompts/markers.md`)
- **截图占位**:视觉演示段后加 `*Screenshot-[mm:ss]`,如 `*Screenshot-[02:45]`(经 `extract_screenshots.py` 替换为真实图)

完整规则与平台替换表见 `prompts/markers.md`。

## 与其他 skill 的关系

- **`baoyu-youtube-transcript`**:YouTube 字幕兜底。本 skill 已自带 youtube-transcript-api + yt-dlp 下载兜底,被反爬时可改用此 skill。
- 本 skill 已实现 **L0(提示词)+ L1(自动转录)+ L2(下载兜底 + 截图)**,覆盖视频 URL / 本地音视频 / 字幕文本全场景。
