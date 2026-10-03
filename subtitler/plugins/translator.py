"""
LLM subtitle translation with sliding context windows and glossary hints.

Segments keep their source text in ``.text`` and receive the translation in ``.translation``;
rendering (bilingual / target-only) is decided later by the subtitle writer.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional, Tuple

from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import TranslationPlugin
from subtitler.plugins.llm import LLMClient, to_id_map, windows

LANG_NAMES = {"zh": "Simplified Chinese (简体中文)", "zh-tw": "Traditional Chinese (繁體中文)",
              "en": "English", "ja": "Japanese", "ko": "Korean", "fr": "French", "es": "Spanish",
              "de": "German", "ru": "Russian"}

SYSTEM_PROMPT = """You are a senior subtitle localizer for online video (Bilibili / YouTube).
Translate each numbered subtitle line from {src} into {tgt}.

Rules:
1. Read the CONTEXT lines first to understand speaker, topic and tone; translate meaning, not words.
2. Natural spoken {tgt}: concise, idiomatic, keep humor and emotion. No literal machine phrasing.
3. One output line per input id. Never merge, split, drop or reorder ids.
4. Keep each line short enough to read on screen (Chinese: ideally <= 22 characters per line).
5. Use the GLOSSARY translations exactly for the listed terms. Keep official localized names
   for games/anime/products; put work titles in 《》 for Chinese.
6. Drop pure filler (えーと, um, uh) unless it carries emotion; keep laughter/exclamations short.
7. If a source line is obviously an ASR mishearing, translate what the speaker most plausibly said.
{topic}
Return ONLY JSON: {{"<id>": "<translation>", ...}}"""


class LLMTranslatorPlugin(TranslationPlugin):
    name = "llm_translator"
    version = "0.3.0"
    description = "Context-window LLM translation with glossary enforcement."

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None,
                 model: Optional[str] = None, batch_size: int = 40, context: int = 6):
        self.client = LLMClient(api_key, base_url, model)
        self.batch_size = batch_size
        self.context = context
        # Optional: callable(text) -> [(src_term, tgt_term)], supplied by the pipeline (KnowledgeEngine)
        self.glossary_hints: Optional[Callable[[str], List[Tuple[str, str]]]] = None
        self.topic: Optional[str] = None

    @property
    def api_key(self):
        return self.client.api_key

    def translate(self, segments: List[SubtitleSegment], target_lang: str,
                  source_lang: Optional[str] = None, bilingual: bool = True,
                  only_missing: bool = False) -> List[SubtitleSegment]:
        if not segments:
            return segments
        if not self.client.available:
            print("[LLMTranslator] No LLM API key configured (SUBTITLER_LLM_API_KEY / OPENAI_API_KEY). "
                  "Translation skipped - use the agent batch workflow instead (subtitler batch / apply).")
            return segments

        src_name = LANG_NAMES.get((source_lang or "").lower(), source_lang or "the source language")
        tgt_name = LANG_NAMES.get(target_lang.lower(), target_lang)
        topic = f"\nVideo topic / notes: {self.topic}" if self.topic else ""
        system = SYSTEM_PROMPT.format(src=src_name, tgt=tgt_name, topic=topic)

        out = [SubtitleSegment(s.start, s.end, s.text, s.translation) for s in segments]
        todo = {i for i, s in enumerate(out) if not (only_missing and (s.translation or "").strip())}
        if not todo:
            return out
        print(f"[LLMTranslator] Translating {len(todo)} lines -> {target_lang} with {self.client.model} "
              f"(batch {self.batch_size}, context ±{self.context})")

        for c0, a, b, c1 in windows(len(out), self.batch_size, self.context):
            ids = [i for i in range(a, b) if i in todo]
            if not ids:
                continue
            ctx_before = [f"[{i}] {out[i].text}" + (f"  => {out[i].translation}" if out[i].translation else "")
                          for i in range(c0, a)]
            ctx_after = [f"[{i}] {out[i].text}" for i in range(b, c1)]
            body = {str(i): out[i].text for i in ids}
            hints = self.glossary_hints("\n".join(out[i].text for i in ids)) if self.glossary_hints else []
            user = ""
            if hints:
                user += "GLOSSARY:\n" + "\n".join(f"- {s} => {t}" for s, t in hints) + "\n\n"
            if ctx_before or ctx_after:
                user += "CONTEXT (do not translate):\n" + "\n".join(ctx_before + ["..."] + ctx_after) + "\n\n"
            user += "TRANSLATE:\n" + json.dumps(body, ensure_ascii=False, indent=0)
            try:
                result = to_id_map(self.client.chat_json(system, user, temperature=0.3), "translation")
            except Exception as e:
                print(f"[LLMTranslator] Batch {a}-{b - 1} failed ({e}); leaving those lines untranslated.")
                continue
            missing = [i for i in ids if not result.get(i, "").strip()]
            for i in ids:
                if result.get(i, "").strip():
                    out[i].translation = result[i].strip()
            print(f"[LLMTranslator] {b}/{len(out)} done" + (f" ({len(missing)} missing)" if missing else ""))
        return out
