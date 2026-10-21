import copy
import json
import sqlite3

import pytest

from subtitler.cli import main
from subtitler.delivery import deliver
from subtitler.evolution.rules import canonical, transform, validate_rule
from subtitler.evolution.runtime import Policy, open_policy, undo
from subtitler.evolution.store import Memory
from subtitler.project import Project


def scope(domain="tech_ai", profile="my-channel"):
    return {"profile": profile, "source_lang": "en", "target_lang": "zh", "domains": [domain]}


def rule(**overrides):
    return {"kind": "term", "scope": scope(), "trigger": "agent", "replacement": "智能体",
            "aliases": ["代理"], "exclude": ["real estate agent"], **overrides}


def case(name, text, translation, expected, context=None):
    return {"name": name, "context": context or scope(),
            "input": {"text": text, "translation": translation},
            "expected": {"text": text, "translation": expected}}


def cases():
    return [case("AI course", "An agent learns.", "代理会学习。", "智能体会学习。"),
            case("property interview", "A real estate agent helps.", "房产经纪人提供帮助。", "房产经纪人提供帮助。"),
            case("different subject", "An agent helps.", "经纪人提供帮助。", "经纪人提供帮助。", scope("property"))]


@pytest.fixture
def memory(tmp_path):
    return Memory.create(tmp_path / "memory.sqlite3")


def propose(memory, spec=None):
    spec = spec or rule()
    quote = canonical({"term": spec["trigger"], "translation": spec["replacement"]})
    with memory.db(write=True) as db:
        source = memory.add_source(db, "local", "original-glossary.json", quote)
    return memory.propose(source, spec, quote)


def activate(memory):
    rid = propose(memory)
    memory.add_cases(rid, cases())
    memory.activate(rid, "test-reviewer")
    return rid


def project(tmp_path, text="An agent learns.", translation="代理会学习。"):
    return Project(path=str(tmp_path / "clip.json"), source_lang="en", target_lang="zh", domains=["tech_ai"],
                   segments=[{"id": 1, "start": 0.0, "end": 4.0, "text": text, "asr": text, "translation": translation}])


def test_learning_is_inactive_until_cases_and_review(memory, tmp_path):
    rid = propose(memory)
    with pytest.raises(ValueError, match="activation blocked"):
        memory.activate(rid, "reviewer")
    assert memory.snapshot()["rules"] == []
    memory.add_cases(rid, cases()[:1])
    assert not memory.evaluate(rid)["passed"]  # a self-confirming positive alone is insufficient
    memory.add_cases(rid, cases()[1:])
    report = memory.activate(rid, "reviewer")
    assert report["passed"] and report["improved_cases"] == 1
    p = project(tmp_path)
    with open_policy(memory.path) as policy:
        policy.bind(p, "my-channel")
        result = policy.apply(p)
        policy.check(p)
        p.save()
        assert result["changed_segments"] == 1
    assert Project.load(p.path).segments[0]["translation"] == "智能体会学习。"
    assert memory.status()["events"][0]["action"] == "rule_activated"


def test_scope_exclusions_word_boundaries_and_no_cascade():
    specs = [rule()]
    for c in cases():
        assert transform(specs, c["input"], c["context"]) == c["expected"]
    original = {"text": "A reagent reacts.", "translation": "试剂发生反应。"}
    assert transform(specs, original, scope()) == original
    other_channel = {"text": "An agent learns.", "translation": "代理会学习。"}
    assert transform(specs, other_channel, scope(profile="other")) == other_channel
    for key, value in (("source_lang", "de"), ("target_lang", "ja")):
        assert transform(specs, other_channel, {**scope(), key: value}) == other_channel
    once = transform(specs, other_channel, scope())
    assert transform(specs, once, scope()) == once
    with pytest.raises(ValueError, match="unresolved"):
        transform(specs, {"text": "An agent learns.", "translation": "它会学习。"}, scope())


def test_conflict_and_cross_kind_regression_block_activation(memory):
    activate(memory)
    conflict = propose(memory, rule(replacement="代理人"))
    conflicting_cases = copy.deepcopy(cases())
    conflicting_cases[0]["expected"]["translation"] = "代理人会学习。"
    memory.add_cases(conflict, conflicting_cases)
    assert not memory.evaluate(conflict)["passed"]
    different_kind = propose(memory, rule(kind="translation", trigger="An agent learns.", replacement="它会学习。", aliases=[]))
    new_cases = [case("bad semantic override", "An agent learns.", "代理会学习。", "它会学习。"),
                 case("other scope", "An agent learns.", "保持原样。", "保持原样。", scope("property"))]
    memory.add_cases(different_kind, new_cases)
    report = memory.evaluate(different_kind)
    assert not report["passed"] and report["regression_cases"] == len(cases())
    with pytest.raises(ValueError):
        memory.activate(different_kind, "reviewer")
    assert len(memory.snapshot()["rules"]) == 1


