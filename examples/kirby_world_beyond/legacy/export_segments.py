
import re

srt_path = r'D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p_bilingual.srt'
with open(srt_path, 'r', encoding='utf-8') as f:
    text = f.read()

pattern = r'(\d+)\r?\n(\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})\r?\n(.*?)(?=\r?\n\r?\n|\Z)'
entries = re.findall(pattern, text, re.DOTALL)

with open('all_bilingual_segments.txt', 'w', encoding='utf-8') as f_out:
    for idx, time_str, content in entries:
        lines = [l.strip() for l in content.strip().split('\n') if l.strip()]
        zh = []
        ja = []
        for l in lines:
            if any(ord(c) > 0x3040 and ord(c) < 0x30FF for c in l):
                ja.append(l)
            else:
                zh.append(l)
        ja_str = ' '.join(ja)
        zh_str = ' '.join(zh)
        f_out.write(f'[{idx}] {time_str}\nJA: {ja_str}\nZH: {zh_str}\n\n')

print(f'Exported {len(entries)} segments to all_bilingual_segments.txt')
