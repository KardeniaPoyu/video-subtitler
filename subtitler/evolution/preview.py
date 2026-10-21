"""Read-only, source-backed change preview for a user's own subtitle project."""
from __future__ import annotations

import html
import json
import os
import tempfile
from pathlib import Path, PureWindowsPath

from subtitler.safe_io import publish_directory
from .rules import applicable, transform
from .runtime import content_hash, open_policy


def preview(project, memory, output):
    project.validate()
    destination = Path(output).absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"preview directory already exists: {destination}")
    with open_policy(memory) as policy:
        context = policy.context(project)
        rows = []
        for segment in project.segments:
            before = {"text": segment["text"], "translation": segment.get("translation", "")}
            matched = [r for r in policy.snapshot["rules"] if applicable(r["spec"], segment, context)]
            evidence = []
            for rule in matched:
                source = dict(rule["evidence"])
                if source["kind"] != "web":
                    source["locator"] = PureWindowsPath(source["locator"]).name
                evidence.append({"rule_id": rule["id"], "source_id": rule["source_id"], **source})
            try:
                after = transform(policy.rules, before, context, allow_untranslated=True)
                error = None
            except ValueError as exc:
                after, error = None, str(exc)
            rows.append({"id": segment["id"], "before": before, "after": after, "error": error,
                         "changed": after is not None and after != before,
                         "pending_translation": after is not None and bool(project.target_lang) and not after['translation'].strip(),
                         "evidence": evidence})
        report = {"schema_version": 1, "kind": "read_only_preview", "profile": context["profile"],
                  "memory_revision": policy.snapshot["revision"], "input_sha": content_hash(project),
                  "changed_segments": sum(r['changed'] for r in rows),
                  "blocked_segments": sum(r['error'] is not None for r in rows),
                  "pending_translations": sum(r['pending_translation'] for r in rows), "segments": rows}
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.evolution-preview-', dir=destination.parent) as temp:
            staged = Path(temp)
            (staged / 'preview.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
            (staged / 'index.html').write_text(render(report), 'utf-8')
            policy.context(project)  # expiry may have changed while producing the preview
            publish_directory(staged, destination)
    return report


def render(report):
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for row in report['segments']:
        status = '需处理' if row['error'] else ('待翻译' if row['pending_translation'] else ('将修改' if row['changed'] else '保持原样'))
        source = '<p>原文：' + esc(row['before']['text']) + '</p>'
        if row['after'] and row['after']['text'] != row['before']['text']:
            source += '<p>纠正后：' + esc(row['after']['text']) + '</p>'
        after = row['after']['translation'] if row['after'] else '本句未生成可用改稿'
        why = ''.join('<details><summary>依据：' + esc(e['kind']) + ' · ' + esc(e['locator']) + '</summary>'
                      '<p>规则 ' + esc(e['rule_id']) + ' / 来源 ' + esc(e['source_id']) + '</p>'
                      '<pre>' + esc(e['quote']) + '</pre><small>快照 SHA：' + esc(e['sha']) + '</small></details>'
                      for e in row['evidence']) or '<small>没有命中已启用的规则。</small>'
        cards.append('<article><h2>#' + esc(row['id']) + ' · ' + status + '</h2>' + source +
                     '<div class="compare"><div><b>当前译文</b><p>' + esc(row['before']['translation'] or '尚未翻译') +
                     '</p></div><div><b>应用后</b><p>' + esc(after or '尚未翻译') + '</p></div></div>' +
                     ('<p class="error">' + esc(row['error']) + '</p>' if row['error'] else '') + why + '</article>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>字幕改前预览</title>
<style>body{background:#f6f7f3;color:#19392f;font:16px/1.7 system-ui;margin:0}main{max-width:1000px;margin:42px auto;padding:0 24px 50px}
h1{font-size:38px}article{background:white;padding:24px;margin:20px 0;border:1px solid #dce7df;border-radius:12px}h2{margin-top:0;font-size:22px}
.compare{display:grid;grid-template-columns:1fr 1fr;gap:16px}.compare>div{padding:16px;background:#eef4ef;border-radius:8px}
p,pre,small{overflow-wrap:anywhere;white-space:pre-wrap}pre{font-size:14px}.error{color:#a13020}summary{cursor:pointer}a{color:#1b7453}
@media(max-width:600px){.compare{grid-template-columns:1fr}article{padding:16px}h1{font-size:28px}}</style><main><h1>先看改动，再决定应用。</h1>''' + (
        '<p>频道：' + esc(report['profile']) + ' · 规则版本：' + esc(report['memory_revision']) + '</p>'
        '<p><strong>' + esc(report['changed_segments']) + ' 句将修改 · ' + esc(report['blocked_segments']) +
        ' 句需处理 · ' + esc(report['pending_translations']) + ' 句待翻译</strong></p>'
        '<p>这次预览没有改动项目。确认后运行 <code>evolve apply</code>，程序会重新读取并校验规则；正式交付另需通过检查。</p>'
        + ''.join(cards) + '<p>此报告包含你的字幕和证据引文，留在本地供审阅。<a href="preview.json">查看详细结果</a></p></main></html>')
