"""
Subtitle writers / readers: SRT, WebVTT and styled ASS.

Render modes
  * ``source``    – original transcript only
  * ``target``    – translation only (falls back to the source line when untranslated)
  * ``bilingual`` – translation as the large primary line + source as the small secondary line
  * ``auto``      – ``bilingual`` if any segment carries a translation, else ``source``

ASS output adapts PlayResX to the real video aspect ratio (vertical videos are no longer
stretched) and derives the wrap width from the font size and the available canvas width.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple, Union

from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import StyleTemplate
from subtitler.plugins.templates import get_template
from subtitler.wrapper import wrap_lines

RENDER_MODES = ("auto", "source", "target", "bilingual")


# ----------------------------------------------------------------------------- timestamps

def _split_ms(seconds: float) -> Tuple[int, int, int, int]:
    total_ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return h, m, s, ms


def format_timestamp_srt(seconds: float) -> str:
    """HH:MM:SS,mmm"""
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    return format_timestamp_srt(seconds).replace(",", ".")


def format_timestamp_ass(seconds: float) -> str:
    """H:MM:SS.cc"""
    cs_total = int(round(max(0.0, seconds) * 100))
    h, rem = divmod(cs_total, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def parse_timestamp(ts: str) -> float:
    """Parse SRT/VTT/ASS timestamps ('00:01:02,500', '01:02.500', '0:01:02.50')."""
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    secs = float(parts[-1])
    mins = int(parts[-2]) if len(parts) >= 2 else 0
    hrs = int(parts[-3]) if len(parts) >= 3 else 0
    return hrs * 3600 + mins * 60 + secs


# ----------------------------------------------------------------------------- helpers

def _resolve_mode(segments: List[SubtitleSegment], mode: str) -> str:
    if mode not in RENDER_MODES:
        raise ValueError(f"Unknown render mode '{mode}'. Use one of {RENDER_MODES}")
    if mode == "auto":
        return "bilingual" if any((s.translation or "").strip() for s in segments) else "source"
    return mode


def _primary_secondary(seg: SubtitleSegment, mode: str) -> Tuple[str, str]:
    """Returns (primary_text, secondary_text) for one segment."""
    src = (seg.text or "").strip()
    tgt = (seg.translation or "").strip()
    if mode == "source":
        return src, ""
    if mode == "target":
        return (tgt or src), ""
    # bilingual
    if tgt:
        return tgt, src
    return src, ""


_CJK_TRAILING = "，。、；：,;"


def tidy_line(line: str) -> str:
    """Subtitle convention for CJK lines: drop trailing ，。、；： (keep ！？… which carry tone)."""
    if re.search(r"[぀-ヿ一-鿿]", line):
        stripped = line.rstrip(_CJK_TRAILING).rstrip()
        return stripped or line
    return line


def _ass_escape(text: str) -> str:
    text = text.replace("{", "｛").replace("}", "｝")
    return re.sub(r"\\(?![Nnh])", "＼", text)


def _plain_lines(text: str, max_chars: float, tidy: bool = True) -> List[str]:
    lines = wrap_lines(text, max_chars=max_chars)
    return [tidy_line(l) for l in lines] if tidy else lines


# ----------------------------------------------------------------------------- SRT / VTT

def _text_block(seg: SubtitleSegment, mode: str, max_chars: float, secondary_max_chars: float,
                tidy: bool = True) -> str:
    primary, secondary = _primary_secondary(seg, mode)
    lines = _plain_lines(primary, max_chars, tidy)
    if secondary:
        lines += _plain_lines(secondary, secondary_max_chars, tidy)
    return "\n".join(lines)


def save_to_srt(segments: List[SubtitleSegment], output_path: str, encoding: str = "utf-8",
                mode: str = "auto", max_chars: float = 22, secondary_max_chars: float = 32,
                tidy_punct: bool = True) -> str:
    """Save segments to .srt (bilingual = translation lines first, then source lines)."""
    mode = _resolve_mode(segments, mode)
    blocks = []
    for idx, seg in enumerate(segments, 1):
        text = _text_block(seg, mode, max_chars, secondary_max_chars, tidy_punct)
        blocks.append(f"{idx}\n{format_timestamp_srt(seg.start)} --> {format_timestamp_srt(seg.end)}\n{text}\n")
    with open(output_path, "w", encoding=encoding, newline="\n") as f:
        f.write("\n".join(blocks))
    return output_path


def save_to_vtt(segments: List[SubtitleSegment], output_path: str, encoding: str = "utf-8",
                mode: str = "auto", max_chars: float = 22, secondary_max_chars: float = 32,
                tidy_punct: bool = True) -> str:
    """Save segments to WebVTT."""
    mode = _resolve_mode(segments, mode)
    blocks = ["WEBVTT\n"]
    for idx, seg in enumerate(segments, 1):
        text = _text_block(seg, mode, max_chars, secondary_max_chars, tidy_punct)
        blocks.append(f"{idx}\n{format_timestamp_vtt(seg.start)} --> {format_timestamp_vtt(seg.end)}\n{text}\n")
    with open(output_path, "w", encoding=encoding, newline="\n") as f:
        f.write("\n".join(blocks))
    return output_path


# ----------------------------------------------------------------------------- ASS

def fit_style_to_video(style: StyleTemplate, video_size: Optional[Tuple[int, int]]) -> StyleTemplate:
    """
    Return a copy of ``style`` whose canvas matches the video aspect ratio (PlayResY stays 1080)
    and whose wrap widths never exceed what physically fits on screen.
    """
    from dataclasses import replace

    play_y = style.play_res_y or 1080
    play_x = style.play_res_x or 1920
    if video_size and video_size[0] > 0 and video_size[1] > 0:
        w, h = video_size
        play_x = int(round(play_y * w / h))
    ml, mr, mv = style.margin_l, style.margin_r, style.margin_v
    fs = style.font_size
    sec_fs = style.secondary_font_size or int(round(fs * 0.65))
    if play_x < 1200:
        # vertical / square video: margins and fonts were designed for a 1920-wide canvas.
        scale = max(0.7, play_x / 1200)
        fs, sec_fs = int(round(fs * scale)), int(round(sec_fs * scale))
        ml = mr = max(30, int(play_x * 0.05))
        mv = max(mv, 200)  # clear Shorts / Douyin / Reels bottom UI
    usable = max(200, play_x - ml - mr)
    fit_primary = usable / fs * 0.96
    fit_secondary = usable / sec_fs * 0.96
    return replace(
        style,
        play_res_x=play_x,
        play_res_y=play_y,
        margin_l=ml,
        margin_r=mr,
        margin_v=mv,
        font_size=fs,
        secondary_font_size=sec_fs,
        max_chars=min(style.max_chars, fit_primary),
        secondary_max_chars=min(style.secondary_max_chars, fit_secondary),
    )


def build_ass_header(style: StyleTemplate, title: str = "Subtitled by Video-Subtitler") -> str:
    b = -1 if style.bold else 0
    i = -1 if style.italic else 0
    sb = -1 if style.secondary_bold else 0
    fmt = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
           "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
           "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding")
    primary = (f"Style: Default,{style.font_name},{style.font_size},{style.primary_color},"
               f"&H000000FF,{style.outline_color},{style.back_color},"
               f"{b},{i},0,0,100,100,0,0,1,{style.outline_width:g},{style.shadow_depth:g},{style.alignment},"
               f"{style.margin_l},{style.margin_r},{style.margin_v},1")
    secondary = (f"Style: Secondary,{style.font_name},{style.secondary_font_size},{style.secondary_color},"
                 f"&H000000FF,{style.outline_color},{style.back_color},"
                 f"{sb},0,0,0,100,100,0,0,1,{style.secondary_outline_width:g},{style.shadow_depth:g},"
                 f"{style.alignment},{style.margin_l},{style.margin_r},{style.margin_v},1")
    extra = f"\n{style.extra_ass_styles.strip()}" if style.extra_ass_styles else ""
    return (
        "[Script Info]\n"
        f"Title: {title}\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 2\n"  # we wrap ourselves; 2 = no automatic wrapping by libass
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n"
        f"PlayResX: {style.play_res_x}\n"
        f"PlayResY: {style.play_res_y}\n"
        "\n[V4+ Styles]\n"
        f"{fmt}\n{primary}\n{secondary}{extra}\n"
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def save_to_ass(
    segments: List[SubtitleSegment],
    output_path: str,
    template: Optional[Union[str, StyleTemplate]] = None,
    encoding: str = "utf-8",
    mode: str = "auto",
    video_size: Optional[Tuple[int, int]] = None,
    secondary_above: bool = False,
    tidy_punct: bool = True,
) -> str:
    """
    Save segments to a styled ASS file.

    :param template: style preset name or StyleTemplate (default: 'default').
    :param mode: 'auto' | 'source' | 'target' | 'bilingual'.
    :param video_size: (width, height) of the target video, used to fit the canvas.
    :param secondary_above: put the small secondary line above the primary line.
    :param tidy_punct: drop trailing ，。、； on CJK lines (subtitle convention).
    """
    if isinstance(template, StyleTemplate):
        style = template
    else:
        style = get_template(template or "default")
    style = fit_style_to_video(style, video_size)
    mode = _resolve_mode(segments, mode)

    events = []
    for seg in segments:
        primary, secondary = _primary_secondary(seg, mode)
        p_lines = [_ass_escape(l) for l in _plain_lines(primary, style.max_chars, tidy_punct)]
        if not p_lines:
            continue
        text = "\\N".join(p_lines)
        if secondary:
            s_lines = [_ass_escape(l) for l in _plain_lines(secondary, style.secondary_max_chars, tidy_punct)]
            s_text = "\\N".join(s_lines)
            if secondary_above:
                text = "{\\rSecondary}" + s_text + "\\N{\\rDefault}" + text
            else:
                text = text + "\\N{\\rSecondary}" + s_text
        events.append(
            f"Dialogue: 0,{format_timestamp_ass(seg.start)},{format_timestamp_ass(seg.end)},Default,,0,0,0,,{text}"
        )

    with open(output_path, "w", encoding=encoding, newline="\n") as f:
        f.write(build_ass_header(style) + "\n".join(events) + "\n")
    return output_path


def save_subtitles(segments: List[SubtitleSegment], output_path: str, **kwargs) -> str:
    """Dispatch on the file extension (.srt / .vtt / .ass)."""
    ext = output_path.lower().rsplit(".", 1)[-1]
    if ext == "ass":
        return save_to_ass(segments, output_path, **kwargs)
    srt_kwargs = {k: v for k, v in kwargs.items()
                  if k in ("mode", "max_chars", "secondary_max_chars", "encoding", "tidy_punct")}
    if ext == "vtt":
        return save_to_vtt(segments, output_path, **srt_kwargs)
    return save_to_srt(segments, output_path, **srt_kwargs)


# ----------------------------------------------------------------------------- readers

def load_srt(path: str) -> List[SubtitleSegment]:
    """Parse SRT/VTT into segments (all text lines kept, joined with '\\n')."""
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read().replace("\r\n", "\n")
    out: List[SubtitleSegment] = []
    for block in re.split(r"\n\s*\n", content):
        lines = [l for l in block.strip().split("\n") if l.strip()]
        for k, l in enumerate(lines):
            if "-->" in l:
                a, b = l.split("-->")
                text = "\n".join(lines[k + 1:])
                out.append(SubtitleSegment(parse_timestamp(a), parse_timestamp(b.split()[0]), text))
                break
    return out


def load_ass(path: str) -> List[SubtitleSegment]:
    """Parse ASS Dialogue events. Secondary-style text (after {\\rSecondary}) goes to ``text``,
    primary text to ``translation`` when both exist, mirroring the bilingual writer."""
    out: List[SubtitleSegment] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            if not line.startswith("Dialogue:"):
                continue
            parts = line.rstrip("\n").split(",", 9)
            if len(parts) < 10:
                continue
            start, end, raw = parse_timestamp(parts[1]), parse_timestamp(parts[2]), parts[9]
            if "{\\rSecondary}" in raw:
                if raw.startswith("{\\rSecondary}"):
                    sec, _, pri = raw.partition("\\N{\\rDefault}")
                else:
                    pri, _, sec = raw.partition("\\N{\\rSecondary}")
                clean = lambda t: re.sub(r"\{[^}]*\}", "", t).replace("\\N", "\n").strip()
                out.append(SubtitleSegment(start, end, clean(sec), clean(pri)))
            else:
                text = re.sub(r"\{[^}]*\}", "", raw).replace("\\N", "\n").strip()
                out.append(SubtitleSegment(start, end, text))
    return out


def load_subtitles(path: str) -> List[SubtitleSegment]:
    return load_ass(path) if path.lower().endswith(".ass") else load_srt(path)
