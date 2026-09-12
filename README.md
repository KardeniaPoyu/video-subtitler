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

### 🔬 核心工程方法论：六阶字幕复核流水线 (6-Stage Verification Pipeline)

在面对游戏、动漫、科技前沿、学术讲座等高密度领域视频时，单纯依靠端到端 ASR + 逐句机翻无法满足专业发布要求。**Video-Subtitler** 沉淀了一套严密的**六阶复核方法论**：

```mermaid
graph TD
    A["Stage 1: 声学先验注入 (ASR Hotwords Conditioning)"] --> B["Stage 2: 画面字卡跨模态校验 (Telop / OCR Cross-Check)"]
    B --> C["Stage 3: 音素映射与专名纠偏 (Phonetic & Domain Alignment)"]
    C --> D["Stage 4: 滑动窗口语境审校 (Contextual LLM Proofreading)"]
    D --> E["Stage 5: 排版边界与安全距离复核 (Typographic & Boundary Audit)"]
    E --> F["Stage 6: 关键帧视觉抽检 (Visual Spot-Check & Smoke Test)"]
```

1. **Stage 1: 声学先验注入 (ASR Hotwords Conditioning)**：提取领域核心专有名词注入 Whisper `initial_prompt`，从底层偏置声学校验，大幅降低冷门片假名与术语漏识别率。
2. **Stage 2: 画面字卡跨模态校验 (Telop / OCR Cross-Check)**：针对语速极快或混杂 BGM 的片段，若视频画面带有作者自带原文字卡（如游戏关卡名、角色名），以视觉 OCR 为基准地面真值校正听觉误差。
3. **Stage 3: 音素映射与专名纠偏 (Phonetic & Domain Alignment)**：挂载领域专库（如任天堂全家桶、卡比宇宙、AI 技术栈），通过音素失真表与正则置换，强制锁定官方标准译名（例：杜绝将“プププランド”误听为“台北”）。
4. **Stage 4: 滑动窗口语境审校 (Contextual LLM Proofreading)**：杜绝单句孤立翻译，向大模型传入前后 5~10 句上下文窗口，理解叙事逻辑与说话人口吻，消灭离谱幻觉机翻，润色为符合当代中文互联网语感的自然口语。
5. **Stage 5: 排版边界与安全距离复核 (Typographic & Boundary Audit)**：
   - **字数上限**：单行严格限制 20~22 中文字符（约 40 英文字符）；
   - **语义断行**：禁止在英文单词/数字中硬拆，仅在标点、助词与语义顿挫处折行；
   - **贴边视觉基准**：默认采用贴边距离（1080p 画布下 `MarginV: 45~50`），保持画面开阔清爽；当遇到底部密集信息条时，支持无缝切换至避让高度（`MarginV: 180~200`）。
6. **Stage 6: 关键帧视觉抽检 (Visual Spot-Check & Smoke Test)**：成片导出前，自动截取多时间轴关键帧，人工/智能多模态抽检双语对齐、字体描边对比度与贴边舒适度。

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

#### 3. 挂载领域知识库与术语库（消除专有名词机翻与口误）
```bash
# 挂载游戏与任天堂专库（精准识别《星之卡比》、Switch 2、游戏黑话）
python -m subtitler "D:\videos\game_direct.mp4" --kb gaming_nintendo --translate zh

# 挂载科技与大模型专库（精准识别 LLM, PyTorch, LoRA, CUDA 等）
python -m subtitler "D:\videos\ai_talk.mp4" --kb tech_ai

# 挂载动漫与 ACG 专库
python -m subtitler "D:\videos\anime_review.mp4" --kb anime_acg
```

---

### 📚 领域知识库与术语增强系统 (Knowledge Base & Glossary System)

针对语音识别与机翻中最致命的**专有名词识别错误**（如将《星之卡比》听成“卡比/星辰小宝”，将“完全新作”听成“感转进削”），本项目构建了双重知识库增强体系：

1. **ASR 识别前注入（Hotwords Injection）**：自动提取领域高频专有名词，注入 Whisper 的 `initial_prompt`，从源头提高识别准确率；
2. **同音错词自愈（Phonetic Error Correction）**：基于发音失真映射表，自动校正 ASR 转写文本；
3. **权威术语表强制对齐（Glossary Alignment）**：翻译时严格锁定官方标准中文译名，彻底告别离谱机翻。

| 内置知识库 | 涵盖领域 | 核心词条举例 |
| :--- | :--- | :--- |
| `gaming_nintendo.json` | 游戏、任天堂全家桶、卡比、主机 | 星之卡比、探索发现、超越世界、Switch 2、任天堂直面会、大招压轴 |
| `tech_ai.json` | 人工智能、大语言模型、软件工程 | ChatGPT、DeepSeek、Faster-Whisper、LoRA量化、模型推理、上下文窗口 |
| `anime_acg.json` | 动漫番剧、声优、制作委员会、网梗 | 京都动画、ufotable、圣地巡礼、异世界转生、作画崩坏、封神名回 |
| `vlogger_slang.json` | 视频博主、自媒体、直播杂谈黑话 | 一键三连、订阅点赞、切片剪辑、游戏实况、生放送、高评价 |

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
