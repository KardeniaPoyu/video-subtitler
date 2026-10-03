"""
FFmpeg hardsub burning and subtitle preview frames.

Path-escaping for FFmpeg filter graphs is notoriously fragile on Windows (drive colons,
quotes, commas, brackets, CJK). We sidestep it entirely: the subtitle is copied into a temp
directory under a plain ASCII name and FFmpeg runs with that directory as its CWD.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Sequence

from subtitler.ffmpeg_utils import get_ffmpeg_path, probe_video, run_ffmpeg

SRT_FORCE_STYLE = ("Fontname=Microsoft YaHei,Fontsize=18,PrimaryColour=&H00FFFFFF,"
                   "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=12")


def format_ffmpeg_filter_path(path: str) -> str:
    """Escape an absolute path for use inside a single-quoted FFmpeg filter argument (legacy helper)."""
    p = os.path.abspath(path).replace("\\", "/")
    p = p.replace("'", r"'\''")
    if len(p) > 1 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    return p


_nvenc_cache: Optional[bool] = None


def is_nvenc_available() -> bool:
    """Check (once) whether h264_nvenc encoding actually works on this machine."""
    global _nvenc_cache
    if _nvenc_cache is None:
        try:
            res = subprocess.run(
                [get_ffmpeg_path(), "-hide_banner", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                 "-c:v", "h264_nvenc", "-f", "null", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            _nvenc_cache = res.returncode == 0
        except Exception:
            _nvenc_cache = False
    return _nvenc_cache


class _StagedSubtitle:
    """Context manager: copy subtitle (and optional fonts dir) to a temp dir with safe names."""

    def __init__(self, subtitle_path: str, fonts_dir: Optional[str] = None):
        self.subtitle_path = subtitle_path
        self.fonts_dir = fonts_dir

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="subtitler_")
        ext = os.path.splitext(self.subtitle_path)[1].lower() or ".srt"
        self.name = "sub" + ext
        shutil.copyfile(self.subtitle_path, os.path.join(self.tmp, self.name))
        if ext == ".ass":
            vf = f"ass={self.name}"
        else:
            vf = f"subtitles={self.name}:force_style='{SRT_FORCE_STYLE}'"
        if self.fonts_dir and os.path.isdir(self.fonts_dir):
            shutil.copytree(self.fonts_dir, os.path.join(self.tmp, "fonts"))
            vf += ":fontsdir=fonts"
        self.filter = vf
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)


def _encoder_args(use_nvenc: bool, crf: int, preset: str) -> List[str]:
    if use_nvenc:
        # -b:v 0 is required for true constant-quality mode; otherwise NVENC caps bitrate.
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr",
                "-cq", str(crf), "-b:v", "0", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]


def burn_subtitles_to_video(
    video_path: str,
    subtitle_path: str,
    output_video_path: Optional[str] = None,
    use_nvenc: Optional[bool] = None,
    crf: int = 20,
    preset: str = "medium",
    fonts_dir: Optional[str] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> str:
    """
    Burn subtitles into a video.

    :param use_nvenc: True/False to force, None = auto-detect NVIDIA NVENC.
    :param crf: quality (CRF for x264, CQ for NVENC). 18 = visually lossless, 20 default, 23 smaller.
    :param fonts_dir: optional directory with .ttf/.otf fonts referenced by the ASS styles.
    :param start/end: optional time range (seconds) for a quick test clip.
    :return: output video path
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(subtitle_path):
        raise FileNotFoundError(f"Subtitle not found: {subtitle_path}")
    if output_video_path is None:
        base, _ = os.path.splitext(video_path)
        output_video_path = f"{base}_subtitled.mp4"
    output_video_path = os.path.abspath(output_video_path)
    video_path = os.path.abspath(video_path)

    if use_nvenc is None:
        use_nvenc = is_nvenc_available()
    info = probe_video(video_path)
    duration = info.duration
    if start is not None or end is not None:
        duration = (end or info.duration) - (start or 0)

    with _StagedSubtitle(subtitle_path, fonts_dir) as staged:
        clip = start is not None or end is not None

        def build(nvenc: bool, audio_copy: bool) -> List[str]:
            cmd = [get_ffmpeg_path(), "-y"]
            vf = staged.filter
            if clip:
                # fast seek but keep original timestamps so subtitles line up, then rebase to 0
                cmd += ["-ss", f"{start or 0:.3f}", "-copyts", "-i", video_path, "-t", f"{duration:.3f}"]
                vf += ",setpts=PTS-STARTPTS"
            else:
                cmd += ["-i", video_path]
            cmd += ["-vf", vf, "-map", "0:v:0", "-map", "0:a?"]
            cmd += _encoder_args(nvenc, crf, preset)
            if clip:
                cmd += ["-af", "asetpts=PTS-STARTPTS", "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"]
            if output_video_path.lower().endswith((".mp4", ".mov", ".m4v")):
                cmd += ["-movflags", "+faststart"]
            return cmd + [output_video_path]

        attempts = [(use_nvenc, True)] + ([] if clip else [(use_nvenc, False)])
        if use_nvenc:
            attempts += [(False, True)] + ([] if clip else [(False, False)])
        last_err = ""
        for nvenc, acopy in attempts:
            enc = "NVENC h264_nvenc" if nvenc else "CPU libx264"
            print(f"[Burner] Encoding with {enc} -> {os.path.basename(output_video_path)}")
            cwd = os.getcwd()
            os.chdir(staged.tmp)
            try:
                res = run_ffmpeg(build(nvenc, acopy), duration=duration, label="Burn")
            finally:
                os.chdir(cwd)
            if res.returncode == 0:
                print(f"[Burner] Done: {output_video_path}")
                return output_video_path
            last_err = res.stderr
            print(f"[Burner] Attempt failed ({enc}, audio {'copy' if acopy else 'aac'}); retrying...")
        raise RuntimeError(f"FFmpeg burning failed:\n{last_err}")


