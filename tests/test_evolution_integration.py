import copy
import json
import threading

import pytest

from subtitler.cli import main
from subtitler.evolution.demo import demo
from subtitler.evolution.runtime import open_policy
from subtitler.evolution.store import Memory
from subtitler.project import Project


def invoke(args, expected=0):
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == expected


def test_cli_learn_to_final_delivery_and_stale_receipt(tmp_path):
    path = str(tmp_path / "memory.sqlite3")
    invoke(["evolve", "init", "--memory", path])
    p = Project(path=str(tmp_path / "video.json"), source_lang="en", target_lang="zh", domains=["cooking"],
                segments=[{"id": 1, "start": 0.0, "end": 4.0, "text": "Enjoy your meal.",
                           "asr": "Enjoy your meal.", "translation": "享受你的饭。"}])
    p.save()
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps({"1": "祝你用餐愉快。"}, ensure_ascii=False), "utf-8")
    original = (tmp_path / "video.json").read_bytes()
    invoke(["evolve", "learn", p.path, str(edits), "--profile", "food-channel", "--memory", path])
    assert (tmp_path / "video.json").read_bytes() == original
    m = Memory(path)
    rid = m.status()["rules"][0]["id"]
    scope = {"profile": "food-channel", "source_lang": "en", "target_lang": "zh", "domains": ["cooking"]}
    cases = [{"name": "cooking signoff", "context": scope,
              "input": {"text": "Enjoy your meal.", "translation": "享受你的饭。"},
              "expected": {"text": "Enjoy your meal.", "translation": "祝你用餐愉快。"}},
             {"name": "another project", "context": {**scope, "profile": "other"},
              "input": {"text": "Enjoy your meal.", "translation": "请慢用。"},
              "expected": {"text": "Enjoy your meal.", "translation": "请慢用。"}}]
    case_file = tmp_path / "cases.json"
    case_file.write_text(json.dumps(cases, ensure_ascii=False), "utf-8")
    invoke(["evolve", "cases", rid, str(case_file), "--memory", path])
    invoke(["evolve", "activate", rid, "--reviewer", "test-editor", "--memory", path])
    invoke(["evolve", "bind", p.path, "--profile", "food-channel", "--memory", path])
    invoke(["evolve", "apply", p.path, "--memory", path])
    invoke(["deliver", p.path, "--output", str(tmp_path / "delivery"), "--memory", path])
    assert "祝你用餐愉快" in (tmp_path / "delivery" / "subtitles.srt").read_text("utf-8-sig")
    invoke(["evolve", "revoke", rid, "--reason", "changed preference", "--memory", path])
    invoke(["deliver", p.path, "--output", str(tmp_path / "stale"), "--memory", path], expected=1)
    assert not (tmp_path / "stale").exists()


def test_demo_executes_real_changes_and_gates(tmp_path):
    root = demo(str(tmp_path / "demo"))
    result = json.loads((root / "results.json").read_text("utf-8"))
    assert result["application"]["changed_segments"] == 2
    assert all(x["blocked"] for x in result["gates"])
    assert result["undo_restored"] and not result["network"]["executed"]
    assert result["after"][1] == result["before"][1]  # real estate example was not rewritten
    assert result["after_revocation"][0]["translation"] == "代理会学习。"
    assert result["after_revocation"][2]["translation"] == "感谢收看。"
    with pytest.raises(FileExistsError):
        demo(str(root))


def test_read_transaction_prevents_revision_change_during_publication(tmp_path):
    root = demo(str(tmp_path / "demo"))
    memory = Memory(root / "channel.sqlite3")
    active = next(x for x in memory.status()["rules"] if x["state"] == "active")
    entered, finished = threading.Event(), threading.Event()
    errors = []

    def revoke():
        entered.set()
        try:
            memory.revoke(active["id"], "concurrency test")
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    with open_policy(memory.path) as policy:
        p = Project.load(str(root / "05-after-revocation.json"))
        policy.check(p)
        worker = threading.Thread(target=revoke)
        worker.start()
        assert entered.wait(1)
        assert not finished.wait(0.15)
        policy.check(p)
    worker.join(3)
    assert finished.is_set() and not errors
    with open_policy(memory.path) as policy:
        with pytest.raises(ValueError, match="revision changed"):
            policy.check(p)


def test_expiry_during_long_operation_is_rechecked(tmp_path, monkeypatch):
    import subtitler.evolution.runtime as runtime
    root = demo(str(tmp_path / "demo"))
    memory = Memory(root / "channel.sqlite3")
    p = Project.load(str(root / "05-after-revocation.json"))
    snapshot = copy.deepcopy(memory.snapshot())
    for row in snapshot["rules"]:
        row["source_expires"] = 100
    policy = runtime.Policy(snapshot)
    monkeypatch.setattr(runtime.time, "time", lambda: 99)
    policy.check(p)
    monkeypatch.setattr(runtime.time, "time", lambda: 101)
    with pytest.raises(ValueError, match="expired during"):
        policy.check(p)
