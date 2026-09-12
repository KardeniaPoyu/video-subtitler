"""
FFmpeg discovery and audio extraction utilities.
Supports system FFmpeg in PATH or automatic fallback to imageio-ffmpeg binary.
"""

import os
import shutil
import subprocess
from typing import Optional


def get_ffmpeg_path() -> str:
    """
    Finds the FFmpeg executable path.
    Checks system PATH first, then imageio-ffmpeg, or raises RuntimeError.
    """
    # 1. Check system PATH
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg

    # 2. Check imageio-ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except ImportError:
        pass

    # 3. Check common Windows paths
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-*\bin\ffmpeg.exe"),
    ]
    for p in common_paths:
        import glob
        matches = glob.glob(p)
        if matches and os.path.exists(matches[0]):
            return matches[0]

    raise RuntimeError(
        "FFmpeg not found! Please install FFmpeg or run: pip install imageio-ffmpeg"
    )


def extract_audio(
    video_path: str,
    output_audio_path: Optional[str] = None,
    sample_rate: int = 16000
) -> str:
    """
    Extracts 16kHz mono WAV audio from a video file using FFmpeg.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if output_audio_path is None:
        base, _ = os.path.splitext(video_path)
        output_audio_path = f"{base}_audio_16k.wav"

    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg,
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", "1",
        output_audio_path
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed:\n{result.stderr.decode('utf-8', errors='ignore')}")

    return output_audio_path
