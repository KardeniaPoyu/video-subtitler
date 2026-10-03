"""
ASR proofreading: rule-based cleanup (always) + optional LLM correction with sliding context.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import PostProcessPlugin
from subtitler.plugins.llm import LLMClient, to_id_map, windows

SYSTEM_PROMPT = """You are an expert subtitle proofreader. Fix speech-recognition (ASR) errors in the
numbered transcript lines, using the surrounding CONTEXT and the domain TERMS.

Rules:
1. Fix misheard words, homophones and wrong proper nouns (katakana names, product/game titles).
2. Remove stutters / accidental repetitions (那个那个 -> 那个); keep the speaker's wording otherwise.
3. Fix punctuation and casing (ai -> AI, chat gpt -> ChatGPT). Keep the original language.
4. Never merge, split, drop or reorder ids. If a line is fine, return it unchanged.
{terms}
Return ONLY JSON: {{"<id>": "<corrected text>", ...}}"""


class LLMProofreaderPlugin(PostProcessPlugin):
    name = "llm_corrector"
    version = "0.3.0"
    description = "Fixes ASR homophone errors, punctuation, and terminology using LLMs."

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None, batch_size: int = 50, context: int = 5):
        self.client = LLMClient(api_key, base_url, model)
        self.batch_size = batch_size
        self.context = context
        self.hotwords: List[str] = []

    @property
    def api_key(self):
        return self.client.api_key

    def process(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        if not segments:
            return segments
        cleaned = self._clean_rule_based(segments)
        if not self.client.available:
            print("[LLMProofreader] No LLM API key configured; applied rule-based cleanup only.")
            return cleaned
        print(f"[LLMProofreader] Proofreading {len(cleaned)} lines with {self.client.model}...")
        terms = f"\nDomain TERMS (correct spellings): {'、'.join(self.hotwords[:80])}" if self.hotwords else ""
        system = SYSTEM_PROMPT.format(terms=terms)
        for c0, a, b, c1 in windows(len(cleaned), self.batch_size, self.context):
            ctx = [f"[{i}] {cleaned[i].text}" for i in list(range(c0, a)) + list(range(b, c1))]
            body = {str(i): cleaned[i].text for i in range(a, b)}
            user = ("CONTEXT (do not edit):\n" + "\n".join(ctx) + "\n\n" if ctx else "") + \
                   "PROOFREAD:\n" + json.dumps(body, ensure_ascii=False, indent=0)
            try:
                fixed = to_id_map(self.client.chat_json(system, user), "text")
            except Exception as e:
                print(f"[LLMProofreader] Batch {a}-{b - 1} failed ({e}); keeping originals.")
                continue
            for i in range(a, b):
                t = fixed.get(i, "").strip()
                if t:
                    cleaned[i].text = t
        return cleaned

    def _clean_rule_based(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """Local cleanup for common ASR artifacts."""
        out: List[SubtitleSegment] = []
        for seg in segments:
            t = seg.text.strip()
            t = re.sub(r"([，。？！、,.?!])\1+", r"\1", t)          # doubled punctuation
            t = re.sub(r"(.{2,6}?)\1{2,}", r"\1\1", t)               # 3+ repeated chunks -> 2
            t = re.sub(r"(.)\1{5,}", r"\1\1\1", t)                   # ああああああ -> あああ
            t = re.sub(r"\s+", " ", t)
            out.append(SubtitleSegment(seg.start, seg.end, t, seg.translation))
        return out
