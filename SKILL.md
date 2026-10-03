---
name: video-subtitler
description: >-
  End-to-end video subtitling and localization toolkit (faster-whisper + FFmpeg/libass). Transcribes
  speech from video/audio, fixes domain terms (games/Nintendo, VALORANT/FPS, anime/ACG, AI/tech, vlogger slang),
  translates line-by-line with context (the agent itself or an OpenAI-compatible LLM), renders styled
  bilingual ASS/SRT/VTT, runs automatic subtitle QA, renders preview frames, burns hard subtitles
  (NVENC/CPU), and creates Bilibili timeline + MP4 chapters. Use whenever the user wants to transcribe,
  subtitle, translate subtitles for, 加字幕/压字幕/双语字幕/翻译视频/搬运, burn, preview, add chapters to,
  or prepare a video for Bilibili/YouTube publishing.
---

# Video-Subtitler

Toolkit location: `C:\Users\LENOVO\.gemini\antigravity\scratch\video-subtitler`
Run every command from that folder as `python -m subtitler <command>` (the `subtitler` console script
also works if the package is pip-installed). `PROJECT` arguments accept the video path directly.

## 0. Before you start

```
python -m subtitler doctor
```
Read the output and act on it:
- **Free space WARN/FAIL on C:** – models download to `~/.cache/huggingface` and temp audio goes to `%TEMP%`.
  Set `HF_HOME` / `TEMP` to a roomy drive for the session, or ask the user to free space.
- **Whisper on GPU: no (cublas64_12.dll …)** – ASR runs on CPU. Use `-m small` (fast) or `-m medium` (better);
  `auto` already picks `small` after falling back. Offer the user
  `pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` to enable GPU ASR (`large-v3-turbo`).
- NVENC only affects burning speed; CPU x264 fallback is automatic.
- LLM API not configured → you (the agent) translate via `batch`/`apply` (this is the default, best-quality path).

Ask the user only what you cannot infer: target language (default: 简体中文), bilingual vs. target-only
(default: bilingual for 搬运/翻译), and whether to burn or only deliver subtitle files.

## 1. Workflow (each step = one command)

| # | Step | Command |
|---|------|---------|
| 1 | Inspect | `python -m subtitler doctor` and look at the video (resolution, language, bottom-area captions) |
| 2 | Transcribe | `python -m subtitler transcribe VIDEO -l ja --kb gaming_nintendo --to zh --notes "..."` |
| 3 | Translate / proofread | loop: `batch` → write JSON → `apply` (or `translate` if an LLM API is configured) |
| 4 | QA | `python -m subtitler check VIDEO` until it prints **PASS** |
| 5 | Render | `python -m subtitler render VIDEO --style bilingual` (→ `VIDEO.ass` + `VIDEO.srt`) |
| 6 | Visual check | `python -m subtitler preview VIDEO VIDEO.ass` then open `preview/contact_sheet.jpg` |
| 7 | Burn | `python -m subtitler burn VIDEO VIDEO.ass` (→ `VIDEO_subtitled.mp4`) |
| 8 | Chapters | write `chapters.txt`, `python -m subtitler chapters VIDEO_subtitled.mp4 chapters.txt --embed` |
| 9 | Deliver | output paths, contact sheet, chapter timeline text, anything you could not verify |

Quick one-shot (no review, for drafts only): `python -m subtitler VIDEO --style bilingual --translate zh`.

### Step 2 – Transcribe
- Always pass `-l` when you know the language (auto-detect can misfire on music intros).
- `--kb` accepts several domains: `gaming_nintendo,anime_acg` (also `gaming_valorant`, `tech_ai`, `vlogger_slang`). `python -m subtitler kb list` shows them.
  If omitted, the domain is guessed from the file name and then from the transcript.
- `--notes` = speaker persona, topic, tone; it is shown in every batch so translations stay consistent.
- Video-specific mishearings/names go into a project KB file (`--kb-file my_video.kb.json`, same JSON
  schema as `subtitler/knowledge/data/*.json`), **not** into the shared domain files.
- The project file `VIDEO.subtitler.json` keeps `asr` (raw), `text` (corrected source) and `translation`
  per line. Re-running `transcribe` needs `--force` and discards edits.

### Step 3 – Translate as the agent (batch / apply loop)
```
python -m subtitler batch VIDEO --size 60          # prints next untranslated lines + context + GLOSSARY
# write batch_001.json with your file-writing tool (UTF-8), then:
python -m subtitler apply VIDEO batch_001.json     # repeat until "Translated: N/N (complete)"
```
JSON shapes accepted by `apply`:
```json
{"12": "译文",
 "13": {"text": "修正后的原文", "translation": "译文"},
 "14": {"start": 61.2, "end": 63.0},
 "15": [{"text": "前半の原文", "translation": "前半译文"},
        {"text": "後半の原文", "translation": "后半译文"}],
 "delete": [57]}
```
A list value splits one line into several (times optional → divided by text length; the first piece
keeps the id, extra pieces get new ids at the end of the numbering but stay in time order).
Translation rules (these are what made past results good):
1. Read the CONTEXT lines and `--notes` first; translate meaning and tone, never word-for-word.
2. Use every GLOSSARY entry exactly; official localized names for games/anime/products, titles in 《》.
3. Fix ASR errors while translating: put the corrected source in `"text"` (the Japanese/English line
   shown under the translation must be right too). If a line is a Whisper hallucination
   (e.g. a stray "ご視聴ありがとうございました" over music), add it to `"delete"`.
4. Keep one output per id – never merge or shift content between ids; if a line is too long to read,
   shorten the wording (aim ≤ 22 汉字 per row, ≤ 2 rows).
