"""
Unit and integration tests for video-subtitler.
"""

import os
import subprocess
import pytest
from subtitler.ffmpeg_utils import get_ffmpeg_path, extract_audio
from subtitler.asr import SubtitleSegment
from subtitler.subtitle import format_timestamp_srt, format_timestamp_ass, save_to_srt, save_to_ass
from subtitler.burner import burn_subtitles_to_video


def test_ffmpeg_discovery():
    ffmpeg_exe = get_ffmpeg_path()
    assert os.path.exists(ffmpeg_exe), f"FFmpeg not found at {ffmpeg_exe}"
    res = subprocess.run([ffmpeg_exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert res.returncode == 0


def test_subtitle_formatting():
    assert format_timestamp_srt(0.0) == "00:00:00,000"
    assert format_timestamp_srt(65.5) == "00:01:05,500"
    assert format_timestamp_ass(65.5) == "0:01:05.50"

    segments = [
        SubtitleSegment(start=0.5, end=2.0, text="你好，世界"),
        SubtitleSegment(start=2.5, end=4.0, text="Hello World")
    ]
    srt_file = "test_output.srt"
    try:
        save_to_srt(segments, srt_file)
        assert os.path.exists(srt_file)
        with open(srt_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "00:00:00,500 --> 00:00:02,000" in content
            assert "你好，世界" in content
    finally:
        if os.path.exists(srt_file):
            os.remove(srt_file)


def test_video_burning(tmp_path):
    # 1. Generate a 2-second blank test video with test tone using ffmpeg
    ffmpeg = get_ffmpeg_path()
    test_video = str(tmp_path / "test_input.mp4")
    test_srt = str(tmp_path / "test_sub.srt")
    test_output_video = str(tmp_path / "test_output.mp4")

    # Create dummy srt
    segments = [SubtitleSegment(start=0.0, end=1.5, text="Testing Subtitle Burn")]
    save_to_srt(segments, test_srt)

    # Create test video with ffmpeg: 2s 320x240 black video with silent audio
    gen_cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2",
        "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
        "-t", "2",
        "-c:v", "libx264", "-c:a", "aac",
        test_video
    ]
    subprocess.run(gen_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert os.path.exists(test_video)

    # 2. Burn subtitle
    burned_path = burn_subtitles_to_video(
        video_path=test_video,
        subtitle_path=test_srt,
        output_video_path=test_output_video
    )
    assert os.path.exists(burned_path)
    assert os.path.getsize(burned_path) > 0
