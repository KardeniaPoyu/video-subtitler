import copy
import hashlib
import json

import pytest
import numpy as np

from subtitler.asr import SubtitleSegment
from subtitler.delivery import deliver, demo
from subtitler.project import Project


def project():
    return Project(path="", target_lang="zh", segments=[
        {"id": 1, "start": 0.0, "end": 3.0, "text": "Hello world.", "translation": "你好，世界。"},
        {"id": 2, "start": 4.0, "end": 6.0, "text": "Goodbye.", "translation": "再见。"},
    ])


def test_bundle_can_be_reopened_and_hashes_match(tmp_path):
    dest = demo(str(tmp_path / "delivery"))
    assert len(Project.load(str(dest / "project.json")).segments) == 2
    manifest = json.loads((dest / "manifest.json").read_text("utf-8"))
    assert {"subtitles.ass", "subtitles.srt", "subtitles.vtt", "qa.json"} <= manifest["files"].keys()
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        demo(str(dest))


def test_no_output_on_failed_checks_and_draft_is_labeled(tmp_path):
    p = project()
    p.segments[0]["translation"] = ""
    with pytest.raises(ValueError, match="字幕错误"):
        deliver(p, str(tmp_path / "final"))
    assert not (tmp_path / "final").exists()
    out = deliver(p, str(tmp_path / "draft"), draft=True)
    assert json.loads((out / "qa.json").read_text("utf-8"))["status"] == "draft"


def test_edits_are_atomic_and_input_is_unchanged():
    p = project()
    before = copy.deepcopy(p.segments)
    edits = {"1": "新翻译", "2": {"end": -1}, "delete": []}
    original = copy.deepcopy(edits)
    with pytest.raises(ValueError):
        p.apply(edits)
    assert p.segments == before
    assert edits == original


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True, "1"])
def test_bad_timestamps_are_rejected(value):
    p = project()
    p.segments[0]["start"] = value
    with pytest.raises(ValueError):
        p.validate()


def test_duplicate_ids_are_rejected():
    p = project()
    p.segments[1]["id"] = 1
    with pytest.raises(ValueError):
        p.validate()


def test_bundle_redacts_local_paths_and_escapes_html(tmp_path):
    p = project()
    p.video = "/private/name/secret/video.mp4"
    p.segments[0]["translation"] = ""
    p.segments[0]["text"] = "<script>alert(1)</script>"
    out = deliver(p, str(tmp_path / "bundle"), draft=True)
    assert "/private/" not in (out / "project.json").read_text("utf-8")
    assert "<script>" not in (out / "review.html").read_text("utf-8")


@pytest.mark.parametrize("scalar", [np.float32, np.float64])
def test_asr_numpy_timestamps_save_and_deliver(tmp_path, scalar):
    p = Project.from_segments(
        str(tmp_path / "project.json"),
        [SubtitleSegment(scalar(0.0), scalar(3.0), "Welcome to our garden.")],
        source_lang="en",
    )
    p.save()
    reloaded = Project.load(p.path)
    assert type(reloaded.segments[0]["start"]) is float
    assert type(reloaded.segments[0]["end"]) is float
    assert (deliver(reloaded, str(tmp_path / "delivery")) / "subtitles.srt").is_file()
