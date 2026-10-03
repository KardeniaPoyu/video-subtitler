"""
Tests for the agent workflow pieces: knowledge replacement rules, project batch/apply,
QA checks, bilingual rendering, chapters, word resegmentation and the CLI.
"""

import json
import os
from types import SimpleNamespace

import pytest

from subtitler.asr import SubtitleSegment, normalize_timing, resegment_words
from subtitler.chapters import generate_ffmetadata, normalize_chapters, parse_chapter_text, validate_chapters
from subtitler.knowledge import KnowledgeEngine
from subtitler.knowledge.engine import build_replacer
from subtitler.project import Project
from subtitler.qa import check_segments
from subtitler.subtitle import (format_timestamp_ass, format_timestamp_srt, load_ass, save_to_ass,
                                save_to_srt, tidy_line)
from subtitler.wrapper import NO_LINE_START, display_width, wrap_lines


# ----------------------------------------------------------------------------- knowledge

def test_replacer_is_single_pass_and_protects_targets():
    rep = build_replacer({"エヴァ": "エヴァンゲリオン", "A": "B", "B": "C"})
    assert rep("エヴァンゲリオンとエヴァ") == "エヴァンゲリオンとエヴァンゲリオン"
    assert rep("A") == "B"  # not chained into C


def test_ascii_keys_respect_word_boundaries():
    rep = build_replacer({"ai": "AI", "chat gpt": "ChatGPT"})
    assert rep("rain and ai") == "rain and AI"
    assert rep("I use Chat GPT daily") == "I use ChatGPT daily"


def test_glossary_is_idempotent():
    ke = KnowledgeEngine()
    once = ke.apply_glossary("星のカービィとディスカバリー", "gaming_nintendo")
    assert ke.apply_glossary(once, "gaming_nintendo") == once


def test_domain_detection_uses_word_boundaries():
    ke = KnowledgeEngine()
    assert ke.auto_detect_domain(r"D:\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p.mp4") is None
    assert ke.auto_detect_domain("Kirby Air Riders reaction.mp4") == "gaming_nintendo"
    assert ke.auto_detect_domain("rainy day.mp4") is None


def test_glossary_hints_and_multi_domain():
    ke = KnowledgeEngine()
    hints = dict(ke.glossary_hints("メタナイトとデデデ大王", "gaming_nintendo,anime_acg"))
    assert hints["メタナイト"] == "魅塔骑士"
    assert hints["デデデ大王"] == "帝帝帝大王"


def test_project_local_kb_file_merges(tmp_path):
    kb = tmp_path / "local.kb.json"
    kb.write_text(json.dumps({"domain": "gaming_nintendo", "asr_phonetic_corrections": {"ワドルデー": "ワドルディ"}},
                             ensure_ascii=False), encoding="utf-8")
    ke = KnowledgeEngine(extra_files=[str(kb)])
    assert ke.correct_phonetics("ワドルデーとカビー", "gaming_nintendo") == "ワドルディとカービィ"


# ----------------------------------------------------------------------------- project

def _project(tmp_path):
    segs = [SubtitleSegment(0, 2, "星のカービィ、完全新作！"), SubtitleSegment(2.5, 4, "やったー"),
            SubtitleSegment(4.5, 6, "ご視聴ありがとうございました")]
    p = Project.from_segments(str(tmp_path / "v.subtitler.json"), segs, source_lang="ja",
                              target_lang="zh", domains=["gaming_nintendo"])
    p.save()
    return Project.load(p.path)


def test_project_batch_and_apply_roundtrip(tmp_path):
    ke = KnowledgeEngine()
    p = _project(tmp_path)
    text, ids = p.batch_text(size=2, knowledge=ke)
    assert ids == [1, 2]
    assert "GLOSSARY" in text and "星之卡比" in text
    report = p.apply({"1": "《星のカービィ》完全新作！", "2": {"text": "やったー！", "translation": "太棒了！"},
                      "7": "nope"}, knowledge=ke)
    assert report["translations"] == 2 and report["source_fixes"] == 1 and report["unknown_ids"] == [7]
    assert p.by_id()[1]["translation"] == "《星之卡比》完全新作！"  # glossary enforced
    p.save()
    p2 = Project.load(p.path)
    assert p2.untranslated_ids() == [3]
    text, ids = p2.batch_text(knowledge=ke)
    assert ids == [3] and "CONTEXT" in text


def test_project_apply_delete(tmp_path):
    p = _project(tmp_path)
    rep = p.apply({"delete": [3]})
    assert rep["deleted"] == 1 and len(p.segments) == 2


# ----------------------------------------------------------------------------- QA

