"""
FFmpeg hardsub burning module.
Encodes styled subtitles directly into the video stream.
"""

import os
import subprocess
from typing import Optional
from subtitler.ffmpeg_utils import get_ffmpeg_path


def format_ffmpeg_filter_path(path: str) -> str:
    """
    FFmpeg filter graph requires escaping for Windows paths:
    Replace '\\' with '/', and escape ':' as '\\:'.
    For example: 'C:\\Users\\...' -> 'C\\:/Users/...'
    """
    abs_path = os.path.abspath(path).replace("\\", "/")
    # Escape colon for drive letter, e.g. C: -> C\:
    if len(abs_path) > 1 and abs_path[1] == ":":
        abs_path = abs_path[0] + "\\:" + abs_path[2:]
    return abs_path


def is_nvenc_available() -> bool:
    """Check if NVIDIA NVENC hardware encoding is available."""
    try:
        ffmpeg = get_ffmpeg_path()
        res = subprocess.run(
            [ffmpeg, "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return res.returncode == 0
    except Exception:
        return False


def burn_subtitles_to_video(
    video_path: str,
    subtitle_path: str,
    output_video_path: Optional[str] = None,
    use_nvenc: Optional[bool] = None,
    crf: int = 22,
    preset: str = "fast"
) -> str:
    """
    Burns subtitles into the video file using FFmpeg.
    
    :param video_path: Path to input video
    :param subtitle_path: Path to .srt or .ass file
    :param output_video_path: Path to destination video (defaults to [name]_subtitled.mp4)
    :param use_nvenc: Whether to use NVIDIA NVENC hardware encoder (h264_nvenc)
    :param crf: Constant Rate Factor (18-28, default 22 for crisp quality)
    :param preset: Encoding speed preset
    :return: Path to output video
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(subtitle_path):
        raise FileNotFoundError(f"Subtitle not found: {subtitle_path}")

    if output_video_path is None:
        base, ext = os.path.splitext(video_path)
        output_video_path = f"{base}_subtitled{ext}"

    ffmpeg = get_ffmpeg_path()
    escaped_sub_path = format_ffmpeg_filter_path(subtitle_path)

    # Determine filter based on extension
    _, sub_ext = os.path.splitext(subtitle_path)
    if sub_ext.lower() == ".ass":
        vf_filter = f"ass='{escaped_sub_path}'"
    else:
        # For SRT, inject modern readable styling
        style = (
            "Fontname=Microsoft YaHei,Fontsize=18,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=25"
        )
        vf_filter = f"subtitles='{escaped_sub_path}':force_style='{style}'"

    cmd = [
        ffmpeg,
        "-y",
        "-i", video_path,
        "-vf", vf_filter,
    ]

    if use_nvenc is None:
        use_nvenc = is_nvenc_available()
        if use_nvenc:
            print("[Burner] Detected NVIDIA GPU. Using NVENC hardware acceleration (h264_nvenc)...")

    if use_nvenc:
        cmd.extend([
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-cq", str(crf),
        ])
    else:
        cmd.extend([
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
        ])

    cmd.extend([
        "-c:a", "copy",
        output_video_path
    ])

    print(f"[Burner] Burning subtitles into {os.path.basename(output_video_path)}...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err_msg = result.stderr.decode("utf-8", errors="ignore")
        # If NVENC failed, try fallback to libx264
        if use_nvenc and "h264_nvenc" in err_msg:
            print("[Burner] NVENC failed, retrying with CPU libx264...")
            return burn_subtitles_to_video(
                video_path,
                subtitle_path,
                output_video_path,
                use_nvenc=False,
                crf=crf,
                preset=preset
            )
        raise RuntimeError(f"FFmpeg burning failed:\n{err_msg}")

    print(f"[Burner] Successfully generated subtitled video: {output_video_path}")
    return output_video_path
