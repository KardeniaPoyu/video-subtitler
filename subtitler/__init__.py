"""
Video-Subtitler: Automated Video Subtitle Generator and Hardsub Burner.
"""

import os
from typing import Optional, Dict, Any

from subtitler.ffmpeg_utils import get_ffmpeg_path, extract_audio
from subtitler.asr import WhisperTranscriber, SubtitleSegment
from subtitler.subtitle import save_to_srt, save_to_vtt, save_to_ass
from subtitler.burner import burn_subtitles_to_video

__version__ = "0.1.0"


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
    initial_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Complete end-to-end pipeline:
    1. Extract audio from video
    2. Transcribe using faster-whisper
    3. Generate subtitle file (.srt / .ass / .vtt)
    4. Burn hard subtitles into video (if burn=True)
    
    :return: Dictionary containing output paths and metadata.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    base, _ = os.path.splitext(video_path)

    # 1. Extract audio
    print(f"\n[1/4] Extracting audio from {os.path.basename(video_path)}...")
    temp_audio = extract_audio(video_path)

    try:
        # 2. Transcribe
        print(f"\n[2/4] Transcribing audio with Whisper '{model_size}' model...")
        transcriber = WhisperTranscriber(model_size=model_size, device=device)
        segments = transcriber.transcribe(
            temp_audio,
            language=language,
            initial_prompt=initial_prompt
        )

        if not segments:
            print("[Warning] No speech detected in video.")

        # 3. Generate Subtitles
        print(f"\n[3/4] Exporting {subtitle_format.upper()} subtitle file...")
        sub_ext = f".{subtitle_format.lower()}"
        if output_subtitle_path is None:
            output_subtitle_path = f"{base}{sub_ext}"

        if subtitle_format.lower() == "ass":
            save_to_ass(segments, output_subtitle_path)
        elif subtitle_format.lower() == "vtt":
            save_to_vtt(segments, output_subtitle_path)
        else:
            save_to_srt(segments, output_subtitle_path)

        print(f"Subtitle saved to: {output_subtitle_path}")

        # 4. Burn subtitles into video
        final_video = None
        if burn:
            print(f"\n[4/4] Burning hard subtitles into video...")
            final_video = burn_subtitles_to_video(
                video_path=video_path,
                subtitle_path=output_subtitle_path,
                output_video_path=output_video_path
            )
        else:
            print("\n[4/4] Skipping video burn as requested (--no-burn).")

        return {
            "success": True,
            "subtitle_path": output_subtitle_path,
            "video_path": final_video,
            "segment_count": len(segments),
            "model": model_size
        }

    finally:
        # Clean up temporary audio file unless requested to keep
        if not keep_audio and os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except OSError:
                pass
