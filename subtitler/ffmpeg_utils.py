"""
FFmpeg discovery, probing, audio extraction and progress-reporting runner.
Uses system FFmpeg from PATH, then the imageio-ffmpeg bundled binary, then common Windows paths.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional


@lru_cache(maxsize=1)
def get_ffmpeg_path() -> str:
    """Finds the FFmpeg executable (PATH -> imageio-ffmpeg -> common Windows locations)."""
    env = os.environ.get("SUBTITLER_FFMPEG")
    if env and os.path.exists(env):
        return env
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    for pattern in (
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe"),
    ):
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    raise RuntimeError("FFmpeg not found! Install FFmpeg or run: pip install imageio-ffmpeg")


@dataclass
class VideoInfo:
    path: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    duration: float = 0.0
    has_audio: bool = False
    video_codec: str = ""
    pix_fmt: str = ""

    @property
    def size(self):
        return (self.width, self.height) if self.width and self.height else None


def probe_video(path: str) -> VideoInfo:
    """Inspect a media file by parsing `ffmpeg -i` output (works without ffprobe)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Media file not found: {path}")
    res = subprocess.run([get_ffmpeg_path(), "-hide_banner", "-i", path],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    err = res.stderr.decode("utf-8", errors="ignore")
    info = VideoInfo(path=path)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info.duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    for line in err.splitlines():
        if "Video:" in line and not info.width:
            mv = re.search(r"Video:\s*(\w+)", line)
            info.video_codec = mv.group(1) if mv else ""
            mp = re.search(r"Video:\s*\w+[^,]*,\s*([a-z0-9_]+)", line)
            info.pix_fmt = mp.group(1) if mp else ""
            ms = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if ms:
                info.width, info.height = int(ms.group(1)), int(ms.group(2))
            mf = re.search(r"([\d.]+)\s*fps", line)
            if mf:
                info.fps = float(mf.group(1))
        if "Audio:" in line:
            info.has_audio = True
    # phone videos: honour rotation metadata
    if re.search(r"rotate\s*:\s*(90|270|-90)", err) or re.search(r"rotation of -?90", err):
        info.width, info.height = info.height, info.width
    return info


def run_ffmpeg(cmd: List[str], duration: Optional[float] = None, label: str = "FFmpeg") -> subprocess.CompletedProcess:
    """
    Run an FFmpeg command, printing percentage progress when ``duration`` is known.
    Returns a CompletedProcess whose ``stderr`` holds the (tail of the) log as text.
    """
    if duration and duration > 0:
        cmd = cmd[:1] + ["-hide_banner", "-nostats", "-progress", "pipe:1"] + cmd[1:]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        import threading
        err_chunks: List[bytes] = []
        t = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
        t.start()
        last = 0.0
        t0 = time.time()
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="ignore").strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    cur = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    continue
                pct = min(100.0, cur / duration * 100)
                if pct - last >= 5 or pct >= 100:
                    last = pct
                    elapsed = time.time() - t0
                    eta = elapsed / max(pct, 0.1) * (100 - pct)
                    print(f"[{label}] {pct:5.1f}%  elapsed {elapsed:5.0f}s  eta {eta:5.0f}s", flush=True)
        proc.wait()
        t.join(timeout=5)
        stderr = b"".join(err_chunks).decode("utf-8", errors="ignore")
        return subprocess.CompletedProcess(cmd, proc.returncode, "", stderr[-6000:])
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return subprocess.CompletedProcess(cmd, res.returncode, "",
                                       res.stderr.decode("utf-8", errors="ignore")[-6000:])


def extract_audio(video_path: str, output_audio_path: Optional[str] = None, sample_rate: int = 16000) -> str:
    """Extract 16 kHz mono PCM WAV from a video file."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if output_audio_path is None:
        base, _ = os.path.splitext(video_path)
        output_audio_path = f"{base}_audio_16k.wav"
    cmd = [get_ffmpeg_path(), "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
           "-ar", str(sample_rate), "-ac", "1", output_audio_path]
    res = run_ffmpeg(cmd, duration=None, label="Audio")
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed:\n{res.stderr}")
    return output_audio_path


def extract_frame(video_path: str, at_seconds: float, output_image: str) -> str:
    """Grab a single frame (fast input seeking)."""
    cmd = [get_ffmpeg_path(), "-y", "-ss", f"{at_seconds:.3f}", "-i", video_path,
           "-frames:v", "1", "-q:v", "2", output_image]
    res = run_ffmpeg(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Frame extraction failed:\n{res.stderr}")
    return output_image


def ensure_utf8_stdio() -> None:
    """Windows consoles default to GBK/cp936 and crash on Japanese / emoji output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream and (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
