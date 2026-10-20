"""Portable delivery bundles. No model, API key or video is needed for export."""
from __future__ import annotations

import copy
import hashlib
import html
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from subtitler.project import Project
from subtitler.qa import check_segments
from subtitler.subtitle import save_subtitles


def deliver(project: Project, output: str, *, draft: bool = False,
            style: str = "bilingual", mode: str = "auto") -> Path:
    """Create a new directory atomically; never overwrite an existing delivery."""
    from subtitler.knowledge import KnowledgeEngine
    from subtitler.plugins.templates import get_template

    project.validate()
    if not project.segments:
        raise ValueError("项目没有字幕，无法生成交付包。")
    destination = Path(output).resolve()
    if destination.exists():
        raise FileExistsError(f"交付目录已存在，请换一个名称：{destination}")
    template = get_template(style)
    issues = check_segments(
        project.to_segments(), style=template, target_lang=project.target_lang,
        ids=[s["id"] for s in project.segments], domains=project.domains,
        knowledge=KnowledgeEngine(extra_files=project.kb_files),
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
        clean.video = Path(clean.video).name
        clean.kb_files = []
        clean.save(str(staged / "project.json"))
        size = (project.video_info.get("width"), project.video_info.get("height"))
        for extension in ("srt", "vtt", "ass"):
            options = {"mode": mode}
            if extension == "ass":
                options.update(template=style, video_size=size if all(size) else None)
            else:
                options.update(max_chars=template.max_chars,
                               secondary_max_chars=template.secondary_max_chars)
            save_subtitles(project.to_segments(), str(staged / f"subtitles.{extension}"), **options)
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
        os.rename(staged, destination)
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
