import json
import os
from subtitler.wrapper import wrap_bilingual_pair
from subtitler.burner import burn_subtitles_to_video
from sub_data_batch1 import BATCH_1
from sub_data_batch2 import BATCH_2
from sub_data_batch3 import BATCH_3
from sub_data_batch4 import BATCH_4
from sub_data_batch5 import BATCH_5

def main():
    # Merge all 5 batches
    all_data = {}
    all_data.update(BATCH_1)
    all_data.update(BATCH_2)
    all_data.update(BATCH_3)
    all_data.update(BATCH_4)
    all_data.update(BATCH_5)

    print(f'[PerfectSubtitles] Merged {len(all_data)} proofread dialogue lines.')

    with open('all_segments_raw.json', 'r', encoding='utf-8') as f:
        raw_segments = json.load(f)

    srt_out = r'D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.srt'
    ass_out = r'D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.ass'

    srt_lines = []
    ass_dialogues = []

    for seg in raw_segments:
        idx = seg['id']
        time_str = seg['time']
        if idx in all_data:
            ja_text, zh_text = all_data[idx]
        else:
            ja_text = seg['ja_raw']
            zh_text = seg['ja_raw']

        w_zh, _ = wrap_bilingual_pair(zh_text, ja_text, max_zh=22, max_ja=26)

        # SRT format (Chinese Only)
        zh_srt = w_zh.replace('\\N', '\n')
        srt_lines.append(f'{idx}\n{time_str}\n{zh_srt}\n')

        # ASS format (Chinese Only)
        times = time_str.split(' --> ')
        start_str = times[0][:8] + '.' + times[0][9:11]
        end_str = times[1][:8] + '.' + times[1][9:11]
        text_formatted = f'{{\\b1\\fs54\\c&H00FFFFFF&}}{w_zh}'
        ass_dialogues.append(f'Dialogue: 0,{start_str},{end_str},ChineseOnly,,0,0,0,,{text_formatted}')

    with open(srt_out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_lines))
    print(f'[PerfectSubtitles] Saved {len(srt_lines)} SRT entries to {srt_out}')

    ass_header = """[Script Info]
Title: Chinese Localized Subtitles (Master Quality Context-Proofread)
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ChineseOnly,Microsoft YaHei,54,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1,2,80,80,165,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(ass_out, 'w', encoding='utf-8') as f:
        f.write(ass_header + '\n'.join(ass_dialogues) + '\n')
    print(f'[PerfectSubtitles] Saved {len(ass_dialogues)} ASS entries to {ass_out}')

    # Burn into Video
    video_in = r'D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p.mp4'
    video_out = r'D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilibili.mp4'

    print(f'[Burner] Starting master re-burn into {video_out} using NVENC hardware acceleration...')
    burn_subtitles_to_video(
        video_path=video_in,
        subtitle_path=ass_out,
        output_video_path=video_out,
        use_nvenc=True
    )
    print('\n================ MASTER SUBTITLING RE-BURN COMPLETE ================\n')

if __name__ == '__main__':
    main()