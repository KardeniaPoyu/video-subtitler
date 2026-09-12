"""
Command Line Interface for Video-Subtitler.
"""

import argparse
import sys
import os
from subtitler import process_video, __version__


def main():
    parser = argparse.ArgumentParser(
        prog="subtitler",
        description="Auto-generate subtitles and burn them into video using AI speech recognition."
    )
    parser.add_argument(
        "video_path",
        help="Path to input video file (e.g. mp4, mkv, mov, etc.)"
    )
    parser.add_argument(
        "-m", "--model",
        default="small",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: small - recommended for balance of speed and accuracy)"
    )
    parser.add_argument(
        "-l", "--lang",
        default=None,
        help="Audio language code (e.g. 'zh' for Chinese, 'en' for English, 'ja' for Japanese). Auto-detects if not specified."
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

    try:
        result = process_video(
            video_path=args.video_path,
            output_video_path=args.output_video,
            output_subtitle_path=args.output_subtitle,
            model_size=args.model,
            language=args.lang,
            burn=not args.no_burn,
            subtitle_format=args.format,
            keep_audio=args.keep_audio,
            initial_prompt=args.prompt
        )
        print("\n================ Processing Complete ================")
        print(f"Subtitle: {result['subtitle_path']}")
        if result['video_path']:
            print(f"Subtitled Video: {result['video_path']}")
        print(f"Segments: {result['segment_count']}")
        print("=====================================================\n")
    except Exception as e:
        print(f"\n[Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