5. Write the JSON with a file tool, not `echo` in PowerShell (console GBK encoding corrupts CJK).
6. Optional second pass: `batch --all --start 1` to review everything with full context.

### Step 4 – QA (`check`)
Fix every **ERROR** (exit code 1): `untranslated`, `rows` (>2 rows → shorten, or split the line with a
list value), `width`, `overlap`, `cps` (≥ 15.4 em/s → shorten text or extend `end`), `timing`.
Review WARNs: `cps` (> 11 em/s; `--max-cps 9` for strict), `leftover` (kana left in Chinese),
`glossary` (term not used), `short`/`long`, `same`, `sparse` (few words over a long span = Whisper
probably dropped speech: re-transcribe that clip, then fix with `text` + `start`/`end`). Fixes go through `apply`.

### Step 5 – Style & layout
`python -m subtitler styles` lists presets. Choose by looking at the source video's bottom area:
- `bilingual` (default, 贴边沉浸式): translation 52 bold/3.5px border, source 34 #EAEAEA/2.5px, MarginV 48.
- `bilingual_avoid` (避让式): MarginV 190 – use when the original has burned-in captions, telops,
  chat boxes or HUD at the bottom that must stay visible.
- `single_large`: translation only (`--mode target`), 54 bold.
- `shorts_punchy`, `cinema_minimal`, `bilibili_standard`, `default`, `dual_contrast` for other looks.
Rendering handles the rest automatically: canvas matches the video aspect ratio (vertical video gets
smaller fonts and a bottom margin above Shorts/Douyin UI), smart line breaking (no split words,
CJK 禁则, no split 《titles》), and trailing ，。 removal on CJK lines (`--keep-punct` to keep).
`--secondary-above` puts the small source line above the main line.

### Step 6 – Visual check (mandatory before burning a full video)
`preview` picks evenly spaced moments plus the widest line (or use `--at 0:31,2:05,5:40`) and writes
full-resolution frames + `contact_sheet.jpg`. Open the images and verify: margin comfortable, nothing
clipped, both rows readable on bright and dark scenes, nothing important covered, names correct.
For a quick encoded test: `burn VIDEO VIDEO.ass --start 1:30 --end 1:45 -o test.mp4`.

### Step 7 – Burn
NVENC (constant quality `-cq 20 -b:v 0`) is auto-detected with CPU x264 fallback; audio is copied
(AAC re-encode fallback). Peak bitrate is capped at 1.6x the source (`--bitrate-cap`, 0 = off) so
re-encoded web videos do not balloon 4x in size. `--crf 18` for higher quality, `--fonts-dir` for custom fonts. Progress
and ETA are printed. Output defaults to `VIDEO_subtitled.mp4`.

### Step 8 – Chapters (videos ≳ 5 min)
1. `python -m subtitler chapters --suggest VIDEO` prints a pause-based scaffold; read the transcript and
   write real topic titles (6–18 chars, first line must be `00:00`, ≥ 10 s apart) to `chapters.txt`:
   `00:00 开场：新作公布` / `02:15 世界观与机制` …
2. `python -m subtitler chapters VIDEO_subtitled.mp4 chapters.txt --embed` validates, prints the
   Bilibili/YouTube description timeline (Bilibili turns `MM:SS 标题` lines into progress-bar chapters)
   and losslessly muxes chapters into `VIDEO_subtitled_chapters.mp4` (PotPlayer/VLC/mpv/IINA).

## 2. Bilibili publishing checklist (manual / API, only when asked)
- **Cover**: `python -m subtitler frames VIDEO --count 8` (or `--at 1:02,4:40,...`) grabs candidates from
  the RAW video (no subtitles) + a contact sheet; pick a title/logo card, climax or wide scenic shot.
  Never a random frame or the first seconds. 16:9.
- **Metadata**: title, tags, description = credits + chapter timeline. Send as UTF-8 JSON (PowerShell's
  default GBK corrupts Chinese); verify on the web edit page afterwards.
- **Repost attribution**: copyright = 转载 (2), source = original channel name + original URL;
  pick the right partition (e.g. 单机游戏).
- Pinned comment with the same timeline helps mobile viewers.
- Cookies/credentials are the user's: only use files they point you to; never print them.

## 3. Reference
- Package map: `asr.py` (Whisper, hotwords, word-level re-segmentation, timing), `knowledge/` (domains,
  single-pass corrections, glossary), `project.py` (project file, batch/apply), `plugins/` (LLM client,
  translator, proofreader, style presets), `subtitle.py` (writers/readers), `wrapper.py` (line breaking),
  `qa.py` (checks), `burner.py` (burn, preview), `chapters.py`, `cli.py`.
- Python API: `from subtitler import process_video, transcribe_video`;
  `from subtitler.project import Project`; `from subtitler.subtitle import save_to_ass`.
- LLM env (optional): `SUBTITLER_LLM_API_KEY`/`OPENAI_API_KEY`, `SUBTITLER_LLM_BASE_URL`,
  `SUBTITLER_LLM_MODEL` (any OpenAI-compatible endpoint, incl. DeepSeek/Gemini/Ollama).
- `examples/valorant_beginner_tips/`: a finished en→zh job (203 lines, `bilingual_avoid` over a game HUD,
  18 chapters) – reference for FPS terminology and how ASR gaps / fixes were applied.
- `examples/kirby_world_beyond/`: a finished ja→zh job (project KB file + 345 reviewed translations
  in `apply` format) – a good reference for translation tone and density.
- Tests: `python -m pytest -q`.
