"""
Unit tests for subtitle line wrapping and length protection.
"""

from subtitler.wrapper import split_text_smartly, wrap_bilingual_pair


def test_split_text_smartly_short():
    short = "这是简短的字幕。"
    assert split_text_smartly(short, max_chars=20) == short


def test_split_text_smartly_punctuation():
    long_zh = "从现在开始，我会等到《时之笛》和《Metasura》。我很高兴这个频道如此匆忙。"
    wrapped = split_text_smartly(long_zh, max_chars=20, lang="zh")
    assert "\\N" in wrapped
    parts = wrapped.split("\\N")
    assert len(parts) == 2
    assert parts[0].endswith("。") or parts[0].endswith("，")
    assert len(parts[0]) <= 28
    assert len(parts[1]) <= 28


def test_wrap_bilingual_pair():
    zh = "从现在开始，我会等到《时之笛》和《Metasura》。我很高兴这个频道如此匆忙。"
    ja = "これからは時のオカリナメトロイドにメタスラまで待ってますからね。このチャンネルが急がしすぎて嬉しい悲鳴です。"
    w_zh, w_ja = wrap_bilingual_pair(zh, ja, max_zh=22, max_ja=26)
    assert "\\N" in w_zh
    assert "\\N" in w_ja
