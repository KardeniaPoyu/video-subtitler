import copy
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import subtitler
import subtitler.burner as burner
import subtitler.delivery as delivery
from subtitler.asr import SubtitleSegment
from subtitler.knowledge.engine import KnowledgeEngine, MAX_KB_BYTES
from subtitler.project import Project


def sample():
    return Project.from_segments("", [
        SubtitleSegment(0, 3, "Hello garden.", "你好，花园。"),
        SubtitleSegment(3.2, 6, "Please come inside.", "请进来。"),
    ], source_lang="en", target_lang="zh")


def test_stale_loaded_project_cannot_discard_another_edit(tmp_path):
    path = str(tmp_path / "project.json")
    sample().save(path)
    first, stale = Project.load(path), Project.load(path)
    first.apply({"1": "修改一"})
    stale.apply({"2": "修改二"})
    first.save()
    before = Path(path).read_bytes()
    with pytest.raises(RuntimeError, match="其他任务修改"):
        stale.save()
    assert Path(path).read_bytes() == before
    assert not Path(path + ".lock").exists()


def test_split_retry_survives_save_reload(tmp_path):
    p = sample()
    edits = {"1": [{"text": "Hello", "translation": "你好"}, {"text": "garden.", "translation": "花园"}]}
    p.apply(edits)
    p.save(str(tmp_path / "project.json"))
    loaded = Project.load(p.path)
    before = copy.deepcopy(loaded.segments)
    assert loaded.apply(edits)["replayed"] is True
    assert loaded.segments == before


@pytest.mark.parametrize("field,value", [
    ("start", 10**400), ("end", 10**400), ("width", "1920"),
    ("height", []), ("fps", float("inf")),
])
def test_invalid_numeric_metadata_is_validation_error(field, value):
    p = sample()
    if field in {"start", "end"}:
        p.segments[0][field] = value
    else:
        p.video_info[field] = value
    with pytest.raises(ValueError):
        p.validate()


def test_out_of_order_project_is_rejected():
    p = sample()
    p.segments.reverse()
    with pytest.raises(ValueError, match="开始时间"):
        p.validate()


def test_source_mode_ignores_bad_translation_and_target_mode_requires_it(tmp_path):
    p = sample()
    p.segments[0]["translation"] = ""
    p.segments[1]["translation"] = "过长译文" * 100
    output = delivery.deliver(p, str(tmp_path / "source"), mode="source")
    assert "Hello" in (output / "subtitles.srt").read_text("utf-8")
    p.target_lang = None
    for s in p.segments:
        s["translation"] = ""
    with pytest.raises(ValueError, match="字幕错误"):
        delivery.deliver(p, str(tmp_path / "target"), mode="target")
    assert not (tmp_path / "target").exists()


def test_one_snapshot_includes_gap_normalization_and_cross_os_redaction(tmp_path, monkeypatch):
    p = sample()
    p.video = r"C:\Users\private\media\clip.mp4"
    real_check = delivery.check_segments
    def change_original(*args, **kwargs):
        p.segments[0]["translation"] = ""
        return real_check(*args, **kwargs)
    monkeypatch.setattr(delivery, "check_segments", change_original)
    output = delivery.deliver(p, str(tmp_path / "bundle"))
    saved = json.loads((output / "project.json").read_text("utf-8"))
    assert saved["video"] == "clip.mp4"
    assert saved["segments"][0]["translation"] == "你好，花园。"
    assert saved["segments"][0]["end"] == saved["segments"][1]["start"]
    assert "00:00:03,200" in (output / "subtitles.srt").read_text("utf-8")


def test_project_kb_paths_need_approval_and_regular_bounded_files(tmp_path):
    kb = tmp_path / "words.json"
    kb.write_text('{"domain":"demo","glossary":{}}', "utf-8")
    p = sample()
    p.kb_files = [str(kb)]
    with pytest.raises(ValueError, match="明确指定"):
        delivery.deliver(p, str(tmp_path / "unapproved"))
    delivery.deliver(p, str(tmp_path / "approved"), approved_kb_files=[str(kb)])
    kb.write_bytes(b" " * (MAX_KB_BYTES + 1))
    with pytest.raises(ValueError, match="1 MiB"):
        KnowledgeEngine(extra_files=[str(kb)])
    with pytest.raises(ValueError, match="普通文件"):
        KnowledgeEngine(extra_files=[str(tmp_path)])
    if os.name != "nt":
        with pytest.raises(ValueError, match="普通文件"):
            KnowledgeEngine(extra_files=["/dev/zero"])


