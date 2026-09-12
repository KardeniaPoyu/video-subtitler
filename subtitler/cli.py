"""
Command Line Interface for Video-Subtitler.
"""

import argparse
import sys
import os
from subtitler import process_video, __version__
from subtitler.plugins.templates import STYLE_TEMPLATES


def main():
    parser = argparse.ArgumentParser(
        prog="subtitler",
        description="Auto-generate subtitles and burn them into video with AI and plugin enhancements."
    )
    parser.add_argument(
        "video_path",
        help="Path to input video file (e.g. mp4, mkv, mov, etc.)"
    )
    parser.add_argument(
        "-m", "--model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: small - recommended balance of speed and accuracy)"
    )
    parser.add_argument(
        "-l", "--lang",
        default=None,
        help="Audio language code (e.g. 'zh', 'en', 'ja'). Auto-detects if not specified."
    )
    parser.add_argument(
        "-o", "--output-video",
        default=None,
        help="Path for output subtitled video file"
    )
    parser.add_argument(
        "-s", "--output-subtitle",
        default=None,
        help="Path for output subtitle file (.srt / .ass / .vtt)"
    )
    parser.add_argument(
        "--format",
        default="srt",
        choices=["srt", "ass", "vtt"],
        help="Subtitle format to generate (default: srt)"
    )
    parser.add_argument(
        "--style",
        default="default",
        choices=list(STYLE_TEMPLATES.keys()),
        help="Visual style template (e.g. bilibili_standard, shorts_punchy, cinema_minimal)"
    )
    parser.add_argument(
        "--kb", "--topic",
        default=None,
        dest="kb",
        help="Domain knowledge base / glossary to load (e.g. 'gaming_nintendo', 'tech_ai', 'anime_acg', 'vlogger_slang')"
    )
    parser.add_argument(
        "--translate",
        default=None,
        help="Target language code for AI translation (e.g. 'en', 'zh')."
    )
    parser.add_argument(
        "--no-bilingual",
        action="store_true",
        help="Generate only translated text rather than dual-row stacked subtitles"
    )
    parser.add_argument(
        "--proofread",
        action="store_true",
        help="Enable AI/LLM proofreader plugin to fix homophone misrecognitions and punctuation"
    )
    parser.add_argument(
        "--no-burn",
        action="store_true",
        help="Only generate subtitle file without burning into video"
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        help="Keep the extracted 16kHz audio file"
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional initial prompt to guide Whisper terminology or punctuation"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"video-subtitler {__version__}"
    )

    args = parser.parse_args()

    if not os.path.exists(args.video_path):
        print(f"Error: Input video not found: {args.video_path}", file=sys.stderr)
        sys.exit(1)

    # If style specified and format is default srt, auto-switch to ass if needed for advanced styling
    fmt = args.format
    if args.style != "default" and fmt == "srt":
        fmt = "ass"

    try:
        result = process_video(
            video_path=args.video_path,
            output_video_path=args.output_video,
            output_subtitle_path=args.output_subtitle,
            model_size=args.model,
            language=args.lang,
            burn=not args.no_burn,
            subtitle_format=fmt,
            keep_audio=args.keep_audio,
            initial_prompt=args.prompt,
            proofread=args.proofread,
            translate=args.translate,
            bilingual=not args.no_bilingual,
            style=args.style,
            topic=args.kb
        )
        print("\n================ Processing Complete ================")
        print(f"Subtitle: {result['subtitle_path']}")
        if result['video_path']:
            print(f"Subtitled Video: {result['video_path']}")
        print(f"Segments: {result['segment_count']}")
        print(f"Style Template: {result['style']}")
        print("=====================================================\n")
    except Exception as e:
        print(f"\n[Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
