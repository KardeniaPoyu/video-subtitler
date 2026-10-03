"""
Video chapters: Bilibili / YouTube description timelines and lossless MP4/MKV chapter muxing.

Chapters can be given as tuples ``(start, title)`` / ``(start, end, title)`` or parsed from a
plain-text file with one ``MM:SS 标题`` / ``HH:MM:SS 标题`` per line.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import List, Optional, Sequence, Tuple

from subtitler.ffmpeg_utils import get_ffmpeg_path, probe_video, run_ffmpeg

Chapter = Tuple[float, float, str]


def format_timestamp(seconds: float) -> str:
    """mm:ss, or hh:mm:ss for videos longer than an hour (Bilibili/YouTube timeline format)."""
    s = int(seconds)  # floor: a chapter must never point *after* its real start
    hrs, rem = divmod(s, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}"


def normalize_chapters(chapters: Sequence[tuple], duration: Optional[float] = None) -> List[Chapter]:
    """Convert (start, title) / (start, end, title) items into sorted (start, end, title) with
    each end = next start (last end = video duration)."""
    items = []
    for c in chapters:
        if len(c) == 2:
            items.append([float(c[0]), None, str(c[1]).strip()])
        else:
            items.append([float(c[0]), None if c[1] is None else float(c[1]), str(c[2]).strip()])
    items.sort(key=lambda x: x[0])
    for i, it in enumerate(items):
        nxt = items[i + 1][0] if i + 1 < len(items) else None
        if it[1] is None or (nxt is not None and it[1] > nxt):
            it[1] = nxt if nxt is not None else (duration if duration else it[0] + 60)
    return [(a, b, t) for a, b, t in items]


def parse_chapter_text(text: str) -> List[Tuple[float, str]]:
    """Parse lines like '00:00 开场' / '1:02:03 - Boss战' / '[12:30] 结尾'."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*\[?((?:\d{1,2}:)?\d{1,2}:\d{2})\]?\s*[-–—|:：]?\s*(.+?)\s*$", line)
        if not m:
            continue
        parts = [int(p) for p in m.group(1).split(":")]
        secs = parts[-1] + parts[-2] * 60 + (parts[-3] * 3600 if len(parts) == 3 else 0)
        out.append((float(secs), m.group(2)))
    return out


def load_chapters(path: str) -> List[Tuple[float, str]]:
    with open(path, "r", encoding="utf-8-sig") as f:
        return parse_chapter_text(f.read())


def validate_chapters(chapters: Sequence[tuple], platform: str = "bilibili") -> List[str]:
    """Return a list of human-readable problems (empty = OK)."""
    problems = []
    norm = normalize_chapters(chapters)
    if not norm:
        return ["No chapters."]
    if norm[0][0] != 0:
        problems.append("First chapter must start at 00:00 (Bilibili/YouTube ignore timelines otherwise).")
    for a, b, t in norm:
        if not t:
            problems.append(f"{format_timestamp(a)} has an empty title.")
        if len(t) > 30:
            problems.append(f"{format_timestamp(a)} title is long ({len(t)} chars); aim for 6-18.")
    for (a, _, _), (b, _, _) in zip(norm, norm[1:]):
        if b - a < 10:
            problems.append(f"Chapters at {format_timestamp(a)} and {format_timestamp(b)} are <10s apart.")
    if platform == "youtube" and len(norm) < 3:
        problems.append("YouTube needs at least 3 chapters.")
    return problems


def format_bilibili_timeline(chapters: Sequence[tuple], header: Optional[str] = "【章节】") -> str:
    """Description text that Bilibili/YouTube players turn into clickable progress-bar chapters."""
    lines = [header] if header else []
    for start, _, title in normalize_chapters(chapters):
        lines.append(f"{format_timestamp(start)} {title}")
    return "\n".join(lines)


def _escape_meta(value: str) -> str:
    return re.sub(r"([=;#\\\n])", r"\\\1", value)


def generate_ffmetadata(chapters: Sequence[tuple], duration: Optional[float] = None) -> str:
    """FFMETADATA1 document for (start[, end], title) chapters."""
    lines = [";FFMETADATA1"]
    for start, end, title in normalize_chapters(chapters, duration):
        lines += ["", "[CHAPTER]", "TIMEBASE=1/1000",
                  f"START={int(start * 1000)}", f"END={int(end * 1000)}", f"title={_escape_meta(title)}"]
    return "\n".join(lines) + "\n"


def embed_chapters_into_video(video_in: str, chapters: Sequence[tuple], video_out: Optional[str] = None) -> str:
    """
    Losslessly mux chapters into an MP4/MKV (stream copy, ~seconds). Keeps all streams and the
    original global metadata. Enables chapter bars in PotPlayer, VLC, mpv, QuickTime, IINA.
    """
    if not os.path.exists(video_in):
        raise FileNotFoundError(f"Input video not found: {video_in}")
    if not video_out:
        base, ext = os.path.splitext(video_in)
        video_out = f"{base}_chapters{ext}"
    if os.path.abspath(video_out) == os.path.abspath(video_in):
        raise ValueError("Output path must differ from input path.")

    duration = probe_video(video_in).duration or None
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(generate_ffmetadata(chapters, duration))
        meta_path = f.name
    try:
        cmd = [get_ffmpeg_path(), "-y", "-i", video_in, "-i", meta_path,
               "-map", "0", "-map_metadata", "0", "-map_chapters", "1", "-codec", "copy", video_out]
        res = run_ffmpeg(cmd)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg chapter muxing failed:\n{res.stderr}")
        return video_out
    finally:
        try:
            os.remove(meta_path)
        except OSError:
            pass


def suggest_chapters_from_segments(segments, min_gap: float = 90.0) -> List[Tuple[float, str]]:
    """
    Cheap heuristic scaffold (pauses >= 2.5 s, at least ``min_gap`` apart) for the agent to refine:
    returns candidate (start, first-line-text) pairs. The agent should rewrite the titles.
    """
    out: List[Tuple[float, str]] = [(0.0, segments[0].translation or segments[0].text)] if segments else []
    for prev, cur in zip(segments, segments[1:]):
        if cur.start - prev.end >= 2.5 and cur.start - out[-1][0] >= min_gap:
            out.append((cur.start, cur.translation or cur.text))
    return out
