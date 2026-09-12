"""
Subtitle formatting utilities.
Supports exporting to SRT, VTT, and styled ASS formats with template support.
"""

from typing import List, Optional, Union
from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import StyleTemplate
from subtitler.plugins.templates import get_template


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
    template: Optional[Union[str, StyleTemplate]] = None,
    encoding: str = "utf-8"
) -> str:
    """
    Save segments to a styled ASS (Advanced SubStation Alpha) file using a StyleTemplate.
    """
    if isinstance(template, str):
        style = get_template(template)
    elif isinstance(template, StyleTemplate):
        style = template
    else:
        style = get_template("default")

    bold_val = -1 if style.bold else 0
    italic_val = -1 if style.italic else 0

    header = f"""[Script Info]
Title: Subtitled by Video-Subtitler
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{style.primary_color},{style.secondary_color},{style.outline_color},{style.back_color},{bold_val},{italic_val},0,0,100,100,0,0,1,{style.outline_width},{style.shadow_depth},{style.alignment},20,20,{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogue_lines = []
    for seg in segments:
        start_str = format_timestamp_ass(seg.start)
        end_str = format_timestamp_ass(seg.end)
        text = seg.text.replace("\n", "\\N")
        dialogue_lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}")

    full_content = header + "\n".join(dialogue_lines) + "\n"
    with open(output_path, "w", encoding=encoding) as f:
        f.write(full_content)
    return output_path
