"""Portable delivery bundles. No model, API key or video is needed for export."""
from __future__ import annotations

import copy
import hashlib
import html
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path, PureWindowsPath
from typing import Optional

from subtitler.project import Project
from subtitler.qa import check_segments
from subtitler.subtitle import save_subtitles
from subtitler.asr import close_gaps
from subtitler.safe_io import publish_directory


def deliver(project: Project, output: str, *, draft: bool = False,
            style: str = "bilingual", mode: str = "auto",
            approved_kb_files=(), memory=None, policy=None) -> Path:
    from subtitler.evolution.runtime import open_policy, require_policy
    if memory is not None and policy is not None:
        raise ValueError("provide memory or an open policy, not both")
    with open_policy(memory) as opened:
        policy = policy or opened
        require_policy(project, policy, final=True)
        return _deliver(project, output, draft=draft, style=style, mode=mode,
                        approved_kb_files=approved_kb_files, policy=policy)


def _deliver(project: Project, output: str, *, draft: bool, style: str, mode: str,
             approved_kb_files, policy) -> Path:
    """Check one snapshot and publish into an exclusively reserved new directory."""
    from subtitler.knowledge import KnowledgeEngine
    from subtitler.plugins.templates import get_template

    project = copy.deepcopy(project)
    project.validate()
    if mode not in {"auto", "source", "target", "bilingual"}:
        raise ValueError("不支持的导出模式。")
    approved = {os.path.abspath(p) for p in approved_kb_files}
    if any(os.path.abspath(p) not in approved for p in project.kb_files):
        raise ValueError("项目包含外部词库；请通过 --kb-file 明确指定允许读取的词库。")
    if not project.segments:
        raise ValueError("项目没有字幕，无法生成交付包。")
    destination = Path(os.path.abspath(output))
    if os.path.lexists(destination):
        raise FileExistsError(f"交付目录已存在，请换一个名称：{destination}")
    template = get_template(style)
    segments = project.to_segments() if project.evolution else close_gaps(project.to_segments())
    for record, segment in zip(project.segments, segments):
        record["end"] = segment.end
    qa_segments = copy.deepcopy(segments)
    effective_mode = mode if mode != "auto" else (
        "bilingual" if project.target_lang or any(s.translation for s in segments) else "source")
    target_lang = project.target_lang or ("und" if effective_mode in {"target", "bilingual"} else None)
    if effective_mode == "source":
        target_lang = None
        for segment in qa_segments:
            segment.translation = None
    issues = check_segments(
        qa_segments, style=template, target_lang=target_lang,
        ids=[s["id"] for s in project.segments], domains=project.domains,
        knowledge=KnowledgeEngine(extra_files=project.kb_files, warn_unknown=not bool(project.evolution)),
    )
    errors = sum(i.level == "error" for i in issues)
    if errors and not draft:
        raise ValueError(f"发现 {errors} 项字幕错误；先运行 check 修正，或用 --draft 导出待修订稿。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".delivery-", dir=destination.parent) as temp:
        staged = Path(temp) / "bundle"
        staged.mkdir()
        clean = copy.deepcopy(project)
        # Delivery must not disclose the creator's home directory or local glossary paths.
        clean.video = PureWindowsPath(clean.video.replace("\\", "/")).name
        clean.kb_files = []
        if clean.evolution:
            # Raw edit history remains private; retain binding/receipt for future edits.
            clean.evolution["history"] = []
        clean.save(str(staged / "project.json"))
        size = (project.video_info.get("width"), project.video_info.get("height"))
        for extension in ("srt", "vtt", "ass"):
            options = {"mode": effective_mode, "tidy_punct": not bool(project.evolution)}
            if extension == "ass":
                options.update(template=style, video_size=size if all(size) else None)
            else:
                options.update(max_chars=template.max_chars,
                               secondary_max_chars=template.secondary_max_chars)
            save_subtitles(segments, str(staged / f"subtitles.{extension}"), **options)
        status = "draft" if draft else "checks_passed"
        report = {"schema_version": 1, "status": status, "segments": len(project.segments),
                  "errors": errors, "warnings": sum(i.level == "warn" for i in issues),
                  "issues": [asdict(i) for i in issues],
                  "note": "检查通过仅表示规则检查通过，不代表识别、翻译或版权已经人工确认。"}
        (staged / "qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        rows = "".join(f"<tr><td>{i.index}</td><td>{html.escape(i.level)}</td>"
                       f"<td>{html.escape(i.message)}</td></tr>" for i in issues)
        (staged / "review.html").write_text(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>字幕交付检查</title><style>body{font:16px/1.7 system-ui;max-width:960px;'
            'margin:48px auto;padding:0 24px;color:#17283a}table{border-collapse:collapse;width:100%}'
            'td,th{border-bottom:1px solid #ddd;text-align:left;padding:12px}</style>'
            f'<h1>字幕交付检查</h1><p>状态：{status} · {len(project.segments)} 条字幕 · '
            f'{errors} 项错误 · {report["warnings"]} 项提醒</p><p>{report["note"]}</p>'
            '<p>交付包包含 SRT、VTT、ASS、可编辑项目和检查结果。'
            '请抽查人名、数字、专业词和音画同步；原视频与自定义词库不在包内。</p>'
            '<table><tr><th>字幕编号</th><th>级别</th><th>说明</th></tr>'
            f'{rows or "<tr><td colspan=3>规则检查未发现问题。</td></tr>"}</table></html>', "utf-8")
        manifest = {"schema_version": 1, "status": status, "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(staged.iterdir())}}
        (staged / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
        if policy is not None:
            policy.check(project)  # recheck TTL at publication, not only at the start
        publish_directory(staged, destination)
    return destination


def demo(output: str) -> Path:
    """An original synthetic example, explicitly not an ASR accuracy benchmark."""
    project = Project(path="", source_lang="en", target_lang="zh", notes="原创合成示例；非实录识别测试",
                      segments=[
                          {"id": 1, "start": 0.0, "end": 3.0, "text": "Welcome to our garden.",
                           "translation": "欢迎来到我们的花园。", "asr": "Welcome to our garden."},
                          {"id": 2, "start": 3.2, "end": 6.2, "text": "We water the plants each morning.",
                           "translation": "我们每天早晨给植物浇水。",
                           "asr": "We water the plants each morning."},
                      ])
    return deliver(project, output)