def test_qa_flags_common_problems():
    segs = [
        SubtitleSegment(0, 2, "a", None),                                   # untranslated
        SubtitleSegment(1.5, 3, "b", "这是カービィ"),                          # overlap + kana leftover
        SubtitleSegment(3.1, 3.4, "c", "一" * 70),                           # rows / cps / short
    ]
    codes = {i.code for i in check_segments(segs, target_lang="zh")}
    assert {"untranslated", "overlap", "leftover", "rows", "cps", "short"} <= codes


def test_qa_passes_clean_lines():
    segs = [SubtitleSegment(0, 3, "Hello there.", "你好啊"), SubtitleSegment(3.5, 6, "Bye.", "再见")]
    assert not [i for i in check_segments(segs, target_lang="zh") if i.level == "error"]


# ----------------------------------------------------------------------------- rendering

def test_timestamp_rounding_never_produces_1000ms():
    assert format_timestamp_srt(0.9996) == "00:00:01,000"
    assert format_timestamp_srt(3599.9999) == "01:00:00,000"
    assert format_timestamp_ass(59.996) == "0:01:00.00"


def test_bilingual_ass_roundtrip(tmp_path):
    segs = [SubtitleSegment(0, 2, "これはテストです。", "这是测试。")]
    out = str(tmp_path / "b.ass")
    save_to_ass(segs, out, template="bilingual", video_size=(1920, 1080))
    content = open(out, encoding="utf-8").read()
    assert "Style: Secondary" in content and "{\\rSecondary}" in content
    back = load_ass(out)
    assert back[0].translation == "这是测试" and back[0].text == "これはテストです"


def test_vertical_video_canvas_not_stretched(tmp_path):
    out = str(tmp_path / "v.ass")
    save_to_ass([SubtitleSegment(0, 2, "hi")], out, template="bilingual", video_size=(1080, 1920))
    content = open(out, encoding="utf-8").read()
    assert "PlayResX: 608" in content and "PlayResY: 1080" in content


def test_srt_bilingual_order_and_braces(tmp_path):
    out = str(tmp_path / "b.srt")
    save_to_srt([SubtitleSegment(0, 2, "Hello {world}", "你好，世界。")], out)
    body = open(out, encoding="utf-8").read().split("\n")
    assert body[2] == "你好，世界" and body[3] == "Hello {world}"


def test_tidy_line():
    assert tidy_line("说实话，") == "说实话"
    assert tidy_line("太棒了！") == "太棒了！"
    assert tidy_line("Hello,") == "Hello,"


def test_wrapper_rules():
    for text in ["这是 Nintendo Switch 2 上的第三款卡比游戏，说实话比我预想的快太多了！",
                 "Kirby and the World Beyond was just announced at the Nintendo Direct, wow.",
                 "网上有人管它叫《影之诗》（Shadowverse）的简称，笑死我了。"]:
        lines = wrap_lines(text, 16)
        assert "".join(lines).replace(" ", "") == text.replace(" ", "")
        for l in lines[1:]:
            assert l[0] not in NO_LINE_START
        assert all("Nintend" not in l or "Nintendo" in l for l in lines)
    assert wrap_lines("但真没想到居然作为任天堂直面会的压轴大作登场！", 22) == ["但真没想到居然作为任天堂直面会的压轴大作登场！"]
    assert display_width("ab漢字") == 3.0


# ----------------------------------------------------------------------------- ASR helpers

def _w(word, start, end):
    return SimpleNamespace(word=word, start=start, end=end)


def test_resegment_splits_sentences_without_orphans():
    words = [_w(" Kirby", 0, .4), _w(" was", .4, .6), _w(" just", .6, .8), _w(" announced", .8, 1.3),
             _w(" at", 1.3, 1.4), _w(" the", 1.4, 1.5), _w(" Nintendo", 1.5, 1.9), _w(" Direct.", 1.9, 2.3),
             _w(" Wow,", 2.6, 2.9), _w(" so", 2.9, 3.0), _w(" fast.", 3.0, 3.4)]
    ev = resegment_words(words, max_chars=40)
    assert [e.text for e in ev] == ["Kirby was just announced at the Nintendo Direct.", "Wow, so fast."]
    ev = resegment_words(words[:8], max_chars=14)
    assert all(display_width(e.text) >= 4 for e in ev)


def test_normalize_timing_removes_overlap_and_enforces_minimum():
    segs = normalize_timing([SubtitleSegment(0, 0.2, "a"), SubtitleSegment(1.0, 3.0, "b"), SubtitleSegment(2.5, 4, "c")])
    assert segs[0].end >= 0.8 - 1e-6
    assert segs[1].end <= segs[2].start


# ----------------------------------------------------------------------------- chapters

