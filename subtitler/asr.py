"""
Speech Recognition (ASR) powered by faster-whisper.

* Auto-selects device / compute type / model size (CUDA -> large-v3-turbo, CPU -> small).
* Domain hotwords are passed via ``hotwords`` (applied to *every* 30 s window), while
  ``initial_prompt`` only conditions the first window.
* Long Whisper segments are re-cut into subtitle-sized events using word timestamps.
* Timing is normalised: no overlaps, minimum display time, short linger after speech.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, List, Optional

from subtitler.wrapper import display_width


@dataclass
class SubtitleSegment:
    start: float  # seconds
    end: float    # seconds
    text: str     # source-language text
    translation: Optional[str] = None  # target-language text (bilingual / translated output)


AUTO_MODEL_GPU = "large-v3-turbo"
AUTO_MODEL_CPU = "small"

SENTENCE_PUNCT = set("。！？!?…")
CLAUSE_PUNCT = set("、，,;；:：")


def add_cuda_dll_dirs() -> List[str]:
    """
    Windows: make pip-installed CUDA runtimes visible to CTranslate2
    (``pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*``). Returns the directories added.
    """
    added: List[str] = []
    if os.name != "nt":
        return added
    import site
    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    for root in roots:
        base = os.path.join(root, "nvidia")
        if not os.path.isdir(base):
            continue
        for pkg in os.listdir(base):
            d = os.path.join(base, pkg, "bin")
            if os.path.isdir(d) and d not in added:
                try:
                    os.add_dll_directory(d)
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                added.append(d)
    return added


def cuda_runtime_status() -> str:
    """'ok', or a short reason why CUDA Whisper inference will not work."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0:
            return "no CUDA device"
    except Exception as e:
        return f"ctranslate2 unavailable ({e})"
    if os.name == "nt":
        import ctypes
        add_cuda_dll_dirs()
        for dll in ("cublas64_12.dll", "cudnn_ops64_9.dll"):
            try:
                ctypes.WinDLL(dll)
            except OSError:
                return (f"{dll} not found - install with: pip install nvidia-cublas-cu12 \"nvidia-cudnn-cu12==9.*\""
                        " (or put the CUDA 12 / cuDNN 9 DLLs on PATH)")
    return "ok"


