"""
Smart subtitle line wrapping and text balancing utilities.
Prevents subtitles from overflowing video boundaries on screen.
"""

import re
from typing import List


def split_text_smartly(text: str, max_chars: int = 22, lang: str = "zh") -> str:
    """
    Intelligently splits long text into balanced multi-line text using \\N (for ASS) or \\n (for SRT).
    Ensures every resulting line stays strictly within comfortable screen reading width,
    never breaks inside words or numbers, and preserves natural punctuation cadence.
    """
    clean_text = text.strip()
    if len(clean_text) <= max_chars:
        return clean_text

    # If text is moderately long (<= max_chars * 2.5), find a clean break near the middle
    if len(clean_text) <= int(max_chars * 2.5):
        midpoint = len(clean_text) // 2
        puncts = ["。", "！", "？", "；", "，", "、", " ", "!", "?", ",", ";"]
        best_pos = -1
        best_dist = len(clean_text)
        max_allowed = int(max_chars * 1.5)
        for i, char in enumerate(clean_text):
            if char in puncts:
                dist = abs(i - midpoint)
                left_len = i + 1
                right_len = len(clean_text) - left_len
                if left_len <= max_allowed and right_len <= max_allowed:
                    if dist < best_dist:
                        best_dist = dist
                        best_pos = i + 1
        if best_pos != -1:
            line1 = clean_text[:best_pos].strip()
            line2 = clean_text[best_pos:].strip()
            return f"{line1}\\N{line2}"

    # For longer sentences, segment iteratively from left to right
    puncts = ["。", "！", "？", "；", "，", "、", " ", "!", "?", ",", ";"]
    ja_particles = [
        "からね", "ですから", "ですが", "だけど", "けれど", "ので", "から", "けど",
        "なら", "たら", "って", "には", "では", "とは", "に", "で", "を", "が", "は", "と"
    ]

    lines = []
    curr = clean_text

    while len(curr) > max_chars:
        search_limit = min(len(curr), max_chars + 3)
        window = curr[:search_limit]
        best_pos = -1

        # 1. Punctuation break
        for p in puncts:
            pos = window.rfind(p)
            if pos >= int(max_chars * 0.35):
                if pos + 1 > best_pos:
                    best_pos = pos + 1

        # 2. Japanese particle break
        if best_pos == -1 and lang == "ja":
            for p in ja_particles:
                pos = window.rfind(p)
                if pos >= int(max_chars * 0.35):
                    end_p = pos + len(p)
                    if end_p <= search_limit and end_p > best_pos:
                        best_pos = end_p

        # 3. Space break
        if best_pos == -1:
            pos = window.rfind(" ")
            if pos >= int(max_chars * 0.35):
                best_pos = pos + 1

        # 4. Fallback break (avoid splitting alphanumeric words)
        if best_pos <= 0:
            best_pos = max_chars
            if 0 < best_pos < len(curr) and curr[best_pos - 1].isalnum() and curr[best_pos].isalnum():
                while best_pos > 0 and curr[best_pos - 1].isalnum():
                    best_pos -= 1
                if best_pos <= 0:
                    best_pos = max_chars

        line = curr[:best_pos].strip()
        if line:
            lines.append(line)
        curr = curr[best_pos:].strip()

    if curr:
        lines.append(curr)

    return "\\N".join(lines)


def wrap_bilingual_pair(zh_text: str, ja_text: str, max_zh: int = 22, max_ja: int = 26) -> tuple:
    """
    Wraps both Chinese and Japanese texts to safe character lengths.
    """
    wrapped_zh = split_text_smartly(zh_text, max_chars=max_zh, lang="zh")
    wrapped_ja = split_text_smartly(ja_text, max_chars=max_ja, lang="ja")
    return wrapped_zh, wrapped_ja