def pick_preview_times(segments, count: int = 4) -> List[float]:
    """Choose informative checkpoints: evenly spread events + the widest (most overflow-prone) event."""
    from subtitler.wrapper import display_width
    if not segments:
        return []
    n = len(segments)
    idxs = {int(round(i * (n - 1) / max(1, count - 2))) for i in range(max(1, count - 1))}
    widest = max(range(n), key=lambda i: display_width((segments[i].translation or "") + segments[i].text))
    idxs.add(widest)
    times = sorted((segments[i].start + segments[i].end) / 2 for i in idxs)
    return times[:count + 1]


def render_preview_frames(
    video_path: str,
    subtitle_path: Optional[str],
    times: Sequence[float],
    out_dir: str,
    fonts_dir: Optional[str] = None,
    contact_sheet: bool = True,
) -> List[str]:
    """
    Render full-resolution frames with subtitles burned in at the given timestamps
    (fast seek + -copyts so subtitle timing stays correct), plus a 2-column contact sheet.
    ``subtitle_path=None`` grabs raw frames (e.g. cover candidates).
    """
    os.makedirs(out_dir, exist_ok=True)
    video_path = os.path.abspath(video_path)
    out_dir = os.path.abspath(out_dir)
    outputs: List[str] = []
    prefix = "preview" if subtitle_path else "frame"
    for k, t in enumerate(times, 1):
        out = os.path.join(out_dir, f"{prefix}_{k:02d}_{int(t // 60):02d}m{t % 60:04.1f}s.jpg")
        if subtitle_path:
            with _StagedSubtitle(subtitle_path, fonts_dir) as staged:
                cmd = [get_ffmpeg_path(), "-y", "-ss", f"{t:.3f}", "-copyts", "-i", video_path,
                       "-vf", staged.filter, "-frames:v", "1", "-q:v", "2", out]
                cwd = os.getcwd()
                os.chdir(staged.tmp)
                try:
                    res = run_ffmpeg(cmd)
                finally:
                    os.chdir(cwd)
        else:
            res = run_ffmpeg([get_ffmpeg_path(), "-y", "-ss", f"{t:.3f}", "-i", video_path,
                              "-frames:v", "1", "-q:v", "2", out])
        if res.returncode != 0:
            raise RuntimeError(f"Frame extraction failed at {t:.2f}s:\n{res.stderr}")
        outputs.append(out)

    if contact_sheet and len(outputs) > 1:
        sheet = os.path.join(out_dir, "contact_sheet.jpg")
        tmp = tempfile.mkdtemp(prefix="subtitler_sheet_")
        try:
            for k, o in enumerate(outputs):
                shutil.copyfile(o, os.path.join(tmp, f"f{k:03d}.jpg"))
            rows = (len(outputs) + 1) // 2
            cmd = [get_ffmpeg_path(), "-y", "-i", os.path.join(tmp, "f%03d.jpg"),
                   "-vf", f"scale=960:-2,tile=2x{rows}:padding=6:color=white",
                   "-frames:v", "1", "-q:v", "3", sheet]
            if run_ffmpeg(cmd).returncode == 0:
                outputs.append(sheet)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return outputs
