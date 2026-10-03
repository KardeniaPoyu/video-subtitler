"""
Subtitle quality checks (Stage 5 "typographic & boundary safety audit" as code).

Flags: untranslated lines, leftover source script in the translation, glossary violations,
lines that wrap to 3+ rows, lines wider than the screen, reading speed (CPS), too-short /
too-long events, overlaps and flicker gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import StyleTemplate
from subtitler.plugins.templates import get_template
from subtitler.wrapper import display_width, wrap_lines

KANA = re.compile(r"[぀-ヿ]")
_STRIP = re.compile(r"[\s()（）《》「」『』\[\]【】·・,，.。!！?？:：;；、\-—]")


def _lcs_len(a: str, b: str) -> int:
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b, 1):
            cur.append(prev[j - 1] + 1 if ca == cb else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def term_present(want: str, text: str, ratio: float = 0.6) -> bool:
    """Lenient glossary match: exact, or most of the term's characters appear in order
    (压轴登场 ~ 压轴大作登场, 3D动作游戏 ~ 3D动作冒险)."""
    w, t = _STRIP.sub("", want).lower(), _STRIP.sub("", text).lower()
    if not w or w in t:
        return True
    return _lcs_len(w, t) / len(w) >= ratio


@dataclass
class Issue:
    level: str      # "error" | "warn" | "info"
    index: int      # 1-based line number / segment id
    start: float
    code: str
    message: str

    def __str__(self) -> str:
        m, s = divmod(self.start, 60)
        return f"{self.level.upper():5s} #{self.index:<4d} {int(m):02d}:{s:04.1f}  [{self.code}] {self.message}"


def check_segments(
    segments: Sequence[SubtitleSegment],
    style: Optional[StyleTemplate] = None,
    target_lang: Optional[str] = None,
    knowledge=None,
    domains: Optional[Sequence[str]] = None,
    ids: Optional[Sequence[int]] = None,
    max_cps: float = 11.0,
    min_duration: float = 0.7,
    max_duration: float = 8.0,
) -> List[Issue]:
    """
    :param style: style used for rendering (wrap widths come from it); default 'bilingual'.
    :param target_lang: when set, every line must carry a translation.
    :param max_cps: reading-speed warning threshold in em/second for the primary line
                    (11 ~= 11 汉字/s, typical for Bilibili; use 9 for Netflix-style strictness).
                    Errors start at 1.4x the threshold.
    """
    style = style or get_template("bilingual")
    issues: List[Issue] = []
    ids = list(ids) if ids else list(range(1, len(segments) + 1))
    hard = style.max_chars * 1.25
    tgt_is_cjk = (target_lang or "").lower().startswith(("zh", "ja", "ko"))

    for k, seg in enumerate(segments):
        n = ids[k]
        src = (seg.text or "").strip()
        tgt = (seg.translation or "").strip()
        dur = seg.end - seg.start
        add = lambda lvl, code, msg: issues.append(Issue(lvl, n, seg.start, code, msg))

        if dur <= 0:
            add("error", "timing", f"end <= start ({seg.start:.2f} -> {seg.end:.2f})")
        elif dur < min_duration:
            add("warn", "short", f"only {dur:.2f}s on screen")
        elif dur > max_duration:
            add("warn", "long", f"{dur:.1f}s on screen; consider splitting")

        if k + 1 < len(segments):
            gap = segments[k + 1].start - seg.end
            if gap < -0.01:
                add("error", "overlap", f"overlaps next line by {-gap:.2f}s")
            elif 0 < gap < 0.08:
                add("info", "flicker", f"{gap * 1000:.0f}ms gap to next line (flicker); close it or widen it")

        if not src and not tgt:
            add("error", "empty", "empty line")
            continue

        if target_lang:
            if not tgt:
                add("error", "untranslated", f"no translation: {src[:40]}")
            else:
                if target_lang.lower().startswith("zh") and KANA.search(tgt):
                    add("warn", "leftover", f"kana left in Chinese translation: {tgt[:40]}")
                if tgt == src and len(src) > 3:
                    add("warn", "same", "translation identical to source")

        primary = tgt or src
        p_lines = wrap_lines(primary, style.max_chars)
        if len(p_lines) > 2:
            add("error", "rows", f"primary wraps to {len(p_lines)} rows (max 2) - shorten or split: {primary[:30]}...")
        widest = max((display_width(l) for l in p_lines), default=0)
        if widest > hard:
            add("error", "width", f"row is {widest:.0f} em wide (limit {hard:.0f})")
        if tgt and src:
            s_lines = wrap_lines(src, style.secondary_max_chars)
            if len(s_lines) > 2:
                add("warn", "rows2", f"secondary (source) wraps to {len(s_lines)} rows")

        if dur > 0:
            cps = display_width(re.sub(r"[\s，。、！？,.!?…「」『』《》()（）]", "", primary)) / dur
            if cps > max_cps * 1.4:
                add("error", "cps", f"reading speed {cps:.1f} em/s (limit {max_cps:g}) - shorten text or extend timing")
            elif cps > max_cps:
                add("warn", "cps", f"reading speed {cps:.1f} em/s (limit {max_cps:g})")

        if knowledge is not None and domains and tgt:
            for term, want in knowledge.glossary_hints(src, list(domains)):
                if not term_present(want, tgt):
                    add("warn", "glossary", f"'{term}' should be translated as '{want}'")
    return issues


def summarize(issues: Sequence[Issue], total: int) -> str:
    e = sum(i.level == "error" for i in issues)
    w = sum(i.level == "warn" for i in issues)
    inf = sum(i.level == "info" for i in issues)
    codes = {}
    for i in issues:
        codes[i.code] = codes.get(i.code, 0) + 1
    by = ", ".join(f"{c}={n}" for c, n in sorted(codes.items(), key=lambda x: -x[1]))
    verdict = "PASS" if e == 0 else "FAIL"
    return f"{verdict}: {total} lines, {e} errors, {w} warnings, {inf} info" + (f"  ({by})" if by else "")
