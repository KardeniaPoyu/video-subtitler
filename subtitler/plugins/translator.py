"""
Bilingual Subtitle & Translation Plugin.
Generates translated or dual-row bilingual subtitles.
"""

import os
import json
from typing import List, Optional
from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import TranslationPlugin


class LLMTranslatorPlugin(TranslationPlugin):
    name = "llm_translator"
    version = "0.1.0"
    description = "Generates high-quality translated and dual-track subtitles using LLMs."

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini"
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = os.environ.get("SUBTITLER_LLM_MODEL", model)

    def translate(
        self,
        segments: List[SubtitleSegment],
        target_lang: str,
        source_lang: Optional[str] = None,
        bilingual: bool = True
    ) -> List[SubtitleSegment]:
        """
        Translate segments into target language. If bilingual=True, stacks
        original and translated text into dual-row format.
        """
        if not segments:
            return segments

        if not self.api_key:
            print("[LLMTranslator] Note: OPENAI_API_KEY is not set. Subtitle translation skipped.")
            return segments

        print(f"[LLMTranslator] Translating {len(segments)} segments to '{target_lang}' (bilingual={bilingual})...")
        try:
            return self._translate_with_llm(segments, target_lang, source_lang, bilingual)
        except Exception as e:
            print(f"[LLMTranslator] Translation failed ({e}). Returning original segments.")
            return segments

    def _translate_with_llm(
        self,
        segments: List[SubtitleSegment],
        target_lang: str,
        source_lang: Optional[str],
        bilingual: bool
    ) -> List[SubtitleSegment]:
        import urllib.request

        url = (self.base_url.rstrip("/") if self.base_url else "https://api.openai.com/v1") + "/chat/completions"
        input_data = [{"id": i, "text": seg.text} for i, seg in enumerate(segments)]

        prompt = (
            f"You are a professional film and video subtitle translator. "
            f"Translate the following subtitle text into target language: '{target_lang}'.\n"
            f"Guidelines:\n"
            f"1. Produce natural, conversational, and culturally accurate video subtitles.\n"
            f"2. Keep translations concise to ensure good viewer reading rhythm on screen.\n"
            f"3. Return ONLY a valid JSON array of objects with fields 'id' and 'translation'."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(input_data, ensure_ascii=False)}
            ],
            "temperature": 0.3
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["choices"][0]["message"]["content"].strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            translated_items = json.loads(raw_text)
            trans_map = {item["id"]: item["translation"] for item in translated_items}

            output_segments: List[SubtitleSegment] = []
            for i, seg in enumerate(segments):
                trans_text = trans_map.get(i, "")
                if bilingual and trans_text:
                    # Stack source and translation: source on top, translation below
                    combined_text = f"{seg.text}\n{trans_text}"
                elif trans_text:
                    combined_text = trans_text
                else:
                    combined_text = seg.text

                output_segments.append(
                    SubtitleSegment(start=seg.start, end=seg.end, text=combined_text)
                )

            return output_segments