def resolve_device(device: Optional[str] = None) -> str:
    if device and device != "auto":
        return device
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = "auto",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        download_root: Optional[str] = None,
    ):
        """
        :param model_size: 'auto', 'tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo', ...
                           or a path to a local CTranslate2 model directory.
        :param device: 'cuda', 'cpu', or None/'auto'.
        :param compute_type: 'float16', 'int8_float16', 'int8', ... (auto if None).
        """
        from faster_whisper import WhisperModel

        add_cuda_dll_dirs()
        device = resolve_device(device)
        auto_model = model_size in (None, "", "auto")
        if auto_model:
            model_size = AUTO_MODEL_GPU if device == "cuda" else AUTO_MODEL_CPU
        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"

        self.device = device
        self.compute_type = compute_type
        self.model_size = model_size

        print(f"[ASR] Loading model '{model_size}' on {device.upper()} ({compute_type})...")
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type,
                                      download_root=download_root)
            if device == "cuda":
                # Verify the CUDA runtime really works (cuBLAS / cuDNN DLLs present).
                import numpy as np
                gen, _ = self.model.transcribe(np.zeros(16000, dtype=np.float32))
                next(iter(gen), None)
        except Exception as e:
            if device != "cuda":
                raise
            if auto_model:
                model_size = self.model_size = AUTO_MODEL_CPU
            print(f"[ASR] CUDA runtime unavailable ({e}). Falling back to CPU (int8, model '{model_size}')...")
            self.device, self.compute_type = "cpu", "int8"
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8",
                                      download_root=download_root)

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
        hotwords: Optional[str] = None,
        word_split: bool = True,
        max_event_chars: float = 40,
        max_event_seconds: float = 7.0,
    ) -> List[SubtitleSegment]:
        """
        Transcribe an audio file into subtitle-sized segments.

        :param hotwords: comma/、-separated domain terms that bias every decoding window.
        :param word_split: re-cut long segments on word timestamps into readable events.
        :param max_event_chars: max width (em; CJK char = 1) of one subtitle event before splitting.
        :param max_event_seconds: max duration of one subtitle event before splitting.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        kwargs: dict = dict(
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=200),
            initial_prompt=initial_prompt,
            word_timestamps=word_split,
            condition_on_previous_text=True,
        )
        if hotwords:
            kwargs["hotwords"] = hotwords

        print(f"[ASR] Transcribing {os.path.basename(audio_path)}...")
        try:
            segments, info = self.model.transcribe(audio_path, **kwargs)
        except TypeError:  # very old faster-whisper without `hotwords`
            kwargs.pop("hotwords", None)
            segments, info = self.model.transcribe(audio_path, **kwargs)

        self.detected_language = info.language
        print(f"[ASR] Detected language: {info.language} (p={info.language_probability:.2f}), "
              f"duration {info.duration:.1f}s")

        results: List[SubtitleSegment] = []
        # Word timings from all Whisper segments are pooled and re-segmented together, so event
        # boundaries follow pauses and punctuation instead of Whisper's internal segment cuts
        # (which otherwise leave fragments like "But this" / "is actually a bad idea").
        words: List[Any] = []

        def flush_words():
            if words:
                results.extend(resegment_words(words, max_event_chars, max_event_seconds))
                words.clear()

        last_report = 0.0
        for s in segments:
            if word_split and getattr(s, "words", None):
                words.extend(s.words)
            else:
                flush_words()
                text = s.text.strip()
                if text:
                    results.append(SubtitleSegment(s.start, s.end, text))
            if info.duration and s.end - last_report > 60:
                last_report = s.end
                print(f"[ASR] ... {s.end / info.duration * 100:5.1f}%  ({s.end:.0f}/{info.duration:.0f}s)")

        flush_words()
        results = collapse_repeats(results)
        results = normalize_timing(results)
        print(f"[ASR] Transcribed {len(results)} subtitle events.")
        return results


def resegment_words(words: List[Any], max_chars: float = 40, max_seconds: float = 7.0,
                    pause_split: float = 0.8) -> List[SubtitleSegment]:
    """
    Turn one Whisper segment's word timings into subtitle events:
      1. split at long pauses and sentence ends (one sentence per event when possible),
      2. recursively split any piece that is still too wide / too long at the best boundary
         (clause punctuation > pauses > spaces), keeping both halves balanced - so no
         orphan one-word events like "Direct.".
    """
    words = [w for w in words if w.word.strip()]
    if not words:
        return []

    def text_of(ws: List[Any]) -> str:
        return "".join(w.word for w in ws).strip()

    def tail(w: Any) -> str:
        t = w.word.strip()
        return t[-1:] if t else ""

    # pass 1: hard boundaries (pauses, sentence punctuation)
    pieces: List[List[Any]] = []
    cur: List[Any] = []
    for k, w in enumerate(words):
        if cur and w.start - cur[-1].end >= pause_split:
            pieces.append(cur)
            cur = []
        cur.append(w)
        if tail(w) in SENTENCE_PUNCT or (tail(w) == "." and not re.search(r"\d\.$", w.word.strip())):
            if display_width(text_of(cur)) >= 4:
                pieces.append(cur)
                cur = []
    if cur:
        if pieces and display_width(text_of(cur)) < 4 and cur[0].start - pieces[-1][-1].end < pause_split:
            pieces[-1].extend(cur)  # glue a tiny trailing fragment to the previous sentence
        else:
            pieces.append(cur)

    # pass 2: recursive balanced split of oversize pieces
    def split(ws: List[Any]) -> List[List[Any]]:
        width = display_width(text_of(ws))
        dur = ws[-1].end - ws[0].start
        if len(ws) < 2 or (width <= max_chars and dur <= max_seconds):
            return [ws]
        best_k, best_score = 1, float("-inf")
        for k in range(1, len(ws)):
            left_w = display_width(text_of(ws[:k]))
            right_w = width - left_w
            prev = ws[k - 1].word.strip()
            score = -abs(left_w - right_w) / max(width, 1) * 40
            if prev[-1:] in SENTENCE_PUNCT or prev.endswith("."):
                score += 45
            elif prev[-1:] in CLAUSE_PUNCT or prev.endswith(","):
                score += 30
            score += min(ws[k].start - ws[k - 1].end, 1.0) * 40
            if ws[k].word.startswith(" "):
                score += 5  # Latin word boundary
            if min(left_w, right_w) < 4:
                score -= 60  # orphan
            if score > best_score:
                best_k, best_score = k, score
        return split(ws[:best_k]) + split(ws[best_k:])

    events: List[SubtitleSegment] = []
    for piece in pieces:
        for chunk in split(piece):
            t = text_of(chunk)
            if t:
                events.append(SubtitleSegment(chunk[0].start, chunk[-1].end, t))
    return events


def collapse_repeats(segments: List[SubtitleSegment], max_repeat: int = 2) -> List[SubtitleSegment]:
    """Drop Whisper hallucination loops (the same line repeated many times in a row)."""
    out: List[SubtitleSegment] = []
    run = 0
    for s in segments:
        if out and re.sub(r"\W", "", s.text) == re.sub(r"\W", "", out[-1].text):
            run += 1
            if run >= max_repeat:
                out[-1].end = max(out[-1].end, s.end)
                continue
        else:
            run = 0
        out.append(s)
    return out


def close_gaps(segments: List[SubtitleSegment], max_gap: float = 0.3) -> List[SubtitleSegment]:
    """Chain consecutive lines whose gap is shorter than ``max_gap`` (the subtitle would otherwise
    blink off for a frame or two between them)."""
    for a, b in zip(segments, segments[1:]):
        if 0 < b.start - a.end < max_gap:
            a.end = b.start
    return segments


def normalize_timing(segments: List[SubtitleSegment], min_duration: float = 0.8,
                     linger: float = 0.25, chain_gap: float = 0.3) -> List[SubtitleSegment]:
    """Remove overlaps, enforce a minimum on-screen time, let lines linger briefly after speech and
    chain lines separated by less than ``chain_gap`` seconds."""
    segs = sorted(segments, key=lambda s: s.start)
    for i, s in enumerate(segs):
        want = max(s.end + linger, s.start + min_duration)
        if i + 1 < len(segs):
            nxt = segs[i + 1].start
            if want > nxt or nxt - want < chain_gap:
                want = nxt  # never overlap; close tiny gaps
        s.start = round(s.start, 3)
        s.end = round(max(want, s.start + 0.3), 3)
    return segs
