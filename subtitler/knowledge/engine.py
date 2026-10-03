"""
Knowledge Base & Glossary Engine.

Each domain JSON (``knowledge/data/*.json`` or a project-local file) may contain:
  * ``hotwords``                – terms used to bias Whisper (passed as faster-whisper ``hotwords``)
  * ``asr_phonetic_corrections`` – mishearing -> correct source text   (applied to the transcript)
  * ``glossary``                – source term -> authoritative translation (enforced on translations,
                                  and shown to the translator as hints)
  * ``keywords``                – optional extra words for automatic domain detection

Replacements are done in a single regex pass (longest match first), so a correction can never
be re-corrected, and already-correct target terms are protected (``エヴァ -> エヴァンゲリオン``
does not turn ``エヴァンゲリオン`` into ``エヴァンゲリオンンゲリオン``). ASCII keys match
case-insensitively on word boundaries (``ai`` never matches inside ``rain``).
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

DomainSpec = Union[None, str, Sequence[str]]

_DETECT_HINTS = {
    "gaming_nintendo": ["nintendo", "switch", "kirby", "mario", "zelda", "pokemon", "splatoon",
                        "カービィ", "任天堂", "ニンテンドー", "ニンダイ", "マリオ", "ゼルダ", "ポケモン", "卡比", "任天堂直面会"],
    "tech_ai": ["ai", "llm", "gpt", "chatgpt", "whisper", "deepseek", "pytorch", "transformer", "agent",
                "人工智能", "大模型", "大语言模型", "机器学习"],
    "anime_acg": ["anime", "manga", "acg", "seiyuu", "アニメ", "声優", "漫画", "作画", "番剧", "动漫"],
    "vlogger_slang": ["vlog", "reaction", "杂谈", "直播", "雑談", "生放送", "チャンネル登録"],
}


def _is_ascii_word(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .+\-']*", s))


def _key_pattern(key: str) -> str:
    esc = re.escape(key)
    if _is_ascii_word(key):
        return r"(?<![A-Za-z0-9])" + esc + r"(?![A-Za-z0-9])"
    return esc


def build_replacer(mapping: Dict[str, str], protect_targets: bool = True):
    """Compile a single-pass, longest-first replacement function for ``mapping``."""
    table: Dict[str, str] = {}
    lower_ascii: Dict[str, str] = {}
    for k, v in mapping.items():
        if not k:
            continue
        table[k] = v
    if protect_targets:
        for v in mapping.values():
            if v and v not in table:
                table[v] = v  # identity: an already-correct term is consumed and left untouched
    if not table:
        return lambda text: text
    keys = sorted(table, key=len, reverse=True)
    for k in keys:
        if _is_ascii_word(k):
            lower_ascii.setdefault(k.lower(), table[k])
    pattern = re.compile("|".join(_key_pattern(k) for k in keys), re.IGNORECASE)

    def repl(m: "re.Match[str]") -> str:
        s = m.group(0)
        if s in table:
            return table[s]
        return lower_ascii.get(s.lower(), s)

    return lambda text: pattern.sub(repl, text) if text else text


class KnowledgeEngine:
    """Loads domain knowledge bases and applies hotwords, ASR corrections and glossary rules."""

    def __init__(self, data_dir: Optional[str] = None, extra_files: Iterable[str] = ()):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
        self.data_dir = data_dir
        self.domains: Dict[str, Dict] = {}
        self._cache: Dict[Tuple[str, Tuple[str, ...]], object] = {}
        self._load_dir(data_dir)
        for path in extra_files:
            self.load_file(path)

    # ------------------------------------------------------------------ loading
    def _load_dir(self, data_dir: str) -> None:
        if not os.path.isdir(data_dir):
            return
        for fname in sorted(os.listdir(data_dir)):
            if fname.endswith(".json"):
                self.load_file(os.path.join(data_dir, fname))

    def load_file(self, path: str) -> str:
        """Load (or merge into) a domain from a JSON file. Returns the domain name."""
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[KnowledgeEngine] Warning: failed to load {path}: {e}")
            return ""
        name = data.get("domain") or os.path.splitext(os.path.basename(path))[0]
        if name in self.domains:  # merge: project-local entries override the built-in ones
            base = self.domains[name]
            base["hotwords"] = list(dict.fromkeys(base.get("hotwords", []) + data.get("hotwords", [])))
            for key in ("asr_phonetic_corrections", "glossary"):
                base.setdefault(key, {}).update(data.get(key, {}))
        else:
            self.domains[name] = data
        self._cache.clear()
        return name

    def list_domains(self) -> List[str]:
        return list(self.domains.keys())

    def _resolve(self, domain: DomainSpec) -> List[str]:
        if domain is None:
            return list(self.domains)
        names = [d.strip() for d in (domain.split(",") if isinstance(domain, str) else domain) if d and d.strip()]
        unknown = [d for d in names if d not in self.domains]
        if unknown:
            print(f"[KnowledgeEngine] Warning: unknown domain(s) {unknown}; available: {self.list_domains()}")
        return [d for d in names if d in self.domains]

    def _merged(self, key: str, domain: DomainSpec) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        for d in self._resolve(domain):
            merged.update(self.domains[d].get(key, {}))
        return merged

    # ------------------------------------------------------------------ detection
    def auto_detect_domain(self, text_or_filename: str) -> Optional[str]:
        """Guess a domain from a file name / title (basename only, word-boundary matching)."""
        detected = self.detect_domains(os.path.basename(text_or_filename))
        return detected[0] if detected else None

    def detect_domains(self, text: str, min_score: int = 1) -> List[str]:
        """Score every domain by keyword + hotword hits in ``text`` (title or transcript)."""
        scores: Dict[str, int] = {}
        for name, data in self.domains.items():
            words = set(_DETECT_HINTS.get(name, [])) | set(data.get("keywords", []))
            words |= {h for h in data.get("hotwords", []) if len(h) >= 3}
            score = 0
            for w in words:
                pat = _key_pattern(w)
                score += len(re.findall(pat, text, flags=re.IGNORECASE))
            if score >= min_score:
                scores[name] = score
        return sorted(scores, key=lambda k: -scores[k])

    def detect_from_segments(self, segments, min_score: int = 3) -> List[str]:
        text = "\n".join(s.text for s in segments)
        found = self.detect_domains(text, min_score=min_score)
        return found[:2]

    # ------------------------------------------------------------------ application
    def get_hotwords(self, domain: DomainSpec = None, max_words: int = 60) -> List[str]:
        words: List[str] = []
        for d in self._resolve(domain):
            words.extend(self.domains[d].get("hotwords", []))
        return list(dict.fromkeys(words))[:max_words]

    def get_asr_prompt(self, domain: DomainSpec = None, max_words: int = 40) -> Optional[str]:
        """Hotwords joined into one string for Whisper ``hotwords`` / ``initial_prompt``."""
        words = self.get_hotwords(domain, max_words)
        return "、".join(words) if words else None

    def _replacer(self, key: str, domain: DomainSpec):
        ck = (key, tuple(self._resolve(domain)))
        if ck not in self._cache:
            self._cache[ck] = build_replacer(self._merged(key, domain))
        return self._cache[ck]

    def correct_phonetics(self, text: str, domain: DomainSpec = None) -> str:
        """Fix known ASR mishearings in source-language text (e.g. カビー -> カービィ)."""
        return self._replacer("asr_phonetic_corrections", domain)(text)

    def apply_glossary(self, text: str, domain: DomainSpec = None) -> str:
        """Force authoritative translations of source terms left untranslated in target text."""
        return self._replacer("glossary", domain)(text)

    def glossary_hints(self, text: str, domain: DomainSpec = None) -> List[Tuple[str, str]]:
        """Glossary entries whose source term occurs in ``text`` (to show the translator)."""
        out = []
        for src, tgt in self._merged("glossary", domain).items():
            if src and src != tgt and re.search(_key_pattern(src), text, flags=re.IGNORECASE):
                out.append((src, tgt))
        return out
