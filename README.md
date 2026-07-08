# video-note-skill

> 一个 Agent Skill:把视频 / 音频 / 字幕自动转换成结构化的中文 Markdown 笔记,支持多风格、原片跳转、自动嵌入截图。

## 它是什么

`video-note` 借鉴 [BiliNote](https://github.com/JinYangBao/BiliNote) 的视频笔记流程,提炼出**最轻量、最核心**的部分封装成一个 Skill:

- **笔记生成由 Claude 自身完成**,不调用任何外部 LLM,**不需要 API Key**
- 依赖从 BiliNote 的 ~130 个 Python 包压缩到 **3 个**(`requests` / `youtube-transcript-api` / `yt-dlp`)
- 覆盖视频 URL、本地音视频、字幕文件全场景

## 核心特性

- 🎬 **自动转录**:YouTube / B站 URL 字幕直取;无字幕则自动下载音频走云端 ASR;抖音公开视频下载音频后 ASR,必要时自动尝试浏览器 fresh cookie(bcut / kuaishou,免 Key)
- ✍️ **9 种笔记风格**:详细 / 精简 / 小红书爆款 / 学术 / 教程 / 生活向 / 任务导向 / 商业 / 会议纪要
- 🔗 **原片跳转**:B站 / YouTube URL 场景,章节标题自动带可点击跳转链接
- 🖼️ **自动截图**:笔记里的截图标记用 ffmpeg 替换为视频对应帧
- 🪶 **三层渐进架构**:L0 纯提示词(零依赖)→ L1 自动转录 → L2 下载兜底 + 截图

## 安装

### 方式一:对话式安装(推荐)

直接对你正在用的 AI 助手(Claude Code / Codex 等)说一句:

> 帮我安装这个 Skill:https://github.com/yilane/video-note-skill

AI 会自动判断你当前使用的 agent 工具的全局 skill 目录并完成安装。它会:

1. **定位全局 skill 目录**(按 agent 工具,自动检测):
   | Agent 工具 | 全局 skill 目录 |
   |---|---|
   | Claude Code | `~/.claude/skills/` |
   | Codex | `~/.codex/skills/` |
   | 其他 | 该工具约定的 skills 目录 |
2. `git clone` 到该目录下的 `video-note-skill/`
3. `pip install -r .../scripts/requirements.txt`
4. 检查 `ffmpeg`(本地视频转录 / 截图需要)

### 方式二:手动安装

```bash
# <SKILL_DIR> = 你的 agent 全局 skill 目录(见上表)
git clone https://github.com/yilane/video-note-skill.git <SKILL_DIR>/video-note-skill
pip install -r <SKILL_DIR>/video-note-skill/scripts/requirements.txt
```

> 本地视频转录 / 截图还需系统 `ffmpeg`:`winget install ffmpeg`(Windows)/ `brew install ffmpeg`(macOS)/ `apt install ffmpeg`(Linux)。

## 用法

对 Claude 说:

- 「帮我把这个视频整理成笔记:<URL>」
- 「这个 B站视频做成详细笔记」
- 「把这段字幕整理成小红书风格」

Claude 会自动触发 skill:获取转录 → 选风格 → 生成笔记 →(可选)嵌入截图。

## 能力矩阵

| 输入 | 支持 | 方式 |
|---|---|---|
| YouTube / B站 URL | ✅ | 字幕直取 + 下载兜底(B站 dm_patch 绕过 412) |
| 抖音 URL | ✅ | 默认免登录解析公开视频,失败时自动尝试 Chrome/Edge fresh cookie;可用 DOUYIN_COOKIE 兜底 |
| 本地音视频文件 | ✅ | ffmpeg 提音频 + bcut 云端 ASR |
| 字幕文件(.srt / .vtt)/ 粘贴文本 | ✅ | 直接解析 |
| 快手等其他平台 | ❌ | 暂未内置自动解析(可手动下载音频后走 ASR) |

## 目录结构

```
video-note-skill/
├── SKILL.md                    # 入口(触发词 + 工作流)
├ prompts/                      # 提示词层(L0)
│   ├── base.md                 # 通用底座
│   ├── markers.md              # 跳转/截图标记协议
│   └── styles/                 # 9 种风格
├── scripts/                    # 代码层(L1/L2)
│   ├── fetch_transcript.py     # 转录入口(智能路由)
│   ├── extract_screenshots.py  # 截图后处理
│   ├── bili_patch.py           # B站 412 风控 patch
│   ├── downloader.py           # yt-dlp 下载封装
│   └── sources/                # youtube / bilibili / bcut / kuaishou
└── references/data-contract.md
```

## 设计要点

- **Claude 即 LLM**:笔记生成不用任何 LLM SDK,提示词作为 `prompts/` 文件由 Claude 在触发时组合套用,省掉分块 / 合并 / 重试 / checkpoint 等工程代码
- **提示词工程是核心资产**:9 种风格 + 标记协议移植自 BiliNote 并做了改进(废弃易泄漏的 `*Content-` 占位符)
- **轻量转录路径**:字幕直取 + bcut/kuaishou 云端 ASR(免 Key),替代 BiliNote 的 faster-whisper 重型本地模型
- **B站风控**:移植 BiliNote 的 dm_img patch 绕过 412,免 cookie 下载

## 致谢

核心思路与提示词资产移植自 **BiliNote** 项目。本 skill 去掉了它的全栈工程(FastAPI / DB / Celery / RAG / 前端 / 插件),只保留提示词工程 + 轻量转录路径,并把笔记生成交给 Claude 自身。

## License

MIT