def test_directory_created_during_delivery_is_not_replaced(tmp_path, monkeypatch):
    target = tmp_path / "bundle"
    publish = delivery.publish_directory
    def competing_publish(source, destination):
        target.mkdir()
        return publish(source, destination)
    monkeypatch.setattr(delivery, "publish_directory", competing_publish)
    with pytest.raises(FileExistsError):
        delivery.deliver(sample(), str(target))
    assert target.is_dir() and list(target.iterdir()) == []


def fake_burn_inputs(tmp_path, monkeypatch):
    video, subtitle = tmp_path / "source.mp4", tmp_path / "source.srt"
    video.write_bytes(b"source")
    subtitle.write_text("subtitle", "utf-8")
    monkeypatch.setattr(burner, "probe_video", lambda _: SimpleNamespace(duration=3))
    monkeypatch.setattr(burner, "get_ffmpeg_path", lambda: "ffmpeg")
    return str(video), str(subtitle)


def test_burn_competing_output_and_failed_retry(tmp_path, monkeypatch):
    inputs = fake_burn_inputs(tmp_path, monkeypatch)
    target = tmp_path / "out.mp4"
    def racing_runner(command, **_):
        Path(command[-1]).write_bytes(b"encoded")
        target.write_bytes(b"other job")
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(burner, "run_ffmpeg", racing_runner)
    with pytest.raises(FileExistsError):
        burner.burn_subtitles_to_video(*inputs, str(target), use_nvenc=False)
    assert target.read_bytes() == b"other job"
    target.unlink()
    def failing_runner(command, **_):
        Path(command[-1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=1, stderr="failure")
    monkeypatch.setattr(burner, "run_ffmpeg", failing_runner)
    with pytest.raises(RuntimeError):
        burner.burn_subtitles_to_video(*inputs, str(target), use_nvenc=False)
    assert not target.exists()
    def success_runner(command, **_):
        Path(command[-1]).write_bytes(b"success")
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(burner, "run_ffmpeg", success_runner)
    burner.burn_subtitles_to_video(*inputs, str(target), use_nvenc=False)
    assert target.read_bytes() == b"success"


@pytest.mark.skipif(os.name == "nt", reason="requires unprivileged POSIX symlinks")
def test_burn_does_not_follow_output_symlink_created_during_encoding(tmp_path, monkeypatch):
    inputs = fake_burn_inputs(tmp_path, monkeypatch)
    target, victim = tmp_path / "out.mp4", tmp_path / "private.txt"
    victim.write_bytes(b"keep me")
    def runner(command, **_):
        Path(command[-1]).write_bytes(b"encoded")
        target.symlink_to(victim)
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(burner, "run_ffmpeg", runner)
    with pytest.raises(FileExistsError):
        burner.burn_subtitles_to_video(*inputs, str(target), use_nvenc=False)
    assert victim.read_bytes() == b"keep me"


def test_run_collisions_fail_before_transcription_or_writes(tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"original")
    outputs = [tmp_path / "source_subtitled.mp4", tmp_path / "source.srt",
               tmp_path / "source.subtitler.json"]
    for path in outputs:
        path.write_bytes(b"user edits")
    monkeypatch.setattr(subtitler, "transcribe_video", lambda *a, **kw: pytest.fail("must not transcribe"))
    with pytest.raises(FileExistsError):
        subtitler.process_video(str(video))
    assert all(p.read_bytes() == b"user edits" for p in outputs)


def test_keep_audio_returns_actual_path(tmp_path, monkeypatch, capsys):
    video = tmp_path / "source.mp4"
    video.touch()
    monkeypatch.setattr(subtitler, "probe_video", lambda _: SimpleNamespace(
        width=320, height=240, fps=25, duration=3, has_audio=True))
    monkeypatch.setattr(subtitler, "extract_audio", lambda a, b: Path(b).write_bytes(b"audio"))
    class Transcriber:
        def __init__(self, **_):
            self.model_size = "fake"
        def transcribe(self, *a, **kw):
            return [SubtitleSegment(0, 3, "hello")]
    monkeypatch.setattr(subtitler, "WhisperTranscriber", Transcriber)
    _, metadata = subtitler.transcribe_video(str(video), keep_audio=True)
    assert Path(metadata["audio_path"]).read_bytes() == b"audio"
    assert metadata["audio_path"] in capsys.readouterr().out
