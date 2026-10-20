"""Real FFmpeg smoke test on an original synthetic clip, without ASR downloads."""
import os
import subprocess
import wave

import pytest

from subtitler.burner import burn_subtitles_to_video
from subtitler.ffmpeg_utils import extract_audio, get_ffmpeg_path, probe_video


def test_generate_extract_and_burn_without_changing_working_directory(tmp_path):
    video = tmp_path / "source.mp4"
    subprocess.run([
        get_ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", "color=c=blue:s=320x240:d=1.5", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=1.5", "-c:v", "libx264", "-c:a", "aac",
        "-shortest", str(video),
    ], check=True, timeout=30)
    info = probe_video(str(video))
    assert info.has_audio and info.width == 320
    audio = extract_audio(str(video), str(tmp_path / "audio.wav"))
    with wave.open(audio) as stream:
        assert stream.getframerate() == 16000 and stream.getnchannels() == 1
    subtitle = tmp_path / "test.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,400\nHello garden.\n", "utf-8")
    destination = tmp_path / "subtitled.mp4"
    before = os.getcwd()
    burn_subtitles_to_video(str(video), str(subtitle), str(destination), use_nvenc=False)
    assert os.getcwd() == before
    assert probe_video(str(destination)).duration > 1
    with pytest.raises(FileExistsError):
        burn_subtitles_to_video(str(video), str(subtitle), str(video), use_nvenc=False)
