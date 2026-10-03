"""
Video-Subtitler: Whisper transcription, domain-aware correction, LLM / agent translation,
styled bilingual subtitles, quality checks, hardsub burning and chapters.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

from subtitler.asr import SubtitleSegment, WhisperTranscriber
from subtitler.burner import burn_subtitles_to_video
from subtitler.ffmpeg_utils import extract_audio, get_ffmpeg_path, probe_video
from subtitler.plugins.manager import PluginManager
from subtitler.subtitle import save_subtitles, save_to_ass, save_to_srt, save_to_vtt

__version__ = "0.3.0"


def _domains_arg(topic) -> Optional[List[str]]:
    if not topic:
        return None
    return [t.strip() for t in (topic.split(",") if isinstance(topic, str) else topic) if t.strip()]


def transcribe_video(
    video_path: str,
    model_size: str = "auto",
    language: Optional[str] = None,
    device: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    topic=None,
    kb_files: Sequence[str] = (),
    keep_audio: bool = False,
    knowledge_engine=None,
    word_split: bool = True,
):
    """
    Extract audio, run Whisper with domain hotwords, apply phonetic corrections.
    Returns (segments, meta) where meta has detected language, domains, video info, model.
    """
    from subtitler.knowledge import KnowledgeEngine

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    ke = knowledge_engine or KnowledgeEngine(extra_files=kb_files)
    domains = _domains_arg(topic) or ([d] if (d := ke.auto_detect_domain(video_path)) else [])
    if domains:
        print(f"[Knowledge] Domains: {', '.join(domains)}")

    info = probe_video(video_path)
    print(f"[Video] {info.width}x{info.height} @ {info.fps:g}fps, {info.duration:.1f}s, audio={info.has_audio}")
    if not info.has_audio:
        raise RuntimeError("The input has no audio stream - nothing to transcribe.")

    import tempfile
    audio_dir = os.path.dirname(os.path.abspath(video_path)) if keep_audio else tempfile.gettempdir()
    audio_path = os.path.join(audio_dir, os.path.splitext(os.path.basename(video_path))[0] + "_audio_16k.wav")
    print("[1/3] Extracting 16 kHz audio...")
    extract_audio(video_path, audio_path)
    try:
        hotwords = ke.get_asr_prompt(domains, max_words=60) if domains else None
        print("[2/3] Transcribing" + (" (with domain hotwords)" if hotwords else "") + "...")
        tr = WhisperTranscriber(model_size=model_size, device=device)
        segments = tr.transcribe(audio_path, language=language, initial_prompt=initial_prompt,
                                 hotwords=hotwords, word_split=word_split)
        lang = language or getattr(tr, "detected_language", None)
    finally:
        if not keep_audio and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass

    if not domains and segments:
        domains = ke.detect_from_segments(segments)
        if domains:
            print(f"[Knowledge] Detected from transcript: {', '.join(domains)}")
    raw = [s.text for s in segments]
    if domains:
        for s in segments:
            s.text = ke.correct_phonetics(s.text, domains)
        fixed = sum(a != s.text for a, s in zip(raw, segments))
        print(f"[3/3] Applied ASR corrections to {fixed} lines.")
    meta = {"language": lang, "domains": domains, "video_info": info, "model": tr.model_size, "raw": raw}
    return segments, meta


def process_video(
    video_path: str,
    output_video_path: Optional[str] = None,
    output_subtitle_path: Optional[str] = None,
    model_size: str = "auto",
    language: Optional[str] = None,
    burn: bool = True,
    subtitle_format: str = "srt",
    keep_audio: bool = False,
    device: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    proofread: bool = False,
    translate: Optional[str] = None,
    bilingual: bool = True,
    style: str = "default",
    topic=None,
    kb_files: Sequence[str] = (),
    plugin_manager: Optional[PluginManager] = None,
    knowledge_engine: Optional[Any] = None,
    save_project: bool = True,
) -> Dict[str, Any]:
    """
    One-shot pipeline: transcribe -> (proofread) -> (translate) -> glossary -> subtitles -> (burn).
    Also writes ``<video>.subtitler.json`` so the result can be refined with the CLI afterwards.
    """
    from subtitler.knowledge import KnowledgeEngine
    from subtitler.project import Project, default_project_path

    ke = knowledge_engine or KnowledgeEngine(extra_files=kb_files)
    pm = plugin_manager or PluginManager()
    segments, meta = transcribe_video(video_path, model_size, language, device, initial_prompt,
                                      topic, kb_files, keep_audio, ke)
    domains = meta["domains"]
    if not segments:
        print("[Warning] No speech detected.")

    if proofread and segments:
        for p in pm.post_processors:
            if hasattr(p, "hotwords"):
                p.hotwords = ke.get_hotwords(domains) if domains else []
        segments = pm.apply_post_processing(segments, enable_proofread=True)

    if translate and segments:
        for t in pm.translators:
            if hasattr(t, "glossary_hints") and domains:
                t.glossary_hints = lambda text, _d=domains: ke.glossary_hints(text, _d)
        segments = pm.apply_translation(segments, target_lang=translate,
                                        source_lang=meta["language"], bilingual=bilingual)
        if domains:
            for s in segments:
                if s.translation:
                    s.translation = ke.apply_glossary(s.translation, domains)

    info = meta["video_info"]
    project_path = None
    if save_project:
        proj = Project.from_segments(default_project_path(video_path), segments,
                                     video=os.path.abspath(video_path),
                                     video_info={"width": info.width, "height": info.height,
                                                 "duration": info.duration, "fps": info.fps},
                                     source_lang=meta["language"], target_lang=translate,
                                     domains=domains, kb_files=list(kb_files), model=meta["model"])
        for seg, raw in zip(proj.segments, meta["raw"]):
            seg["asr"] = raw
        project_path = proj.save()

    base, _ = os.path.splitext(video_path)
    fmt = subtitle_format.lower()
    if output_subtitle_path is None:
        output_subtitle_path = f"{base}.{fmt}"
    mode = "bilingual" if (translate and bilingual) else ("target" if translate else "source")
    if fmt == "ass":
        save_to_ass(segments, output_subtitle_path, template=style, mode=mode, video_size=info.size)
    elif fmt == "vtt":
        save_to_vtt(segments, output_subtitle_path, mode=mode)
    else:
        save_to_srt(segments, output_subtitle_path, mode=mode)
    print(f"Subtitle saved to: {output_subtitle_path}")

    final_video = None
    if burn and segments:
        final_video = burn_subtitles_to_video(video_path, output_subtitle_path, output_video_path)

    return {
        "success": True,
        "subtitle_path": output_subtitle_path,
        "video_path": final_video,
        "project_path": project_path,
        "segment_count": len(segments),
        "model": meta["model"],
        "style": style,
        "domains": domains,
        "language": meta["language"],
    }
