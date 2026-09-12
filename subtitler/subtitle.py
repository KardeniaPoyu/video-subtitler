"""
Subtitle formatting utilities.
Supports exporting to SRT, VTT, and styled ASS formats.
"""

from typing import List
from subtitler.asr import SubtitleSegment


def format_timestamp_srt(seconds: float) -> str:
    """Format seconds into SRT timestamp: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 999
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_timestamp_ass(seconds: float) -> str:
    """Format seconds into ASS timestamp: H:MM:SS.cc"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def save_to_srt(segments: List[SubtitleSegment], output_path: str, encoding: str = "utf-8") -> str:
    """Save segments to a standard .srt file."""
    lines = []
    for idx, seg in enumerate(segments, 1):
        start_str = format_timestamp_srt(seg.start)
        end_str = format_timestamp_srt(seg.end)
        lines.append(f"{idx}\n{start_str} --> {end_str}\n{seg.text}\n")

    content = "\n".join(lines)
    with open(output_path, "w", encoding=encoding) as f:
        f.write(content)
    return output_path


def save_to_vtt(segments: List[SubtitleSegment], output_path: str, encoding: str = "utf-8") -> str:
    """Save segments to a WebVTT (.vtt) file."""
    lines = ["WEBVTT\n"]
    for idx, seg in enumerate(segments, 1):
        start_str = format_timestamp_srt(seg.start).replace(",", ".")
        end_str = format_timestamp_srt(seg.end).replace(",", ".")
        lines.append(f"{idx}\n{start_str} --> {end_str}\n{seg.text}\n")

    content = "\n".join(lines)
    with open(output_path, "w", encoding=encoding) as f:
        f.write(content)
    return output_path


def save_to_ass(
    segments: List[SubtitleSegment],
    output_path: str,
    font_name: str = "Microsoft YaHei",
    font_size: int = 20,
    primary_color: str = "&H00FFFFFF",  # BGR format: White
    outline_color: str = "&H00000000",  # BGR format: Black
    outline_width: int = 2,
    margin_v: int = 30,
    encoding: str = "utf-8"
) -> str:
    """
    Save segments to a styled ASS (Advanced SubStation Alpha) file.
    Gives a modern, high-contrast look suitable for YouTube, Bilibili, and TikTok.
    """
    header = f"""[Script Info]
Title: Subtitled by Video-Subtitler
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},1,2,20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogue_lines = []
    for seg in segments:
        start_str = format_timestamp_ass(seg.start)
        end_str = format_timestamp_ass(seg.end)
        # Escape special ASS characters if necessary
        text = seg.text.replace("\n", "\\N")
        dialogue_lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")

    full_content = header + "\n".join(dialogue_lines) + "\n"
    with open(output_path, "w", encoding=encoding) as f:
        f.write(full_content)
    return output_path
