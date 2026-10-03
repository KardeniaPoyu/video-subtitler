"""
Command line interface.

    subtitler doctor                              environment check (FFmpeg, CUDA, NVENC, fonts, LLM)
    subtitler transcribe VIDEO --to zh            ASR -> VIDEO.subtitler.json (editable project)
    subtitler status  PROJECT                     progress overview
    subtitler batch   PROJECT [--size 60]         print next untranslated lines for the agent
    subtitler apply   PROJECT edits.json          merge agent translations / source fixes
    subtitler translate PROJECT                   translate via an OpenAI-compatible LLM API
    subtitler proofread PROJECT                   proofread source via LLM API
    subtitler check   PROJECT|SUB                 QA: untranslated, rows, width, CPS, overlaps, glossary
    subtitler render  PROJECT --style bilingual   write .ass / .srt / .vtt
    subtitler preview VIDEO SUB                   burn-in preview frames + contact sheet
    subtitler frames  VIDEO [--at ...]            raw frames (cover candidates) + contact sheet
    subtitler burn    VIDEO SUB                   hardsub (NVENC auto, CPU fallback)
    subtitler chapters VIDEO chapters.txt         Bilibili timeline + lossless MP4 chapters
    subtitler kb list|show DOMAIN                 knowledge bases
    subtitler styles                              style presets
    subtitler run VIDEO [...]                     legacy one-shot pipeline (also: subtitler VIDEO)

PROJECT may be the project JSON or the video path (resolved to VIDEO.subtitler.json).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from subtitler import __version__
from subtitler.ffmpeg_utils import ensure_utf8_stdio

COMMANDS = ("doctor", "transcribe", "status", "batch", "apply", "translate", "proofread", "check",
            "render", "preview", "frames", "burn", "chapters", "kb", "styles", "run")


# ----------------------------------------------------------------------------- helpers

def _parse_time(s: str) -> float:
    s = s.strip()
    if ":" in s:
        from subtitler.subtitle import parse_timestamp
        return parse_timestamp(s)
    return float(s)


def _resolve_project(arg: str) -> str:
    from subtitler.project import PROJECT_SUFFIX, default_project_path
    if arg.endswith(".json"):
        return arg
    cand = default_project_path(arg)
    if os.path.exists(cand):
        return cand
    if os.path.exists(arg + PROJECT_SUFFIX):
        return arg + PROJECT_SUFFIX
    return cand


def _load_project(arg: str):
    from subtitler.project import Project
    path = _resolve_project(arg)
    if not os.path.exists(path):
        sys.exit(f"Project not found: {path}\nRun `subtitler transcribe VIDEO` first.")
    return Project.load(path)


def _knowledge(project=None, extra: Optional[List[str]] = None):
    from subtitler.knowledge import KnowledgeEngine
    files = list(project.kb_files if project else []) + list(extra or [])
    return KnowledgeEngine(extra_files=[f for f in files if os.path.exists(f)])


def _style_names():
    from subtitler.plugins.templates import STYLE_TEMPLATES
    return list(STYLE_TEMPLATES)


# ----------------------------------------------------------------------------- commands

def cmd_doctor(a) -> int:
    import platform
    import shutil
    import subprocess
    import tempfile
    ok = True
    print(f"video-subtitler {__version__}  |  Python {platform.python_version()}  |  {platform.platform()}")
    try:
        from subtitler.ffmpeg_utils import get_ffmpeg_path
        ff = get_ffmpeg_path()
        ver = subprocess.run([ff, "-version"], stdout=subprocess.PIPE).stdout.decode("utf-8", "ignore").splitlines()[0]
        filters = subprocess.run([ff, "-hide_banner", "-filters"], stdout=subprocess.PIPE).stdout.decode("utf-8", "ignore")
        has_ass = " ass " in filters
        print(f"[OK]   FFmpeg: {ff}\n       {ver}")
        print(f"[{'OK' if has_ass else 'FAIL'}]   libass 'ass' filter")
        ok &= has_ass
    except Exception as e:
        print(f"[FAIL] FFmpeg: {e}")
        ok = False
    try:
        import faster_whisper
        print(f"[OK]   faster-whisper {faster_whisper.__version__}")
    except Exception as e:
        print(f"[FAIL] faster-whisper not importable: {e}  ->  pip install faster-whisper")
        ok = False
    from subtitler.asr import cuda_runtime_status
    cs = cuda_runtime_status()
    print(f"[{'OK' if cs == 'ok' else 'INFO'}]   Whisper on GPU: " + ("CUDA ready" if cs == "ok"
          else f"no ({cs}); CPU will be used - prefer -m small / medium"))
    from subtitler.burner import is_nvenc_available
    nv = is_nvenc_available()
    print(f"[{'OK' if nv else 'INFO'}]   NVENC h264 encoder: {'available' if nv else 'not available (CPU libx264 will be used)'}")
    hub = os.path.expanduser("~/.cache/huggingface/hub")
    cached = sorted(d.replace("models--", "").replace("--", "/") for d in os.listdir(hub)
                    if d.startswith("models--")) if os.path.isdir(hub) else []
    print(f"[INFO] Cached Whisper models: {', '.join(cached) or 'none'}  (others download on first use)")
    fonts = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")
    if os.path.isdir(fonts):
        have = {f.lower() for f in os.listdir(fonts)}
        print(f"[{'OK' if 'msyh.ttc' in have else 'WARN'}]   Microsoft YaHei font (msyh.ttc)")
    from subtitler.plugins.llm import LLMClient
    c = LLMClient()
    print(f"[{'OK' if c.available else 'INFO'}]   LLM API: " + (f"{c.base_url} model={c.model}" if c.available
          else "not configured (agent batch workflow will be used)"))
    hf_home = os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    places = {"system drive": os.environ.get("SystemDrive", os.path.abspath(os.sep)) + os.sep,
              "working dir": os.path.abspath("."), "model cache": hf_home, "temp": tempfile.gettempdir()}
    seen = set()
    for label, path in places.items():
        drive = os.path.splitdrive(os.path.abspath(path))[0] or path
        if drive in seen:
            continue
        seen.add(drive)
        try:
            free = shutil.disk_usage(drive + os.sep).free / 1e9
        except OSError:
            continue
        lvl = "OK" if free > 3 else ("FAIL" if free < 0.5 else "WARN")
        hint = "" if free > 3 else "  <- free space (models ~0.5-3 GB, burned videos ~1 GB). Set HF_HOME / TEMP to another drive."
        print(f"[{lvl}]{' ' * (6 - len(lvl))}Free space on {drive} ({label}): {free:.1f} GB{hint}")
        ok &= free >= 0.5
    return 0 if ok else 1


def cmd_transcribe(a) -> int:
    from subtitler import transcribe_video
    from subtitler.project import Project, default_project_path
    out = a.output or default_project_path(a.video)
    if os.path.exists(out) and not a.force:
        sys.exit(f"Project already exists: {out}\nUse --force to overwrite (this discards edits/translations).")
    segments, meta = transcribe_video(a.video, model_size=a.model, language=a.lang, device=a.device,
                                      initial_prompt=a.prompt, topic=a.kb, kb_files=a.kb_file or [],
                                      keep_audio=a.keep_audio, word_split=not a.no_word_split)
    info = meta["video_info"]
    proj = Project.from_segments(out, segments, video=os.path.abspath(a.video),
                                 video_info={"width": info.width, "height": info.height,
                                             "duration": info.duration, "fps": info.fps},
                                 source_lang=meta["language"], target_lang=a.to,
                                 domains=meta["domains"], kb_files=[os.path.abspath(f) for f in (a.kb_file or [])],
                                 notes=a.notes or "", model=meta["model"])
    for seg, raw in zip(proj.segments, meta["raw"]):
        seg["asr"] = raw
    proj.save()
    print("\n" + proj.status())
    print(f"\nNext: subtitler batch \"{out}\"   (or `subtitler translate` with an LLM API key)")
    return 0


def cmd_status(a) -> int:
    print(_load_project(a.project).status())
    return 0


def cmd_batch(a) -> int:
    proj = _load_project(a.project)
    ke = _knowledge(proj)
    text, ids = proj.batch_text(start_id=a.start, size=a.size, context=a.context, knowledge=ke,
                                only_missing=not a.all)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"Wrote batch ({len(ids)} lines) to {a.out}")
    else:
        print(text)
    return 0


def cmd_apply(a) -> int:
    proj = _load_project(a.project)
    with open(a.edits, "r", encoding="utf-8-sig") as f:
        edits = json.load(f)
    report = proj.apply(edits, knowledge=_knowledge(proj), glossary=not a.no_glossary)
    proj.save()
    print(f"Applied: {report['translations']} translations, {report['source_fixes']} source fixes, "
          f"{report['timing']} timing edits, {report.get('split', 0)} lines added by splits, "
          f"{report['deleted']} deleted.")
    if report["unknown_ids"]:
        print(f"WARNING unknown ids ignored: {report['unknown_ids'][:20]}")
    print(proj.status())
    return 0


def cmd_translate(a) -> int:
    from subtitler.plugins.translator import LLMTranslatorPlugin
    proj = _load_project(a.project)
    target = a.to or proj.target_lang
    if not target:
        sys.exit("No target language: pass --to zh (or set target_lang in the project).")
    proj.target_lang = target
    ke = _knowledge(proj)
    tr = LLMTranslatorPlugin(model=a.model, batch_size=a.batch)
    if not tr.client.available:
        sys.exit("No LLM API configured (SUBTITLER_LLM_API_KEY / OPENAI_API_KEY [+ _BASE_URL, SUBTITLER_LLM_MODEL]).\n"
                 "Use the agent workflow instead: subtitler batch / subtitler apply.")
    if proj.domains:
        tr.glossary_hints = lambda text: ke.glossary_hints(text, proj.domains)
    tr.topic = proj.notes or None
    segs = tr.translate(proj.to_segments(), target, proj.source_lang, only_missing=not a.all)
    for d, s in zip(proj.segments, segs):
        if s.translation:
            d["translation"] = ke.apply_glossary(s.translation, proj.domains) if proj.domains else s.translation
    proj.save()
    print(proj.status())
    return 0


def cmd_proofread(a) -> int:
    from subtitler.plugins.corrector import LLMProofreaderPlugin
    proj = _load_project(a.project)
    ke = _knowledge(proj)
    p = LLMProofreaderPlugin(model=a.model)
    p.hotwords = ke.get_hotwords(proj.domains) if proj.domains else []
    segs = p.process(proj.to_segments())
    changed = 0
    for d, s in zip(proj.segments, segs):
        if s.text != d["text"]:
            changed += 1
            d["text"] = s.text
    proj.save()
    print(f"Proofread: {changed} lines changed.")
    return 0


def cmd_check(a) -> int:
    from subtitler.plugins.templates import get_template
    from subtitler.qa import check_segments, summarize
    style = get_template(a.style)
    if a.target.lower().endswith((".srt", ".ass", ".vtt")):
        from subtitler.subtitle import load_subtitles
        segs = load_subtitles(a.target)
        issues = check_segments(segs, style=style, max_cps=a.max_cps)
    else:
        proj = _load_project(a.target)
        ke = _knowledge(proj)
        segs = proj.to_segments()
        ids = [int(s["id"]) for s in proj.segments]
        issues = check_segments(segs, style=style, target_lang=proj.target_lang, knowledge=ke,
                                domains=proj.domains, ids=ids, max_cps=a.max_cps)
    shown = [i for i in issues if a.verbose or i.level != "info"]
    for i in shown[: a.limit]:
        print(i)
    if len(shown) > a.limit:
        print(f"... {len(shown) - a.limit} more (use --limit)")
    print(summarize(issues, len(segs)))
    return 1 if any(i.level == "error" for i in issues) else 0


def cmd_render(a) -> int:
    from subtitler.plugins.templates import get_template
    from subtitler.project import PROJECT_SUFFIX
    from subtitler.subtitle import save_subtitles
    proj = _load_project(a.project)
    segs = proj.to_segments()
    if a.output:
        base = a.output
    elif proj.video:
        base = os.path.splitext(proj.video)[0]
    else:
        base = proj.path[: -len(PROJECT_SUFFIX)] if proj.path.endswith(PROJECT_SUFFIX) else os.path.splitext(proj.path)[0]
    size = (proj.video_info.get("width"), proj.video_info.get("height"))
    for ext in [x.strip().lower() for x in a.format.split(",") if x.strip()]:
        path = base if base.lower().endswith("." + ext) else f"{base}.{ext}"
        kwargs = dict(mode=a.mode, tidy_punct=not a.keep_punct)
        if ext == "ass":
            kwargs.update(template=a.style, video_size=size if all(size) else None,
                          secondary_above=a.secondary_above)
        else:
            st = get_template(a.style)
            kwargs.update(max_chars=st.max_chars, secondary_max_chars=st.secondary_max_chars)
        save_subtitles(segs, path, **kwargs)
        print(f"Wrote {path}")
    return 0


def cmd_preview(a) -> int:
    from subtitler.burner import pick_preview_times, render_preview_frames
    from subtitler.subtitle import load_subtitles
    if a.at:
        times = [_parse_time(t) for t in a.at.split(",")]
    else:
        times = pick_preview_times(load_subtitles(a.subtitle), a.count)
    out_dir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.subtitle)), "preview")
    files = render_preview_frames(a.video, a.subtitle, times, out_dir, fonts_dir=a.fonts_dir)
    print("Preview frames (open and inspect each one):")
    for f in files:
        print("  " + f)
    return 0


def cmd_frames(a) -> int:
    from subtitler.burner import render_preview_frames
    from subtitler.ffmpeg_utils import probe_video
    if a.at:
        times = [_parse_time(t) for t in a.at.split(",")]
    else:
        dur = probe_video(a.video).duration
        times = [dur * (k + 1) / (a.count + 1) for k in range(a.count)]
    out_dir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.video)), "frames")
    for f in render_preview_frames(a.video, None, times, out_dir):
        print("  " + f)
    return 0


def cmd_burn(a) -> int:
    from subtitler.burner import burn_subtitles_to_video
    nvenc = True if a.nvenc else (False if a.cpu else None)
    burn_subtitles_to_video(a.video, a.subtitle, a.output, use_nvenc=nvenc, crf=a.crf,
                            fonts_dir=a.fonts_dir,
                            start=_parse_time(a.start) if a.start else None,
                            end=_parse_time(a.end) if a.end else None)
    return 0


def cmd_chapters(a) -> int:
    from subtitler.chapters import (embed_chapters_into_video, format_bilibili_timeline, format_timestamp,
                                    load_chapters, suggest_chapters_from_segments, validate_chapters)
    if a.suggest:
        proj = _load_project(a.suggest)
        for t, title in suggest_chapters_from_segments(proj.to_segments()):
            print(f"{format_timestamp(t)} {title[:30]}")
        print("\n(Heuristic scaffold - rewrite titles into 6-18 char topic names, save as chapters.txt)")
        return 0
    if not a.video or not a.chapters:
        sys.exit("usage: subtitler chapters VIDEO chapters.txt [--embed] [-o OUT]  |  "
                 "subtitler chapters --suggest PROJECT")
    chapters = load_chapters(a.chapters)
    for p in validate_chapters(chapters):
        print("WARN  " + p)
    print("\n" + format_bilibili_timeline(chapters, header=a.header or None) + "\n")
    if a.embed:
        out = embed_chapters_into_video(a.video, chapters, a.output)
        print(f"Embedded {len(chapters)} chapters -> {out}")
    return 0


def cmd_kb(a) -> int:
    ke = _knowledge(extra=a.kb_file)
    if a.action == "list" or not a.domain:
        for name, d in ke.domains.items():
            print(f"{name:18s} hotwords={len(d.get('hotwords', [])):3d} "
                  f"corrections={len(d.get('asr_phonetic_corrections', {})):3d} "
                  f"glossary={len(d.get('glossary', {})):3d}  {d.get('description', '')[:60]}")
        return 0
    d = ke.domains.get(a.domain)
    if not d:
        sys.exit(f"Unknown domain {a.domain}. Available: {ke.list_domains()}")
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


def cmd_styles(a) -> int:
    from subtitler.plugins.templates import STYLE_TEMPLATES
    for name, s in STYLE_TEMPLATES.items():
        sec = f"/{s.secondary_font_size}" if s.secondary_font_size else ""
        print(f"{name:18s} fs{s.font_size}{sec:4s} MarginV {s.margin_v:<4d} {s.description}")
    return 0


def cmd_run(a) -> int:
    from subtitler import process_video
    fmt = a.format
    if a.style != "default" and fmt == "srt":
        fmt = "ass"
    res = process_video(
        video_path=a.video, output_video_path=a.output_video, output_subtitle_path=a.output_subtitle,
        model_size=a.model, language=a.lang, burn=not a.no_burn, subtitle_format=fmt,
        keep_audio=a.keep_audio, device=a.device, initial_prompt=a.prompt, proofread=a.proofread,
        translate=a.translate, bilingual=not a.no_bilingual, style=a.style, topic=a.kb,
        kb_files=a.kb_file or [],
    )
    print("\n================ Processing Complete ================")
    for k in ("subtitle_path", "video_path", "project_path", "segment_count", "language", "domains", "model", "style"):
        if res.get(k):
            print(f"{k:14s}: {res[k]}")
    return 0


# ----------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="subtitler", description="AI video subtitling toolkit",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("-v", "--version", action="version", version=f"video-subtitler {__version__}")
    sub = p.add_subparsers(dest="cmd")

    def asr_opts(sp):
        sp.add_argument("-m", "--model", default="auto",
                        help="auto (GPU: large-v3-turbo, CPU: small) | tiny | base | small | medium | large-v3 | "
                             "large-v3-turbo | distil-large-v3 | path")
        sp.add_argument("-l", "--lang", default=None, help="source language code (ja/zh/en...). Auto if omitted.")
        sp.add_argument("--device", default=None, choices=["cuda", "cpu", "auto"])
        sp.add_argument("--kb", "--topic", dest="kb", default=None,
                        help="knowledge domains, comma separated (gaming_nintendo,tech_ai,anime_acg,vlogger_slang)")
        sp.add_argument("--kb-file", action="append", help="extra project-specific knowledge JSON (repeatable)")
        sp.add_argument("--prompt", default=None, help="initial prompt (style / names) for the first window")
        sp.add_argument("--keep-audio", action="store_true")

    sp = sub.add_parser("doctor", help="check FFmpeg / CUDA / NVENC / fonts / LLM config")
    sp.set_defaults(fn=cmd_doctor)

    sp = sub.add_parser("transcribe", help="ASR -> editable project JSON")
    sp.add_argument("video")
    asr_opts(sp)
    sp.add_argument("--to", default=None, help="target language for translation (e.g. zh)")
    sp.add_argument("--notes", default=None, help="speaker / topic notes shown to translators")
    sp.add_argument("-o", "--output", default=None, help="project path (default VIDEO.subtitler.json)")
    sp.add_argument("--no-word-split", action="store_true", help="keep raw Whisper segments")
    sp.add_argument("--force", action="store_true", help="overwrite an existing project")
    sp.set_defaults(fn=cmd_transcribe)

    sp = sub.add_parser("status", help="project overview")
    sp.add_argument("project")
    sp.set_defaults(fn=cmd_status)

    sp = sub.add_parser("batch", help="print a batch of lines (with context + glossary) for the agent")
    sp.add_argument("project")
    sp.add_argument("--start", type=int, default=None, help="first id (default: first untranslated)")
    sp.add_argument("--size", type=int, default=60)
    sp.add_argument("--context", type=int, default=4)
    sp.add_argument("--all", action="store_true", help="include already translated lines (review pass)")
    sp.add_argument("--out", default=None, help="write to a file instead of stdout")
    sp.set_defaults(fn=cmd_batch)

    sp = sub.add_parser("apply", help="merge a JSON of translations / fixes into the project")
    sp.add_argument("project")
    sp.add_argument("edits")
    sp.add_argument("--no-glossary", action="store_true", help="do not enforce glossary on translations")
    sp.set_defaults(fn=cmd_apply)

    sp = sub.add_parser("translate", help="translate via OpenAI-compatible LLM API")
    sp.add_argument("project")
    sp.add_argument("--to", default=None)
    sp.add_argument("--model", default=None)
    sp.add_argument("--batch", type=int, default=40)
    sp.add_argument("--all", action="store_true", help="re-translate lines that already have a translation")
    sp.set_defaults(fn=cmd_translate)

    sp = sub.add_parser("proofread", help="LLM proofreading of the source transcript")
    sp.add_argument("project")
    sp.add_argument("--model", default=None)
    sp.set_defaults(fn=cmd_proofread)

    sp = sub.add_parser("check", help="quality checks; exit code 1 if errors")
    sp.add_argument("target", help="project / video / .srt / .ass")
    sp.add_argument("--style", default="bilingual", choices=_style_names())
    sp.add_argument("--max-cps", type=float, default=11.0, help="reading speed warning (em/s); 9 = strict")
    sp.add_argument("--limit", type=int, default=80)
    sp.add_argument("--verbose", action="store_true", help="also show info-level items")
    sp.set_defaults(fn=cmd_check)

    sp = sub.add_parser("render", help="write subtitle files from the project")
    sp.add_argument("project")
    sp.add_argument("--style", default="bilingual", choices=_style_names())
    sp.add_argument("--mode", default="auto", choices=["auto", "source", "target", "bilingual"])
    sp.add_argument("--format", default="ass,srt", help="comma list of ass,srt,vtt")
    sp.add_argument("-o", "--output", default=None, help="output base path (extension added)")
    sp.add_argument("--secondary-above", action="store_true", help="small source line above the main line")
    sp.add_argument("--keep-punct", action="store_true", help="keep trailing ，。 on CJK lines")
    sp.set_defaults(fn=cmd_render)

    sp = sub.add_parser("preview", help="render subtitle preview frames + contact sheet")
    sp.add_argument("video")
    sp.add_argument("subtitle")
    sp.add_argument("--at", default=None, help="comma list of times (90, 1:30, 00:01:30.5)")
    sp.add_argument("--count", type=int, default=4)
    sp.add_argument("--out", default=None, help="output directory")
    sp.add_argument("--fonts-dir", default=None)
    sp.set_defaults(fn=cmd_preview)

    sp = sub.add_parser("frames", help="grab raw frames (cover candidates) + contact sheet")
    sp.add_argument("video")
    sp.add_argument("--at", default=None, help="comma list of times; default: evenly spaced")
    sp.add_argument("--count", type=int, default=6)
    sp.add_argument("--out", default=None)
    sp.set_defaults(fn=cmd_frames)

    sp = sub.add_parser("burn", help="burn subtitles into the video")
    sp.add_argument("video")
    sp.add_argument("subtitle")
    sp.add_argument("-o", "--output", default=None)
    sp.add_argument("--crf", type=int, default=20)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--nvenc", action="store_true")
    g.add_argument("--cpu", action="store_true")
    sp.add_argument("--start", default=None, help="test clip start (e.g. 1:30)")
    sp.add_argument("--end", default=None, help="test clip end")
    sp.add_argument("--fonts-dir", default=None)
    sp.set_defaults(fn=cmd_burn)

    sp = sub.add_parser("chapters", help="Bilibili timeline + MP4 chapter embedding")
    sp.add_argument("video", nargs="?")
    sp.add_argument("chapters", nargs="?", help="text file: one 'MM:SS title' per line")
    sp.add_argument("--embed", action="store_true", help="mux chapters into a copy of the video")
    sp.add_argument("-o", "--output", default=None)
    sp.add_argument("--header", default="", help="optional first line for the description")
    sp.add_argument("--suggest", default=None, metavar="PROJECT", help="print a pause-based chapter scaffold")
    sp.set_defaults(fn=cmd_chapters)

    sp = sub.add_parser("kb", help="list / show knowledge bases")
    sp.add_argument("action", nargs="?", default="list", choices=["list", "show"])
    sp.add_argument("domain", nargs="?")
    sp.add_argument("--kb-file", action="append")
    sp.set_defaults(fn=cmd_kb)

    sp = sub.add_parser("styles", help="list style presets")
    sp.set_defaults(fn=cmd_styles)

    sp = sub.add_parser("run", help="legacy one-shot pipeline")
    sp.add_argument("video")
    asr_opts(sp)
    sp.add_argument("-o", "--output-video", default=None)
    sp.add_argument("-s", "--output-subtitle", default=None)
    sp.add_argument("--format", default="srt", choices=["srt", "ass", "vtt"])
    sp.add_argument("--style", default="default", choices=_style_names())
    sp.add_argument("--translate", default=None)
    sp.add_argument("--no-bilingual", action="store_true")
    sp.add_argument("--proofread", action="store_true")
    sp.add_argument("--no-burn", action="store_true")
    sp.set_defaults(fn=cmd_run)
    return p


def main(argv: Optional[List[str]] = None) -> None:
    ensure_utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    # backwards compatibility: `subtitler video.mp4 [opts]` == `subtitler run video.mp4 [opts]`
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["run"] + argv
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        sys.exit(0)
    try:
        sys.exit(args.fn(args))
    except KeyboardInterrupt:
        sys.exit(130)
    except (FileNotFoundError, RuntimeError, KeyError, ValueError) as e:
        print(f"\n[Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