def test_positive_must_improve_and_negative_must_exercise_trigger(memory):
    rid = propose(memory)
    no_improvement = [case("already correct", "An agent learns.", "智能体会学习。", "智能体会学习。"),
                      case("unrelated", "Hello.", "你好。", "你好。", scope("property"))]
    memory.add_cases(rid, no_improvement)
    report = memory.evaluate(rid)
    assert not report["passed"] and report["improved_cases"] == report["negative_cases"] == 0


def test_capture_edits_and_reuse_exact_phrase(memory, tmp_path):
    before = project(tmp_path, text="Thank you for joining.", translation="谢谢加入。")
    after = copy.deepcopy(before)
    after.segments[0]["translation"] = "感谢收看。"
    result = memory.capture(before, after, "my-channel")
    rid = result["candidates"][0]
    memory.add_cases(rid, [case("approved signoff", "Thank you for joining.", "谢谢加入。", "感谢收看。"),
                           case("different client", "Thank you for joining.", "感谢参加。", "感谢参加。", scope(profile="other"))])
    memory.activate(rid, "editor")
    next_video = project(tmp_path, text="Thank you for joining.", translation="谢谢加入。")
    with open_policy(memory.path) as policy:
        policy.bind(next_video, "my-channel")
        policy.apply(next_video)
    assert next_video.segments[0]["translation"] == "感谢收看。"
    assert memory.capture(before, before, "my-channel")["candidates"] == []


def test_local_kb_unicode_escapes_atomic_import_and_snapshot(memory, tmp_path):
    path = tmp_path / "kb.json"
    path.write_text(json.dumps({"glossary": {"agent": "智能体"}}), "utf-8")
    result = memory.import_kb(path, scope())
    rid = result["candidates"][0]
    assert memory.snapshot()["rules"] == []
    path.write_text('{"glossary":{"agent":"changed externally"}}', "utf-8")
    assert memory.status()["rules"][0]["spec"]["replacement"] == "智能体"
    before = memory.status()
    path.write_text('{"glossary":{"agent":"valid","bad":42}}', "utf-8")
    with pytest.raises(ValueError):
        memory.import_kb(path, scope())
    assert memory.status() == before
    memory.add_cases(rid, [case("source left in translation", "An agent learns.", "agent会学习。", "智能体会学习。"), cases()[2]])
    memory.activate(rid, "reviewer")


def test_fabricated_evidence_and_executable_rules_rejected(memory):
    with memory.db(write=True) as db:
        sid = memory.add_source(db, "local", "guide.md", "agent means 智能体 in this course.")
    with pytest.raises(ValueError, match="does not exist"):
        memory.propose(sid, rule(), "agent 智能体 fabricated quote")
    for extra in ({"code": "import os"}, {"kind": "python"}, {"scope": {**scope(), "domains": []}}):
        with pytest.raises(ValueError):
            validate_rule({**rule(), **extra})


def test_bound_project_cannot_skip_memory_or_receipts(memory, tmp_path):
    activate(memory)
    p = project(tmp_path)
    with open_policy(memory.path) as policy:
        policy.bind(p, "my-channel")
        policy.apply(p)
        p.save()
    for draft in (False, True):
        with pytest.raises(ValueError, match="requires --memory"):
            deliver(p, str(tmp_path / "blocked"), draft=draft)
    with pytest.raises(ValueError, match="requires --memory"):
        p.apply({"1": "bad"}, glossary=False)
    p.segments[0]["translation"] = "tampered"
    with pytest.raises(ValueError, match="content changed"):
        deliver(p, str(tmp_path / "tampered"), memory=memory.path)
    assert not (tmp_path / "tampered").exists()
    for command in (["render", p.path, "-o", str(tmp_path / "rendered")], ["check", p.path]):
        with pytest.raises(SystemExit) as exc:
            main(command)
        assert exc.value.code == 1


def test_delivery_rechecks_policy_and_redacts_undo_history(memory, tmp_path):
    activate(memory)
    p = project(tmp_path)
    with open_policy(memory.path) as policy:
        policy.bind(p, "my-channel")
        policy.apply(p)
        p.save()
    out = deliver(p, str(tmp_path / "delivery"), memory=memory.path)
    exported = Project.load(str(out / "project.json"))
    assert exported.evolution["history"] == []
    with open_policy(memory.path) as policy:
        policy.check(exported)
    assert "智能体" in (out / "subtitles.srt").read_text("utf-8-sig")
    assert p.evolution["history"]  # original private history was preserved


