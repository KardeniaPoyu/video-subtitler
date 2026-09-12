# 🎬 Video-Subtitler (视频自动打字幕与硬字幕压制工具)

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Whisper](https://img.shields.io/badge/Powered%20By-Faster--Whisper-orange)](https://github.com/SYSTRAN/faster-whisper)
[![Antigravity Skill](https://img.shields.io/badge/Antigravity-Skill%20Ready-purple)](./SKILL.md)

[English](#english) | [中文说明](#中文说明)

---

<a name="中文说明"></a>
## 🇨🇳 中文说明

**Video-Subtitler** 是一款轻量、高速、开箱即用的 AI 视频字幕自动生成与硬字幕压制工具。基于 `faster-whisper`（比原版 OpenAI Whisper 快 4 倍且占用仅 1/3 显存）与 `FFmpeg` 打造，支持从视频中自动识别语音、生成时间轴字幕（SRT / ASS / VTT），并可直接把美化后的硬字幕烧录进视频画面中，一键输出成品视频。

同时原生支持作为 **Antigravity AI Agent 专属 Skill**，让你在与 AI 对话时发送视频路径，AI 即可全自动帮你生成带字幕的视频！

### ✨ 核心特性

- 🚀 **极速转写**：基于 CTranslate2 的 `faster-whisper`，自动支持 NVIDIA CUDA GPU 加速与 CPU `int8` 极速量化。
- 📦 **免繁琐配置**：内置 FFmpeg 自动探测与 `imageio-ffmpeg` 回退机制，**无需手动安装或配置系统环境变量**，插拔即用。
- 🎨 **精美字幕样式**：支持生成标准 `.srt`、`.vtt` 以及带描边阴影的高对比度 `.ass` 字幕，避免白色文字在亮色背景下看不清。
- 🎬 **一键压制成片**：提取音频 $\to$ 语音识别 $\to$ 生成字幕 $\to$ 压制硬字幕合并成新视频（音频流无损复制，画面快速编码）。
- 🤖 **AI Agent 技能集成**：自带 `SKILL.md`，可作为 Google Antigravity 的原生技能加载，随时在对话中驱动。

---

### 🛠️ 快速安装

```bash
git clone https://github.com/your-username/video-subtitler.git
cd video-subtitler

pip install -r requirements.txt
```

---

### 💻 命令行使用 (CLI)

#### 1. 一键全自动（生成字幕并压制成新视频）
```bash
# 默认使用 small 模型（平衡速度与准确度），自动检测语言并压制视频
python -m subtitler "D:\videos\my_video.mp4"
```
完成后会在同一目录下生成：
- `my_video.srt`（时间轴字幕）
- `my_video_subtitled.mp4`（压好字幕的最终视频）

#### 2. 指定语言与模型大小
```bash
# 使用中文 zh，中等 medium 模型获得更高识别精度
python -m subtitler "D:\videos\presentation.mp4" -l zh -m medium
```

#### 3. 仅生成字幕文件，不重新压制视频
```bash
python -m subtitler "D:\videos\podcast.mp4" --no-burn
```

#### 4. 生成精美样式的 ASS 字幕并压制
```bash
python -m subtitler "D:\videos\vlog.mp4" --format ass
```

#### 常用参数说明：
| 参数 | 缩写 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `video_path` | - | 必填 | 输入的视频文件路径 |
| `--model` | `-m` | `small` | 模型大小：`tiny`, `base`, `small`, `medium`, `large-v3` |
| `--lang` | `-l` | 自动检测 | 语言代码：如 `zh` (中文), `en` (英语), `ja` (日语) 等 |
| `--no-burn` | - | False | 只生成字幕文件，不重新压制输出视频 |
| `--format` | - | `srt` | 字幕格式：`srt`, `ass`, `vtt` |
| `--output-video` | `-o` | 自动命名 | 自定义输出视频路径 |
| `--output-subtitle` | `-s` | 自动命名 | 自定义输出字幕路径 |
| `--prompt` | - | 无 | 初始提示词（用于专业术语、人名提示或纠偏） |

---

### 🐍 Python 代码调用

你也可以将本项目作为 Python 库集成到自己的工程中：

```python
from subtitler import process_video

result = process_video(
    video_path=r"D:\videos\demo.mp4",
    model_size="small",
    language="zh",
    burn=True,          # 烧录进视频
    subtitle_format="srt"
)

print("字幕路径:", result["subtitle_path"])
print("压制后视频路径:", result["video_path"])
print("总字幕段数:", result["segment_count"])
```

---

<a name="english"></a>
## 🌐 English

**Video-Subtitler** is a lightweight, high-performance, and out-of-the-box tool for automatic video transcription, subtitle generation (SRT/ASS/VTT), and hardsub burning. Powered by `faster-whisper` and `FFmpeg`.

### Quickstart

```bash
# Clone and install
git clone https://github.com/your-username/video-subtitler.git
cd video-subtitler
pip install -r requirements.txt

# Run CLI
python -m subtitler "path/to/video.mp4" --model small --burn
```

---

## 🤖 Antigravity AI Agent Skill Usage

本项目已原生封装 Antigravity Agent Skill 规范。

你可以直接将项目中的 `SKILL.md` 放置在全局技能目录：
```text
~/.gemini/config/skills/video-subtitler/SKILL.md
```
之后只需在 Antigravity 中对 AI 说：
> *“帮我把 D:\videos\meeting.mp4 提取字幕并压制成新视频”*

AI 将会自动调用此模块完成端到端任务！

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