def test_chapters_parse_and_metadata():
    ch = parse_chapter_text("00:00 开场\n[01:30] - Boss 战\n1:02:03 结尾=end;#")
    assert ch == [(0.0, "开场"), (90.0, "Boss 战"), (3723.0, "结尾=end;#")]
    norm = normalize_chapters(ch, duration=4000)
    assert norm[0][1] == 90.0 and norm[-1][1] == 4000
    meta = generate_ffmetadata(ch, duration=4000)
    assert "title=结尾\\=end\\;\\#" in meta
    assert validate_chapters([(5, "x")])  # must start at 00:00


# ----------------------------------------------------------------------------- CLI

def test_cli_styles_and_legacy_routing(capsys):
    from subtitler import cli
    with pytest.raises(SystemExit) as e:
        cli.main(["styles"])
    assert e.value.code == 0
    assert "bilingual" in capsys.readouterr().out
    args = cli.build_parser().parse_args(["run", "x.mp4", "--style", "bilingual"])
    assert args.fn is cli.cmd_run


def test_cli_apply_and_check(tmp_path, capsys):
    from subtitler import cli
    p = _project(tmp_path)
    edits = tmp_path / "e.json"
    edits.write_text(json.dumps({"1": "星之卡比完全新作！", "2": "太棒了！", "3": "感谢收看！"}, ensure_ascii=False),
                     encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cli.main(["apply", p.path, str(edits)])
    assert e.value.code == 0
    with pytest.raises(SystemExit) as e:
        cli.main(["check", p.path])
    assert e.value.code == 0, capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        cli.main(["render", p.path, "-o", str(tmp_path / "out"), "--format", "ass,srt"])
    assert os.path.exists(tmp_path / "out.ass") and os.path.exists(tmp_path / "out.srt")


def test_project_split_line_keeps_order_and_times(tmp_path):
    p = _project(tmp_path)
    rep = p.apply({"1": [{"text": "星のカービィ、", "translation": "星之卡比"},
                         {"text": "完全新作！", "translation": "完全新作！"}]})
    assert rep["split"] == 1
    first, second = p.segments[0], p.segments[1]
    assert first["id"] == 1 and second["id"] == 4
    assert first["start"] == 0 and second["end"] == 2 and first["end"] == second["start"]


def test_glossary_term_match_is_lenient():
    from subtitler.qa import term_present
    assert term_present("压轴登场", "作为压轴大作登场！")
    assert term_present("3D动作游戏", "继承了 3D 动作冒险玩法")
    assert not term_present("帝帝帝大王", "国王出现了")


def test_valorant_domain():
    ke = KnowledgeEngine()
    assert ke.auto_detect_domain("15-Beginner-Tips-I-Wish-I-Knew-Sooner-in-VALORANT_1080p.mp4") == "gaming_valorant"
    assert ke.correct_phonetics("buy a vandle and play cipher", "gaming_valorant") == "buy a Vandal and play Cypher"
    hints = dict(ke.glossary_hints("Plant the Spike, then hold with the Operator", "gaming_valorant"))
    assert hints["Spike"] == "爆能器" and hints["Operator"] == "冥驹"


def test_time_display_never_shows_60_seconds():
    from subtitler.project import _fmt_t
    assert _fmt_t(239.97) == "04:00.0"
    assert _fmt_t(3599.96) == "1:00:00.0"


def test_qa_flags_sparse_lines_as_possible_asr_gaps():
    segs = [SubtitleSegment(0, 6.3, "find a They", "找一个")]
    assert "sparse" in {i.code for i in check_segments(segs, target_lang="zh")}


def test_tiny_gaps_are_chained():
    from subtitler.asr import close_gaps
    segs = normalize_timing([SubtitleSegment(0, 1.0, "a"), SubtitleSegment(1.3, 2.5, "b"), SubtitleSegment(4.0, 5, "c")])
    assert segs[0].end == segs[1].start and segs[1].end < segs[2].start
    segs = close_gaps([SubtitleSegment(0, 1.0, "a"), SubtitleSegment(1.04, 2, "b")])
    assert segs[0].end == 1.04


def test_burn_bitrate_cap(tmp_path):
    from subtitler.burner import _encoder_args, source_bitrate_cap
    f = tmp_path / "v.bin"
    f.write_bytes(b"\0" * 1_000_000)          # 8 Mbit over 1 s = 8000 kbps
    assert source_bitrate_cap(str(f), 1.0, 1.5) == 12000
    assert source_bitrate_cap(str(f), 100.0, 1.5) == 3000  # floor
    assert source_bitrate_cap(str(f), 1.0, 0) is None
    assert "-maxrate" in _encoder_args(True, 20, "medium", 5000)
    assert "-maxrate" not in _encoder_args(False, 20, "medium", None)
