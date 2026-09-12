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

**Video-Subtitler** 是一款轻量、高速、高度可扩展的**下一代 AI 视频字幕自动生成与硬字幕压制工具**。不同于传统沉重笨拙的桌面工具或单一功能的脚本，本项目采用**微内核 + 可扩展插件化架构**，不仅支持毫秒级语音转录与硬字幕渲染，更内建了 **LLM 智能同音字纠错**、**上下文感知双语翻译**与**短视频爆款视觉模板**。

原生支持作为 **Antigravity / Cursor / Claude Code AI Agent 技能**，让 AI 助手在对话中即可全自动处理视频并压制交付！

---

### 🌟 核心差异化与优势对比

| 维度 / 特性 | 传统高星项目 (`pyvideotrans`, `auto-subtitle`) | 🔬 **Video-Subtitler (本项目)** |
| :--- | :--- | :--- |
| **系统架构** | 臃肿庞大的桌面客户端 (数百MB/几个G) 或僵化单脚本 | **微内核 + 插件体系** (`subtitler.plugins`)，极其轻巧灵活 |
| **AI Agent 原生** | ❌ 无，只能人工在界面反复点选 | ✅ **自带 Antigravity Skill**，自然语言对话即可调度完成 |
| **同音字错别字** | ❌ 无法解决 ASR 同音错字、专有名词乱码 | ✅ **LLM Proofreader 插件**，智能上下文纠偏与标点规范 |
| **双语字幕制作** | ⚠️ 僵硬逐句机翻，缺少上下文，双语排版难调 | ✅ **上下文双语翻译插件**，自动生成上下双层对齐字幕 |
| **视觉样式模板** | ⚠️ 默认仅支持简陋白字 | ✅ **内置预设视觉模板**（B站/YouTube清晰风、TikTok爆款高对比、电影极简风） |
| **跨平台零配置** | ⚠️ 需手动配置庞大的系统级 FFmpeg 路径 | ✅ **智能双重探测**，自带嵌入式静态二进制回退，开箱即用 |

---

### 🧩 插件化架构 (Plugin Architecture)

```
                       ┌───────────────────────┐
                       │   Input Video/Audio   │
                       └───────────┬───────────┘
                                   │
                       ┌───────────▼───────────┐
                       │     FFmpeg Engine     │  (Zero-config detection)
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

#### 2. 使用短视频爆款黄色高对比模板（TikTok / Reels / 抖音）
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

### 🔌 编写你自己的插件

编写新插件只需继承 `PostProcessPlugin` 或 `TranslationPlugin`：

```python
from subtitler.plugins.base import PostProcessPlugin
from subtitler.asr import SubtitleSegment
from typing import List

class CensorFilterPlugin(PostProcessPlugin):
    name = "censor_filter"
    description = "过滤敏感词或替换指定专有名词"

    def process(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        for seg in segments:
            seg.text = seg.text.replace("badword", "***")
        return segments
```

---

<a name="english"></a>
## 🌐 English

**Video-Subtitler** is a lightweight, extensible, and plugin-driven AI subtitling and hardsub-burning engine powered by `faster-whisper`, `FFmpeg`, and modern LLM refinement plugins.

### Highlights
- **Plugin Ecosystem**: Pluggable post-processing, LLM homophone proofreading, bilingual translations, and visual templates.
- **Zero-Config FFmpeg**: Automated binary detection and fallback.
- **AI Agent Skill Native**: Equipped with `SKILL.md` for seamless tool use in Antigravity or other agent environments.

### Quickstart
```bash
git clone https://github.com/KardeniaPoyu/video-subtitler.git
cd video-subtitler
pip install -r requirements.txt

# Run with punchy TikTok-style subtitles
python -m subtitler "path/to/video.mp4" --style shorts_punchy
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
