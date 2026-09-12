---
name: video-subtitler
description: >-
  Transcribes speech from video or audio files, generates synchronized subtitles (SRT, ASS, VTT),
  and burns hard subtitles directly into the output video using faster-whisper and FFmpeg.
  Activate this skill whenever the user asks to transcribe a video/audio, generate subtitles,
  burn hard subtitles, or create a subtitled video from a file.
---

# Video-Subtitler Skill

This skill provides an automated workflow to transcribe audio/video files, generate subtitles, and burn them onto the video directly on the user's machine.

## When to Use

Activate this skill when the user:
- Requests subtitles for a local video or audio file (e.g. "帮我给这个视频加字幕", "打字幕", "生成带字幕的视频").
- Wants to burn hard subtitles directly into a video (`.mp4`).
- Wants to extract an `.srt`, `.ass`, or `.vtt` file from an audio/video file.

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
| **Default (Generate SRT + Burn Video)** | `python -m subtitler "D:\video.mp4"` |
| **High Accuracy (Medium model)** | `python -m subtitler "D:\video.mp4" -m medium` |
| **Chinese Specific** | `python -m subtitler "D:\video.mp4" -l zh` |
| **English Specific** | `python -m subtitler "D:\video.mp4" -l en` |
| **Subtitles Only (No video re-encoding)** | `python -m subtitler "D:\video.mp4" --no-burn` |
| **Styled Subtitles (ASS)** | `python -m subtitler "D:\video.mp4" --format ass` |

---

## Workflow Steps for the Agent

1. **Locate the Input File**:
   Ensure the video/audio path exists on the user's filesystem.
2. **Determine Parameters**:
   - If the audio language is known (e.g. Chinese, English), pass `-l <lang>` to accelerate detection and reduce hallucination.
   - For standard 10-30 min videos, the default `small` model is recommended (takes only ~1-2 min). If the user asks for maximum accuracy, use `-m medium` or `-m large-v3`.
   - If the user only wants the subtitle file (e.g., to import into Premiere or CapCut), add `--no-burn`.
3. **Execute the Subtitler**:
   Run the command using `run_command` in `C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler`.
4. **Respond to the User**:
   Provide clickable markdown file links to:
   - The generated subtitle file: `[subtitles.srt](file:///path/to/video.srt)`
   - The subtitled video file: `[video_subtitled.mp4](file:///path/to/video_subtitled.mp4)`
