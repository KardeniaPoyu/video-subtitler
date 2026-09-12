"""
Video-Subtitler: Automated Video Subtitle Generator and Hardsub Burner.
"""

import os
from typing import Optional, Dict, Any

from subtitler.ffmpeg_utils import get_ffmpeg_path, extract_audio
from subtitler.asr import WhisperTranscriber, SubtitleSegment
from subtitler.subtitle import save_to_srt, save_to_vtt, save_to_ass
from subtitler.burner import burn_subtitles_to_video
from subtitler.plugins.manager import PluginManager

__version__ = "0.2.0"


def process_video(
    video_path: str,
    output_video_path: Optional[str] = None,
    output_subtitle_path: Optional[str] = None,
    model_size: str = "small",
    language: Optional[str] = None,
    burn: bool = True,
    subtitle_format: str = "srt",
    keep_audio: bool = False,
    device: Optional[str] = None,
    initial_prompt: Optional[str] = None,
    proofread: bool = False,
    translate: Optional[str] = None,
    style: str = "default",
    topic: Optional[str] = None,
    plugin_manager: Optional[PluginManager] = None,
    knowledge_engine: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Complete end-to-end pipeline with plugin & knowledge base architecture:
    1. Extract audio from video
    2. Condition Whisper with domain hotwords & transcribe
    3. Run KnowledgeBase phonetic error corrections (カビー -> カービィ)
    4. Run Post-Processing & Translation plugins
    5. Enforce domain glossary translations
    6. Generate subtitle file (.srt / .ass / .vtt) with selected StyleTemplate
    7. Burn hard subtitles into video (if burn=True)
    
    :return: Dictionary containing output paths and metadata.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    from subtitler.knowledge import KnowledgeEngine
    ke = knowledge_engine or KnowledgeEngine()
    detected_topic = topic or ke.auto_detect_domain(video_path)
    if detected_topic:
        print(f"[KnowledgeEngine] Activated domain knowledge base: '{detected_topic}'")

    base, _ = os.path.splitext(video_path)
    pm = plugin_manager or PluginManager()

    # 1. Extract audio
    print(f"\n[1/5] Extracting audio from {os.path.basename(video_path)}...")
    temp_audio = extract_audio(video_path)

    try:
        # 2. Transcribe with knowledge base prompt conditioning
        asr_prompt = initial_prompt or (ke.get_asr_prompt(detected_topic) if detected_topic else None)
        print(f"\n[2/5] Transcribing audio with Whisper '{model_size}' model...")
        if asr_prompt:
            print(f"[KnowledgeEngine] Injecting domain hotwords into ASR prompt...")

        transcriber = WhisperTranscriber(model_size=model_size, device=device)
        segments = transcriber.transcribe(
            temp_audio,
            language=language,
            initial_prompt=asr_prompt
        )

        if not segments:
            print("[Warning] No speech detected in video.")

        # Apply KnowledgeBase phonetic corrections to segments
        if detected_topic and segments:
            for s in segments:
                s.text = ke.correct_phonetics(s.text, domain=detected_topic)

        # 3. Apply Plugins: Post-processing (LLM Proofreading)
        if proofread:
            print("\n[3/5] Applying Post-Processing plugins (Proofreading)...")
            segments = pm.apply_post_processing(segments, enable_proofread=True)

        # 4. Apply Plugins: Translation / Bilingual
        if translate:
            print(f"\n[4/5] Applying Translation plugin (Target: {translate})...")
            segments = pm.apply_translation(
                segments,
                target_lang=translate,
                source_lang=language,
                bilingual=bilingual
            )
            # Enforce authoritative domain glossary translations
            if detected_topic:
                for s in segments:
                    s.text = ke.apply_glossary(s.text, domain=detected_topic)

        # 5. Generate Subtitles
        print(f"\n[5/5] Exporting {subtitle_format.upper()} subtitle file with style '{style}'...")
        sub_ext = f".{subtitle_format.lower()}"
        if output_subtitle_path is None:
            output_subtitle_path = f"{base}{sub_ext}"

        if subtitle_format.lower() == "ass":
            save_to_ass(segments, output_subtitle_path, template=style)
        elif subtitle_format.lower() == "vtt":
            save_to_vtt(segments, output_subtitle_path)
        else:
            save_to_srt(segments, output_subtitle_path)

        print(f"Subtitle saved to: {output_subtitle_path}")

        # Burn subtitles into video
        final_video = None
        if burn:
            print(f"\nBurning hard subtitles into video using style '{style}'...")
            final_video = burn_subtitles_to_video(
                video_path=video_path,
                subtitle_path=output_subtitle_path,
                output_video_path=output_video_path
            )
        else:
            print("\nSkipping video burn as requested (--no-burn).")

        return {
            "success": True,
            "subtitle_path": output_subtitle_path,
            "video_path": final_video,
            "segment_count": len(segments),
            "model": model_size,
            "style": style
        }

    finally:
        if not keep_audio and os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except OSError:
                pass
