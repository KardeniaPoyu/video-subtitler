# 🎬 Video-Subtitler: Plugin-Powered AI Subtitle & Hardsub Engine

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Whisper](https://img.shields.io/badge/Powered%20By-Faster--Whisper-orange)](https://github.com/SYSTRAN/faster-whisper)
[![Architecture](https://img.shields.io/badge/Architecture-Plugin--Driven-blueviolet)](#-插件化架构-plugin-architecture)
[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill%20Ready-purple)](./SKILL.md)

[English](#english) | [中文说明](#中文说明)

---

<a name="中文说明"></a>
## 🇨🇳 中文说明

**Video-Subtitler** 是一款轻量、高速、模块化的 **AI 视频字幕生成与硬字幕压制引擎**。

开源社区中已有许多优秀的字幕工具（如功能全面的桌面端 GUI 工具 `pyvideotrans`，经典的命令行工具 `auto-subtitle`，以及擅长词级对齐的 `whisperX`）。**Video-Subtitler** 的定位则专注于：
1. **轻量微内核与插件化扩展**（模块化接入 AI 润色、双语翻译与视觉样式）；
2. **AI Agent 生态原生集成**（作为 Antigravity / Cursor / Claude Code 的对话技能与 MCP 工具直接调度）；
3. **开箱即用的自动化压制体验**（自动环境探测、高质量断句排版与视觉模板）。

---

### 🎯 设计取向与生态定位对比

| 维度 / 取向 | 桌面 GUI 交互类工具 (如 `pyvideotrans`) | 基础 CLI 类工具 (如 `auto-subtitle`) | 🔬 **Video-Subtitler (本项目)** |
| :--- | :--- | :--- | :--- |
| **主要定位** | 独立图形界面，适合无终端经验的桌面用户直观操作 | 极简转录压制，适合基础命令行流水线 | **轻量微内核 + 插件总线**，兼顾 CLI 与 AI Agent 自动化驱动 |
| **Agent 协作** | 依赖鼠标手动交互，不易被智能体直接调度 | 需自定义封装驱动 | **原生内置 Skill 规范**，自然语言直接下发任务并交付成品 |
| **扩展机制** | 模块与 GUI 深度耦合 | 功能相对单一固定 | **插件化微内核** (`subtitler.plugins`)，后处理、翻译与样式可自由拔插 |
| **文本与样式** | 提供界面配置项，依赖用户手动微调 | 输出默认字体排版 | **内置爆款模板与 LLM 校对插件**，支持同音字自愈与双语排版 |
| **部署与依赖** | 需下载较完整的应用运行环境 | 依赖系统全局安装的 FFmpeg | **智能双轨探测**，支持系统环境与内嵌便携执行文件自动回退 |

---

### 🧩 插件化架构 (Plugin Architecture)

```
                       ┌───────────────────────┐
                       │   Input Video/Audio   │
                       └───────────┬───────────┘
                                   │
                       ┌───────────▼───────────┐
                       │     FFmpeg Engine     │  (Auto-detection & portable fallback)
                       └───────────┬───────────┘
                                   │
                       ┌───────────▼───────────┐
                       │ Faster-Whisper (ASR)  │  (CUDA / CPU int8)
                       └───────────┬───────────┘
                                   │
         ═════════════════════ Plugin Bus ═════════════════════
           │                                             │
   ┌───────▼─────────────────┐               ┌───────────▼─────────────┐
   │  LLM Proofreader Plugin │               │ LLM Translator Plugin   │
   │  • 同音字与专有名词纠偏 │               │ • 上下文感知双语字幕    │
   │  • 口吃停顿字平滑处理   │               │ • 双层对齐渲染          │
   └─────────────────────────┘               └─────────────────────────┘
                                   │
         ══════════════════════════════════════════════════════
                                   │
                       ┌───────────▼───────────┐
                       │  StyleTemplate Engine │  (bilibili / shorts / cinema)
                       └───────────┬───────────┘
                                   │
                       ┌───────────▼───────────┐
                       │ Hardsub Video Burner  │
                       └───────────┬───────────┘
                                   │
                       ┌───────────▼───────────┐
                       │  Subtitled Video MP4  │
                       └───────────────────────┘
```

---

### 🛠️ 快速安装

```bash
git clone https://github.com/KardeniaPoyu/video-subtitler.git
cd video-subtitler

pip install -r requirements.txt
```

---

### 💻 命令行玩法 (CLI)

#### 1. 一键全自动（生成字幕并压制成新视频）
```bash
python -m subtitler "D:\videos\demo.mp4"
```

#### 2. 使用短视频高对比模板（TikTok / Reels / 抖音）
```bash
python -m subtitler "D:\videos\vlog.mp4" --style shorts_punchy
```

#### 3. 启用 AI 大模型校对纠错（修正同音字、专有名词与标点）
```bash
# 设置任意 OpenAI 兼容的 API Key（支持 DeepSeek, OpenAI, Groq, Ollama 等）
set OPENAI_API_KEY=your_key_here
python -m subtitler "D:\videos\interview.mp4" --proofread
```

#### 4. 生成双语双层字幕（如中英双语）
```bash
python -m subtitler "D:\videos\lecture.mp4" --translate en --style dual_contrast
```

#### 5. 仅生成字幕文件，不重新压制视频
```bash
python -m subtitler "D:\videos\podcast.mp4" --no-burn
```

---

### 🎨 内置视觉风格模板一览

| 模板名称 | 风格特征 | 推荐场景 |
| :--- | :--- | :--- |
| `default` | 纯白加粗 + 2px 纯黑外描边，下中对齐 | 通用视频、日常记录 |
| `bilibili_standard` | 大字号高对比加粗 + 深黑粗描边 | B站 / YouTube 知识科普、科技数码 |
| `shorts_punchy` | 炫彩醒目金黄 + 4px 粗描边 + 底部抬升 | 抖音、TikTok、YouTube Shorts、Reels |
| `cinema_minimal` | 宋体/衬线微弱阴影、经典电影下沉微距 | 影视解说、微电影、纪录片 |
| `dual_contrast` | 双层对比对齐排版（上层母语，下层译文） | 跨国演讲、双语教程、影视外语翻译 |

---

### 🔌 编写自定义插件

只需继承 `PostProcessPlugin` 或 `TranslationPlugin` 即可接入插件流：

```python
from subtitler.plugins.base import PostProcessPlugin
from subtitler.asr import SubtitleSegment
from typing import List

class CustomFilterPlugin(PostProcessPlugin):
    name = "custom_filter"
    description = "自定义过滤或替换指定关键词"

    def process(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        for seg in segments:
            seg.text = seg.text.replace("旧词", "新词")
        return segments
```

---

<a name="english"></a>
## 🌐 English

**Video-Subtitler** is a lightweight, extensible, and plugin-driven AI subtitling and hardsub-burning engine designed for developers and AI Agent workflows.

### Highlights
- **Plugin-Driven Architecture**: Clean micro-kernel supporting pluggable post-processing, LLM homophone proofreading, bilingual translation, and aesthetic styling.
- **Agent-Ready**: Native Antigravity skill specification for seamless invocation via natural language.
- **Zero-Config Portability**: Automatic environment detection and bundled portable fallback.

### Quickstart
```bash
git clone https://github.com/KardeniaPoyu/video-subtitler.git
cd video-subtitler
pip install -r requirements.txt

# Run with punchy viral subtitles
python -m subtitler "path/to/video.mp4" --style shorts_punchy
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
