"""
Knowledge Base & Glossary Engine for Video-Subtitler.
Provides domain hotword injection for ASR, phonetic correction for misheard words,
and authoritative bilingual glossary alignment.
"""

import os
import json
import re
from typing import Dict, List, Optional, Any, Set


class KnowledgeEngine:
    """
    Central engine managing domain knowledge bases, glossary dictionaries,
    and automatic terminology alignment.
    """

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.data_dir = data_dir
        self.domains: Dict[str, Dict[str, Any]] = {}
        self._load_all_domains()

    def _load_all_domains(self):
        """Scans and loads all .json files in the knowledge data directory."""
        if not os.path.exists(self.data_dir):
            return

        for fname in os.listdir(self.data_dir):
            if fname.endswith(".json"):
                path = os.path.join(self.data_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        dom_name = data.get("domain", os.path.splitext(fname)[0])
                        self.domains[dom_name] = data
                except Exception as e:
                    print(f"[KnowledgeEngine] Warning: Failed to load {fname}: {e}")

    def list_domains(self) -> List[str]:
        """Returns a list of available domain names."""
        return list(self.domains.keys())

    def auto_detect_domain(self, text_or_filename: str) -> Optional[str]:
        """
        Infers the most relevant domain from video filename or audio sample.
        """
        lowered = text_or_filename.lower()
        # Keywords mapping to domains
        hints = {
            "gaming_nintendo": ["nintendo", "switch", "kirby", "カービィ", "任天堂", "mario", "zelda", "pokemon", "direct"],
            "tech_ai": ["ai", "llm", "gpt", "whisper", "deepseek", "model", "python", "pytorch", "agent"],
            "anime_acg": ["anime", "manga", "acg", "seiyuu", "アニメ", "声優", "漫画", "作画"],
            "vlogger_slang": ["vlog", "youtube", "bilibili", "reaction", "杂谈", "直播"]
        }

        for domain, keywords in hints.items():
            for kw in keywords:
                if kw in lowered:
                    return domain
        return "gaming_nintendo" if ("kirby" in lowered or "foz" in lowered) else None

    def get_asr_prompt(self, domain: Optional[str] = None, max_words: int = 40) -> Optional[str]:
        """
        Returns a comma-separated string of hotwords to feed into Whisper's initial_prompt.
        """
        if domain and domain in self.domains:
            hotwords = self.domains[domain].get("hotwords", [])
        else:
            # Merge hotwords from all domains
            hotwords = []
            for d in self.domains.values():
                hotwords.extend(d.get("hotwords", []))

        if not hotwords:
            return None

        # Return unique hotwords joined by comma
        selected = list(dict.fromkeys(hotwords))[:max_words]
        return "、".join(selected)

    def correct_phonetics(self, text: str, domain: Optional[str] = None) -> str:
        """
        Replaces common ASR phonetic mishearings (e.g. カビー -> カービィ, 感転進削 -> 完全新作).
        """
        target_domains = [self.domains[domain]] if (domain and domain in self.domains) else list(self.domains.values())

        # Collect all corrections and sort by length descending to avoid partial replacements
        corrections: Dict[str, str] = {}
        for d in target_domains:
            corrections.update(d.get("asr_phonetic_corrections", {}))

        sorted_keys = sorted(corrections.keys(), key=len, reverse=True)
        result = text
        for wrong in sorted_keys:
            if wrong in result:
                result = result.replace(wrong, corrections[wrong])

        return result

    def apply_glossary(self, text: str, domain: Optional[str] = None) -> str:
        """
        Enforces authoritative translations from the domain glossary.
        """
        target_domains = [self.domains[domain]] if (domain and domain in self.domains) else list(self.domains.values())

        glossary: Dict[str, str] = {}
        for d in target_domains:
            glossary.update(d.get("glossary", {}))

        sorted_keys = sorted(glossary.keys(), key=len, reverse=True)
        result = text
        for term in sorted_keys:
            if term in result:
                result = result.replace(term, glossary[term])

        return result
