---
name: video-subtitler
description: >-
  Transcribes speech from video or audio files, generates synchronized subtitles (SRT, ASS, VTT),
  and burns hard subtitles directly into the output video using faster-whisper, FFmpeg, and a modular
  plugin system (LLM proofreading, bilingual translations, viral/shorts style templates).
  Activate this skill whenever the user asks to transcribe a video/audio, generate subtitles,
  burn hard subtitles, or create a subtitled video from a file.
---

# Video-Subtitler Skill

This skill provides an automated, plugin-powered workflow to transcribe audio/video files, generate subtitles, apply styling presets, and burn them onto video directly on the user's machine.

## When to Use

Activate this skill when the user:
- Requests subtitles for a local video or audio file (e.g. "帮我给这个视频加字幕", "打字幕", "生成带字幕的视频").
- Wants to burn hard subtitles directly into a video (`.mp4`).
- Wants styled subtitles (Bilibili standard, TikTok/Shorts punchy yellow, cinema style, or bilingual dual-row).
- Wants to extract an `.srt`, `.ass`, or `.vtt` file.

---

## Tool Location & Execution

The core CLI tool is located at:
`C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler`

### Execution Command

```powershell
python -m subtitler "<VIDEO_OR_AUDIO_PATH>" [OPTIONS]
```

### Options Guide

| Goal | Command Example |
| :--- | :--- |
| **Default (SRT + Burn Video)** | `python -m subtitler "D:\video.mp4"` |
| **Shorts / TikTok Viral Style** | `python -m subtitler "D:\video.mp4" --style shorts_punchy` |
| **Bilibili / YouTube High Contrast**| `python -m subtitler "D:\video.mp4" --style bilibili_standard` |
| **AI LLM Proofreading** | `python -m subtitler "D:\video.mp4" --proofread` |
| **Bilingual Subtitles (e.g. English)**| `python -m subtitler "D:\video.mp4" --translate en --style dual_contrast` |
| **Domain Knowledge Base (e.g. Gaming)**| `python -m subtitler "D:\video.mp4" --kb gaming_nintendo` |
| **Subtitles Only (No video burn)** | `python -m subtitler "D:\video.mp4" --no-burn` |

---

## Workflow Steps for the Agent

1. **Locate the Input File**:
   Ensure the video/audio path exists on the user's filesystem.
2. **Determine Parameters**:
   - Check if user wants a specific style (e.g. "短视频风格" -> `--style shorts_punchy`, "双语字幕" -> `--translate en --style dual_contrast`).
   - Check if user asked to fix homophones or proofread -> `--proofread`.
   - If user only wants the subtitle file -> `--no-burn`.
3. **Execute the Subtitler**:
   Run the command with Cwd set to `C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler`.
4. **Respond to the User**:
   Provide clickable markdown file links to:
   - The generated subtitle file: `[subtitles.srt](file:///path/to/video.srt)`
   - The subtitled video file: `[video_subtitled.mp4](file:///path/to/video_subtitled.mp4)`
