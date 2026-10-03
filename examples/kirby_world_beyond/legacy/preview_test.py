import subprocess
from subtitler.ffmpeg_utils import get_ffmpeg_path

ffmpeg = get_ffmpeg_path()
video_in = r"D:\Personal\Downloads\YTDown.com_YouTube_Media_fozLKmQtznc_001_1080p.mp4"
test_ass = r"C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler\test_preview.ass"
test_mp4 = r"C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler\test_preview.mp4"
test_jpg = r"C:\Users\LENOVO\.gemini\antigravity\brain\0077f589-766e-4e9c-aa37-0074e4adfa01\test_preview.jpg"

# Chinese: 54px bold white, Japanese: 36px bold silver, MarginV: 200
ass_content = """[Script Info]
Title: Test Preview Large Legible
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
Dialogue: 0,00:00:29.59,00:00:35.11,Bilingual,,0,0,0,,{\\b1\\fs54\\c&H00FFFFFF&}从现在开始，我会等到《时之笛》和《Metasura》。\\N我很高兴这个频道如此匆忙。\\N{\\b1\\fs36\\c&H00F0F0F0&}これからは時のオカリナメトロイドにメタスラまで待ってますからね。\\Nこのチャンネルが急がしすぎて嬉しい悲鳴です。
"""

with open(test_ass, "w", encoding="utf-8") as f:
    f.write(ass_content)

escaped_ass = test_ass.replace("\\", "/").replace(":", "\\:")
cmd = [
    ffmpeg, "-y",
    "-i", video_in,
    "-ss", "00:00:32.5", "-to", "00:00:34.5",
    "-vf", f"ass='{escaped_ass}'",
    "-c:v", "h264_nvenc", "-preset", "p4",
    test_mp4
]
subprocess.run(cmd, check=True)

cmd_frame = [
    ffmpeg, "-y",
    "-i", test_mp4,
    "-ss", "00:00:00.5",
    "-frames:v", "1", "-q:v", "2",
    test_jpg
]
subprocess.run(cmd_frame, check=True)
print("Preview screenshot generated successfully!")
