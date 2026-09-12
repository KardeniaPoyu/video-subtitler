"""
Unit tests for the Knowledge Base & Glossary Engine.
"""

from subtitler.knowledge import KnowledgeEngine


def test_knowledge_engine_loading():
    ke = KnowledgeEngine()
    domains = ke.list_domains()
    assert "gaming_nintendo" in domains
    assert "tech_ai" in domains
    assert "anime_acg" in domains
    assert "vlogger_slang" in domains


def test_asr_prompt_generation():
    ke = KnowledgeEngine()
    prompt = ke.get_asr_prompt("gaming_nintendo")
    assert prompt is not None
    assert "星のカービィ" in prompt
    assert "Switch 2" in prompt


def test_phonetic_corrections():
    ke = KnowledgeEngine()
    raw = "星のカビー、感転進削！その名も、星のカビー、ワールドビヨンド！処方PVを見ました！"
    corrected = ke.correct_phonetics(raw, domain="gaming_nintendo")
    
    assert "星のカービィ" in corrected
    assert "完全新作" in corrected
    assert "初報PV" in corrected
    assert "星のカビー" not in corrected
    assert "感転進削" not in corrected


def test_glossary_application():
    ke = KnowledgeEngine()
    text = "这是关于星のカービィ和ディスカバリー的作品。"
    result = ke.apply_glossary(text, domain="gaming_nintendo")
    
    assert "星之卡比" in result
    assert "探索发现" in result
    assert "星のカービィ" not in result
