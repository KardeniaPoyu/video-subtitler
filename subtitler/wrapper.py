"""
Smart subtitle line wrapping.

Widths are measured in "em": one CJK / full-width character = 1.0, one Latin
character = 0.5. That way a single ``max_chars`` budget works for Chinese,
Japanese and English alike (22 em ~= 22 汉字 ~= 44 Latin characters).

The breaker is a small dynamic program over break opportunities that:
  * never splits a Latin word or a number,
  * obeys CJK line-breaking rules (no line starts with ，。！？」 etc., no line
    ends with 「『（《 etc.),
  * prefers sentence punctuation > clause punctuation > spaces > particles,
  * balances line lengths and strongly avoids more than two lines.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import List, Optional, Tuple

# Characters that must not start a line (行頭禁則)
NO_LINE_START = set("，。！？、；：,.!?;:)）]］」』》〉】〕”’…‥ー〜～・ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々%％")
# Characters that must not end a line (行末禁則)
NO_LINE_END = set("（([［「『《〈【〔“‘")

OPEN_BRACKETS = set("《「『（(【〈“")
CLOSE_BRACKETS = set("》」』）)】〉”")
SENTENCE_END = set("。！？!?…")
CLAUSE_END = set("，、；：,;:")
JA_PARTICLES = ("からね", "ですから", "ですが", "だけど", "けれど", "ので", "から", "けど",
                "なら", "たら", "って", "には", "では", "とは", "は", "が", "を", "に", "で", "と", "も", "へ")

_LATIN_RUN = re.compile(r"[A-Za-z0-9À-ɏ][A-Za-z0-9À-ɏ'’\.\-_/%+&#@]*")


def char_width(ch: str) -> float:
    if ch in "​":
        return 0.0
    return 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.5


def display_width(text: str) -> float:
    """Visual width of ``text`` in em (CJK char = 1, Latin char = 0.5)."""
    return sum(char_width(c) for c in text)


def detect_lang(text: str) -> str:
    """Rough script detection: 'ja' if kana present, 'zh' if mostly Han, else 'en'."""
    if re.search(r"[぀-ヿ]", text):
        return "ja"
    han = len(re.findall(r"[一-鿿]", text))
    if han and han * 2 >= len(re.sub(r"\s", "", text)) * 0.5:
        return "zh"
    if re.search(r"[가-힯]", text):
        return "ko"
    return "en" if not han else "zh"


def _atomize(text: str) -> List[str]:
    """Split text into unbreakable atoms (Latin words with trailing spaces, single CJK chars)."""
    atoms: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = _LATIN_RUN.match(text, i)
        if m:
            j = m.end()
        else:
            j = i + 1
        # attach following spaces to the atom so that breaks happen after spaces
        while j < n and text[j] == " ":
            j += 1
        atoms.append(text[i:j])
        i = j
    return atoms


def _break_bonus(left: str, right: str, lang: str) -> Optional[float]:
    """Desirability of breaking between atom ``left`` and atom ``right``. None = forbidden."""
    l_core = left.rstrip()
    r_core = right.lstrip()
    if not l_core or not r_core:
        return 10.0
    last, first = l_core[-1], r_core[0]
    if first in NO_LINE_START or last in NO_LINE_END:
        return None
    if last in SENTENCE_END or (last == "." and left.endswith(" ")):
        return 40.0
    if last in CLAUSE_END:
        return 26.0
    if left.endswith(" "):
        return 12.0
    if lang == "ja":
        # Bunsetsu-ish boundary: particle followed by a non-hiragana character
        if not ("぀" <= first <= "ゟ"):
            for p in JA_PARTICLES:
                if l_core.endswith(p):
                    return 8.0 + min(len(p), 3)
            if "぀" <= last <= "ゟ":
                return 3.0
    # Breaking between two Latin/number atoms without a space never happens (they are one atom),
    # but guard against e.g. "Switch2" split oddly.
    if last.isascii() and last.isalnum() and first.isascii() and first.isalnum():
        return None
    # between two CJK characters with no other cue: likely mid-word
    return -10.0


def _wrap_line(text: str, max_chars: float, hard_max: float, lang: str) -> List[str]:
    text = re.sub(r"[ \t]+", " ", text.strip())
    total = display_width(text)
    if total <= max_chars:
        return [text] if text else []

    atoms = _atomize(text)
    n = len(atoms)
    widths = [display_width(a) for a in atoms]
    prefix = [0.0]
    for w in widths:
        prefix.append(prefix[-1] + w)

    bonus: List[Optional[float]] = [None] * (n + 1)
    bonus[n] = 0.0
    depth = 0
    for k in range(1, n):
        for ch in atoms[k - 1]:
            if ch in OPEN_BRACKETS:
                depth += 1
            elif ch in CLOSE_BRACKETS and depth > 0:
                depth -= 1
        b = _break_bonus(atoms[k - 1], atoms[k], lang)
        if b is not None and depth > 0:
            b -= 45.0  # avoid splitting 《titles》 / 「quotes」 / (asides)
        bonus[k] = b

    def solve(k: int):
        """Best split into exactly k lines, balanced around total/k. Returns (cost, cuts)."""
        target = total / k
        INF = float("inf")
        best = [[INF] * (n + 1) for _ in range(k + 1)]
        prev = [[-1] * (n + 1) for _ in range(k + 1)]
        best[0][0] = 0.0
        for lines in range(1, k + 1):
            for j in range(1, n + 1):
                if bonus[j] is None:
                    continue
                for i in range(j - 1, -1, -1):
                    if best[lines - 1][i] == INF:
                        continue
                    w = prefix[j] - prefix[i]
                    if w > hard_max * 1.6 and i < j - 1:
                        break
                    w = display_width("".join(atoms[i:j]).strip())
                    c = 0.4 * (w - target) ** 2 if k > 1 else 0.0
                    if w > max_chars:
                        c += 6.0 * (w - max_chars) + (w - max_chars) ** 2
                    if w > hard_max:
                        c += 10000.0 + 1000.0 * (w - hard_max)
                    if w < 3 and k > 1:
                        c += 60.0  # orphan
                    c += best[lines - 1][i] - (bonus[j] if j < n else 0.0)
                    if c < best[lines][j]:
                        best[lines][j] = c
                        prev[lines][j] = i
        if best[k][n] == INF:
            return INF, []
        cuts, j = [], n
        for lines in range(k, 0, -1):
            cuts.append(j)
            j = prev[lines][j]
        return best[k][n], cuts[::-1]

    line_penalty = {1: 0.0, 2: 40.0, 3: 1200.0, 4: 3000.0}
    max_k = min(n, max(2, math.ceil(total / hard_max) + 1), 6)
    best_cost, cuts = float("inf"), []
    for k in range(1, max_k + 1):
        cost, c = solve(k)
        cost += line_penalty.get(k, 3000.0 + 1000.0 * (k - 4))
        if cost < best_cost:
            best_cost, cuts = cost, c

    if not cuts:  # no legal path (shouldn't happen) - fall back to a hard chop
        out, cur = [], ""
        for a in atoms:
            if display_width(cur + a) > max_chars and cur:
                out.append(cur.strip())
                cur = ""
            cur += a
        if cur.strip():
            out.append(cur.strip())
        return out

    lines, start = [], 0
    for c in cuts:
        line = "".join(atoms[start:c]).strip()
        if line:
            lines.append(line)
        start = c
    return lines


def wrap_lines(
    text: str,
    max_chars: float = 22,
    lang: Optional[str] = None,
    hard_max: Optional[float] = None,
) -> List[str]:
    """
    Wrap text into a list of display lines. Existing ``\\N`` / ``\\n`` breaks are kept.
    :param max_chars: soft line budget in em (CJK chars).
    :param hard_max: absolute line limit in em (defaults to 1.25 * max_chars).
    """
    if hard_max is None:
        hard_max = max_chars * 1.25
    pieces = text.replace("\\N", "\n").split("\n")
    out: List[str] = []
    for p in pieces:
        if not p.strip():
            continue
        out.extend(_wrap_line(p, max_chars, hard_max, lang or detect_lang(p)))
    return out


def split_text_smartly(text: str, max_chars: int = 22, lang: Optional[str] = None,
                       sep: str = "\\N") -> str:
    """
    Wrap ``text`` and join lines with ``sep`` (``\\N`` for ASS, ``\\n`` for SRT/VTT).
    Never breaks inside words or numbers, preserves punctuation cadence, and
    never leaves an empty trailing line.
    """
    return sep.join(wrap_lines(text, max_chars=max_chars, lang=lang))


def clean_sub_text(text: str) -> str:
    """Remove empty lines / trailing line breaks and collapse whitespace."""
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.replace("\\N", "\n").split("\n")]
    return "\n".join(l for l in lines if l)


def wrap_bilingual_pair(zh_text: str, ja_text: str, max_zh: int = 22, max_ja: int = 26) -> Tuple[str, str]:
    """Wraps primary (zh) and secondary (ja/en) texts to safe widths. Returns ASS ``\\N``-joined strings."""
    return (split_text_smartly(zh_text, max_chars=max_zh),
            split_text_smartly(ja_text, max_chars=max_ja))