def test_apply_atomic_failure_wrong_memory_and_undo_conflict(memory, tmp_path):
    rid = activate(memory)
    p = project(tmp_path)
    with open_policy(memory.path) as policy:
        policy.bind(p, "my-channel")
        before = copy.deepcopy(p)
        with pytest.raises(ValueError):
            p.apply({"1": "我不包含术语。"}, policy=policy, glossary=False)
        assert p.segments == before.segments and p.evolution == before.evolution
        policy.apply(p)
    other = Memory.create(tmp_path / "other.sqlite3")
    with pytest.raises(ValueError, match="wrong memory"):
        deliver(p, str(tmp_path / "wrong"), memory=other.path)
    p.segments[0]["end"] = 5
    with pytest.raises(ValueError, match="overwrite"):
        undo(p)
    p.segments[0]["end"] = 4.0
    memory.revoke(rid, "test rollback")
    with pytest.raises(ValueError, match="revision changed"):
        deliver(p, str(tmp_path / "stale"), memory=memory.path)
    undo(p)
    assert p.segments[0]["translation"] == "代理会学习。"
    with open_policy(memory.path) as policy:
        policy.apply(p)
        policy.check(p)


def test_active_rule_edits_and_db_tampering_fail_closed(memory):
    rid = activate(memory)
    with pytest.raises(ValueError, match="immutable"):
        memory.add_cases(rid, cases())
    with sqlite3.connect(memory.path) as db:
        db.execute("UPDATE rules SET spec=? WHERE id=?", (canonical(rule(replacement="伪造")), rid))
    with pytest.raises(ValueError, match="receipt"):
        memory.snapshot()


def test_web_expiry_and_changed_refresh_block_dependents(memory, monkeypatch, tmp_path):
    import subtitler.evolution.store as store_module
    text = "agent means 智能体 in this course."
    monkeypatch.setattr(store_module, "fetch_public", lambda *a: {"text": text, "raw_sha256": "test-fixture"})
    source = memory.fetch("https://example.org/glossary", ["example.org"])
    rid = memory.propose(source, rule(), text)
    memory.add_cases(rid, cases())
    memory.activate(rid, "reviewer")
    assert memory.refresh(source, ["example.org"])["changed"] is False
    with memory.db(write=True) as db:
        db.execute("UPDATE sources SET expires=0 WHERE id=?", (source,))
    with pytest.raises(ValueError, match="expired"):
        memory.snapshot()
    memory.refresh(source, ["example.org"])
    assert memory.snapshot()["rules"]
    monkeypatch.setattr(store_module, "fetch_public", lambda *a: {"text": "agent changed to 经纪人", "raw_sha256": "test-v2"})
    assert memory.refresh(source, ["example.org"])["changed"] is True
    with pytest.raises(ValueError, match="revoked"):
        memory.snapshot()


def test_source_correction_exact_not_regex(memory, tmp_path):
    before = project(tmp_path, "We use Pie Torch.", "我们使用 PyTorch。")
    after = copy.deepcopy(before)
    after.segments[0]["text"] = "We use PyTorch."
    rid = memory.capture(before, after, "my-channel")["candidates"][0]
    positive = case("ASR correction", "We use Pie Torch.", "我们使用 PyTorch。", "我们使用 PyTorch。")
    positive["expected"]["text"] = "We use PyTorch."
    negative = case("another domain", "We use Pie Torch.", "保持。", "保持。", scope("fiction"))
    memory.add_cases(rid, [positive, negative])
    memory.activate(rid, "editor")
    with open_policy(memory.path) as policy:
        policy.bind(before, "my-channel")
        policy.apply(before)
        policy.check(before)
    assert before.segments[0]["asr"] == "We use Pie Torch."
    assert before.segments[0]["text"] == "We use PyTorch."


def test_quotes_and_multiline_edits_preserve_verifiable_evidence(memory, tmp_path):
    before = project(tmp_path, 'He said "hello".\nWelcome.', '他说你好。')
    after = copy.deepcopy(before)
    after.segments[0]["translation"] = '他说“你好”。\n欢迎。'
    rid = memory.capture(before, after, "my-channel")["candidates"][0]
    status = memory.status()
    source_id = next(r["source_id"] for r in status["rules"] if r["id"] == rid)
    with memory.db() as db:
        text = memory.source(db, source_id)["text"]
    assert before.segments[0]["text"] in text and after.segments[0]["translation"] in text


def test_batch_cannot_drop_bound_memory(memory, tmp_path, capsys):
    activate(memory)
    p = project(tmp_path)
    with open_policy(memory.path) as policy:
        policy.bind(p, "my-channel")
        p.save()
    with pytest.raises(SystemExit) as error:
        main(["batch", p.path, "--all"])
    assert error.value.code == 1
    with pytest.raises(SystemExit) as error:
        main(["batch", p.path, "--all", "--memory", str(memory.path)])
    assert error.value.code == 0
    assert "VERIFIED CONSTRAINTS" in capsys.readouterr().out


def test_sdk_optional_fields_do_not_invalidate_saved_receipt(memory, tmp_path):
    activate(memory)
    p = project(tmp_path)
    del p.segments[0]["asr"]
    with open_policy(memory.path) as policy:
        policy.bind(p, "my-channel")
        policy.apply(p)
        p.save()
        policy.check(Project.load(p.path))
