"""
Smart subtitle line wrapping and text balancing utilities.
Prevents subtitles from overflowing video boundaries on screen.
"""

import re
from typing import List


def split_text_smartly(text: str, max_chars: int = 22, lang: str = "zh") -> str:
    """
    Intelligently splits long text into balanced multi-line text using \\N (for ASS) or \\n (for SRT).
    Breaks at natural punctuation marks, word boundaries, or semantic particles.
    """
    clean_text = text.strip()
    if len(clean_text) <= max_chars:
        return clean_text

    # Punctuation marks suitable for breaking
    puncts = ["，", "。", "！", "？", "；", "、", " ", "!", "?", ",", ";"]
    midpoint = len(clean_text) // 2

    # 1. Look for punctuation close to the midpoint (between 30% and 70% of text length)
    best_pos = -1
    best_dist = len(clean_text)

    for i, char in enumerate(clean_text):
        if char in puncts:
            dist = abs(i - midpoint)
            # Prefer breaking in the middle third of the sentence
            if dist < best_dist and (0.25 * len(clean_text) <= i <= 0.75 * len(clean_text)):
                best_dist = dist
                best_pos = i + 1  # Break right after punctuation

    # 2. For Japanese text without punctuation, look for common particles
    if best_pos == -1 and lang == "ja":
        particles = ["からね", "ですから", "ですが", "だけど", "けれど", "ので", "から", "けど", "なら", "たら", "って", "には", "では", "とは"]
        for p in particles:
            pos = clean_text.find(p)
            if pos != -1:
                break_point = pos + len(p)
                dist = abs(break_point - midpoint)
                if dist < best_dist and (0.25 * len(clean_text) <= break_point <= 0.75 * len(clean_text)):
                    best_dist = dist
                    best_pos = break_point

    # 3. If no natural punctuation found, break at whitespace (English) or middle
    if best_pos == -1:
        # Check for whitespace
        spaces = [i for i, c in enumerate(clean_text) if c == " "]
        if spaces:
            best_space = min(spaces, key=lambda i: abs(i - midpoint))
            best_pos = best_space + 1
        else:
            best_pos = midpoint

    line1 = clean_text[:best_pos].strip()
    line2 = clean_text[best_pos:].strip()

    # If the remaining line is still too long (> max_chars * 1.5), recursively split it
    if len(line2) > max_chars * 1.4:
        line2 = split_text_smartly(line2, max_chars, lang)

    return f"{line1}\\N{line2}"


def wrap_bilingual_pair(zh_text: str, ja_text: str, max_zh: int = 22, max_ja: int = 26) -> tuple:
    """
    Wraps both Chinese and Japanese texts to safe character lengths.
    """
    wrapped_zh = split_text_smartly(zh_text, max_chars=max_zh, lang="zh")
    wrapped_ja = split_text_smartly(ja_text, max_chars=max_ja, lang="ja")
    return wrapped_zh, wrapped_ja
