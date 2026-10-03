"""
Accurate Knowledge-Base-Driven Bilingual Translation & Video Burning Script.
Applies domain phonetic corrections, intelligent translation, glossary alignment,
and smart line wrapping to strictly prevent screen overflow.
"""

import os
import re
import time
from deep_translator import GoogleTranslator
from subtitler.knowledge import KnowledgeEngine
from subtitler.burner import burn_subtitles_to_video
from subtitler.wrapper import wrap_bilingual_pair, split_text_smartly


def clean_text_for_translation(text: str) -> str:
    """Strip odd symbols or repeated stutter that confuse machine translation."""
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    return t


def translate_with_retry(translator, text: str, max_retries: int = 3) -> str:
    """Translates single text with retry and fallbacks."""
    clean = clean_text_for_translation(text)
    if not clean or clean in ["...", "。", "、"]:
        return clean

    for attempt in range(max_retries):
        try:
            res = translator.translate(clean)
            if res:
                return res.strip()
        except Exception as e:
            time.sleep(0.5 * (attempt + 1))

    return clean


def main():
    ke = KnowledgeEngine()
    bilingual_srt = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.srt"
    srt_source = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p.srt"
    
    processed_entries = []

    # If already translated, reuse existing translation pairs and apply enhanced wrapping
    if os.path.exists(bilingual_srt):
        print(f"[KnowledgeEngine] Found existing bilingual SRT: {bilingual_srt}. Re-wrapping with large-font parameters...")
        with open(bilingual_srt, "r", encoding="utf-8") as f:
            bilingual_content = f.read()

        pattern = r"(\d+)\r?\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\r?\n(.*?)(?=\r?\n\r?\n|\Z)"
        matches = re.findall(pattern, bilingual_content, re.DOTALL)

        for idx, time_str, block in matches:
            raw_lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
            zh_parts = []
            ja_parts = []
            for l in raw_lines:
                if any(ord(c) > 0x3040 and ord(c) < 0x30FF for c in l):
                    ja_parts.append(l)
                else:
                    zh_parts.append(l)

            zh_raw = "".join(zh_parts)
            ja_raw = "".join(ja_parts)

            # Specific domain enhancements for Kirby context
            zh_raw = zh_raw.replace("星库比", "星之卡比").replace("库比", "卡比").replace("小宝", "卡比")
            zh_raw = zh_raw.replace("第三个立方体", "第三部卡比新作").replace("修莱", "袭来")
            zh_raw = zh_raw.replace("影之诗", "暗影诗章 (Shadowverse)")
            zh_raw = zh_raw.replace("等到《时之笛》和《Metasura》", "《时之笛》、《银河战士》和《合金弹头》都等着呢")
            zh_raw = zh_raw.replace("《Metasura》", "《合金弹头》").replace("Metasura", "合金弹头")
            zh_raw = zh_raw.replace("如此匆忙", "忙得让我幸福得尖叫")

            # Smart line wrapping: wrap long lines so they NEVER overflow the screen width!
            zh_wrapped, ja_wrapped = wrap_bilingual_pair(zh_raw, ja_raw, max_zh=22, max_ja=26)

            processed_entries.append({
                "id": idx,
                "time": time_str,
                "ja": ja_wrapped,
                "zh": zh_wrapped
            })
    else:
        with open(srt_source, "r", encoding="utf-8") as f:
            content = f.read()

        pattern = r"(\d+)\r?\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\r?\n(.*?)(?=\r?\n\r?\n|\Z)"
        matches = re.findall(pattern, content, re.DOTALL)
        print(f"[KnowledgeEngine] Loaded {len(matches)} subtitle entries.")

        translator = GoogleTranslator(source="ja", target="zh-CN")
        print("[KnowledgeEngine] Processing phonetics, translating, and applying glossary...")

        for idx, time_str, ja_text in matches:
            ja_raw = ja_text.strip()
            ja_corr = ke.correct_phonetics(ja_raw, domain="gaming_nintendo")
            zh_trans = translate_with_retry(translator, ja_corr)
            zh_final = ke.apply_glossary(zh_trans, domain="gaming_nintendo")

            zh_final = zh_final.replace("星库比", "星之卡比").replace("库比", "卡比").replace("小宝", "卡比")
            zh_final = zh_final.replace("第三个立方体", "第三部卡比新作").replace("修莱", "袭来")
            zh_final = zh_final.replace("影之诗", "暗影诗章 (Shadowverse)")

            zh_wrapped, ja_wrapped = wrap_bilingual_pair(zh_final, ja_corr, max_zh=18, max_ja=24)

            processed_entries.append({
                "id": idx,
                "time": time_str,
                "ja": ja_wrapped,
                "zh": zh_wrapped
            })

    # Save Polished Bilingual SRT
    srt_out = bilingual_srt
    srt_lines = []
    for item in processed_entries:
        zh_srt = item["zh"].replace("\\N", "\n")
        ja_srt = item["ja"].replace("\\N", "\n")
        srt_lines.append(f"{item['id']}\n{item['time']}\n{zh_srt}\n{ja_srt}\n")

    with open(srt_out, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    print(f"[Success] Saved accurate bilingual SRT with smart wrapping: {srt_out}")

    # Save Styled Bilingual ASS with Large Font (54px Chinese / 36px Japanese) and elevated MarginV: 200
    ass_out = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.ass"
    header = """[Script Info]
Title: Japanese-Chinese Bilingual Subtitles (Knowledge-Base Enhanced, Screen-Safe, Large Font)
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bilingual,Microsoft YaHei,54,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1,2,80,80,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = []
    for item in processed_entries:
        times = item["time"].split(" --> ")
        start_str = times[0][:8] + "." + times[0][9:11]
        end_str = times[1][:8] + "." + times[1][9:11]
        zh = item["zh"].replace("\n", "\\N")
        ja = item["ja"].replace("\n", "\\N")
        # Large prominent Chinese (Bold 54px, Pure White), Clear Japanese (Bold 36px, Silver #F0F0F0)
        text_formatted = f"{{\\b1\\fs54\\c&H00FFFFFF&}}{zh}\\N{{\\b1\\fs36\\c&H00F0F0F0&}}{ja}"
        ass_lines.append(f"Dialogue: 0,{start_str},{end_str},Bilingual,,0,0,0,,{text_formatted}")

    with open(ass_out, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(ass_lines) + "\n")
    print(f"[Success] Saved styled large-font bilingual ASS with safe margins: {ass_out}")

    # Burn into Video with NVENC
    video_in = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p.mp4"
    video_out = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.mp4"
    print(f"[Burner] Burning screen-safe large-font bilingual subtitles into {video_out} using NVENC...")
    burn_subtitles_to_video(
        video_path=video_in,
        subtitle_path=ass_out,
        output_video_path=video_out,
        use_nvenc=True
    )
    print("\n================ Screen-Safe Subtitling Complete ================\n")


if __name__ == "__main__":
    main()
