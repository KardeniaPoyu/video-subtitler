"""
Script to generate bilingual (Chinese + Japanese) subtitles and burn them into video.
"""

import os
import json
import time
from deep_translator import GoogleTranslator
from subtitler.burner import burn_subtitles_to_video
from subtitler.subtitle import format_timestamp_srt, format_timestamp_ass


def main():
    json_path = r"C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler\subtitles_ja.json"
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    print(f"Loaded {len(items)} segments. Starting batch translation to Chinese...")
    translator = GoogleTranslator(source="ja", target="zh-CN")

    batch_size = 25
    all_translated = []

    for i in range(0, len(items), batch_size):
        chunk = items[i:i + batch_size]
        texts = [c["ja"] if c["ja"].strip() else "..." for c in chunk]
        try:
            translations = translator.translate_batch(texts)
        except Exception as e:
            print(f"Batch {i} failed ({e}), falling back to single...")
            translations = []
            for t in texts:
                try:
                    translations.append(translator.translate(t))
                except Exception:
                    translations.append(t)

        for item, zh in zip(chunk, translations):
            all_translated.append({
                "id": item["id"],
                "time": item["time"],
                "ja": item["ja"],
                "zh": zh.strip()
            })
        print(f"Translated {min(i + batch_size, len(items))}/{len(items)} segments...")
        time.sleep(0.3)

    # 1. Generate Bilingual SRT
    srt_out = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.srt"
    srt_lines = []
    for item in all_translated:
        zh = item["zh"]
        ja = item["ja"]
        srt_lines.append(f"{item['id']}\n{item['time']}\n{zh}\n{ja}\n")

    with open(srt_out, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    print(f"Bilingual SRT saved to: {srt_out}")

    # 2. Generate Styled Bilingual ASS
    ass_out = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.ass"
    header = """[Script Info]
Title: Japanese-Chinese Bilingual Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bilingual,Microsoft YaHei,22,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2.5,1,2,20,20,28,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_lines = []
    for item in all_translated:
        # time format: 00:00:02,160 --> 00:00:06,910
        times = item["time"].split(" --> ")
        start_str = times[0][:8] + "." + times[0][9:11]
        end_str = times[1][:8] + "." + times[1][9:11]
        zh = item["zh"].replace("\n", " ")
        ja = item["ja"].replace("\n", " ")
        # Primary Chinese line (Bold, 22pt, White), Secondary Japanese line (Regular, 16pt, Slight silver-gray)
        text_formatted = f"{{\\b1\\fs22\\c&H00FFFFFF&}}{zh}\\N{{\\b0\\fs16\\c&H00E0E0E0&}}{ja}"
        ass_lines.append(f"Dialogue: 0,{start_str},{end_str},Bilingual,,0,0,0,,{text_formatted}")

    with open(ass_out, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(ass_lines) + "\n")
    print(f"Bilingual ASS saved to: {ass_out}")

    # 3. Burn into video using NVENC hardware acceleration
    video_in = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p.mp4"
    video_out = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.mp4"
    print(f"Burning bilingual subtitles into {video_out} using NVENC...")
    burn_subtitles_to_video(
        video_path=video_in,
        subtitle_path=ass_out,
        output_video_path=video_out,
        use_nvenc=True
    )
    print("All tasks completed successfully!")


if __name__ == "__main__":
    main()
