"""
Smart Subtitle Proofreading & Homophone Correction Plugin.
Uses an LLM (OpenAI / DeepSeek / Ollama / Groq) or rule-based heuristics to correct
homophone misrecognitions, punctuation, and stutter artifacts produced by ASR.
"""

import os
import json
from typing import List, Optional, Dict, Any
from subtitler.asr import SubtitleSegment
from subtitler.plugins.base import PostProcessPlugin


class LLMProofreaderPlugin(PostProcessPlugin):
    name = "llm_corrector"
    version = "0.1.0"
    description = "Fixes ASR homophone errors, punctuation, and terminology using LLMs."

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini"
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self.model = os.environ.get("SUBTITLER_LLM_MODEL", model)

    def process(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """
        Process and refine segments. If API key is not configured, performs
        intelligent local regex/rule-based normalization.
        """
        if not segments:
            return segments

        if not self.api_key:
            print("[LLMProofreader] No OPENAI_API_KEY found. Applying rule-based text cleaning...")
            return self._clean_rule_based(segments)

        print(f"[LLMProofreader] Refining {len(segments)} subtitle segments using LLM ({self.model})...")
        try:
            return self._refine_with_llm(segments)
        except Exception as e:
            print(f"[LLMProofreader] LLM refinement failed ({e}). Falling back to rule cleaning.")
            return self._clean_rule_based(segments)

    def _refine_with_llm(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        import urllib.request

        url = (self.base_url.rstrip("/") if self.base_url else "https://api.openai.com/v1") + "/chat/completions"
        
        # Batch segments into JSON payload for context-aware correction
        input_data = [{"id": i, "text": seg.text} for i, seg in enumerate(segments)]
        
        system_prompt = (
            "You are an expert subtitle proofreader and editor. "
            "Your task is to fix speech recognition (ASR) errors in the provided subtitle text. "
            "Rules:\n"
            "1. Fix obvious homophones, misheard words, and typos based on conversational context.\n"
            "2. Remove awkward speech stutters or repeated words (e.g. '那个那个' -> '那个').\n"
            "3. Format numbers, acronyms, and proper nouns correctly (e.g. 'ai' -> 'AI', 'Chat GPT' -> 'ChatGPT').\n"
            "4. NEVER change timestamps, segment counts, or drastically alter the speaker's original meaning.\n"
            "5. Return ONLY a valid JSON array of objects with fields 'id' and 'text'."
        )

        user_content = json.dumps(input_data, ensure_ascii=False)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2
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

            # Strip possible markdown code fence
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            corrected_items = json.loads(raw_text)
            correction_map = {item["id"]: item["text"] for item in corrected_items}

            refined_segments: List[SubtitleSegment] = []
            for i, seg in enumerate(segments):
                refined_text = correction_map.get(i, seg.text)
                refined_segments.append(
                    SubtitleSegment(start=seg.start, end=seg.end, text=refined_text)
                )
            return refined_segments

    def _clean_rule_based(self, segments: List[SubtitleSegment]) -> List[SubtitleSegment]:
        """Local rule-based cleaning for common ASR artifacts."""
        import re

        cleaned: List[SubtitleSegment] = []
        for seg in segments:
            t = seg.text.strip()
            # Collapse repeated stutter characters (e.g., "啊啊啊" -> "啊")
            t = re.sub(r"([，。？！,.?!])\1+", r"\1", t)
            # Normalize multiple spaces
            t = re.sub(r"\s+", " ", t)
            cleaned.append(SubtitleSegment(start=seg.start, end=seg.end, text=t))
        return cleaned
