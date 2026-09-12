"""
Unit tests for video-subtitler plugin system and style templates.
"""

import os
from subtitler.asr import SubtitleSegment
from subtitler.plugins import (
    PluginManager,
    STYLE_TEMPLATES,
    get_template,
    LLMProofreaderPlugin,
    LLMTranslatorPlugin
)
from subtitler.subtitle import save_to_ass


def test_style_templates():
    assert "default" in STYLE_TEMPLATES
    assert "bilibili_standard" in STYLE_TEMPLATES
    assert "shorts_punchy" in STYLE_TEMPLATES
    assert "cinema_minimal" in STYLE_TEMPLATES
    assert "dual_contrast" in STYLE_TEMPLATES

    shorts = get_template("shorts_punchy")
    assert shorts.font_size >= 24
    assert shorts.bold is True


def test_plugin_manager_lifecycle():
    pm = PluginManager()
    assert len(pm.post_processors) > 0
    assert len(pm.translators) > 0

    segments = [
        SubtitleSegment(start=0.0, end=1.0, text="啊啊啊测试一下。"),
        SubtitleSegment(start=1.0, end=2.0, text="这是   第二个   测试。")
    ]

    # Test local rule-based cleanup when no OPENAI_API_KEY is present
    processed = pm.apply_post_processing(segments, enable_proofread=True)
    assert len(processed) == 2
    assert "   " not in processed[1].text


def test_ass_export_with_templates(tmp_path):
    segments = [
        SubtitleSegment(start=0.0, end=2.0, text="测试字幕渲染"),
        SubtitleSegment(start=2.0, end=4.0, text="Testing Subtitle Rendering")
    ]
    out_ass = str(tmp_path / "styled.ass")
    save_to_ass(segments, out_ass, template="shorts_punchy")

    assert os.path.exists(out_ass)
    with open(out_ass, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Style: Default" in content
        assert "测试字幕渲染" in content
