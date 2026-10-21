"""Original multi-domain demonstration; executes the real engine, not canned metrics."""
from __future__ import annotations

import copy
import html
import json
from pathlib import Path

from subtitler.delivery import deliver
from subtitler.project import Project
from .rules import digest
from .runtime import open_policy, undo
from .store import Memory
from .preview import preview


def demo(output, online=False):
    root = Path(output).absolute()
    root.mkdir(parents=True, exist_ok=False)
    memory = Memory.create(root / "channel.sqlite3")
    context = {"profile": "learning-studio", "source_lang": "en", "target_lang": "zh", "domains": ["education"]}
    first = Project(path=str(root / "01-before.json"), source_lang="en", target_lang="zh", domains=["education"], segments=[
        {"id": 1, "start": 0.0, "end": 4.0, "text": "Thank you for joining.", "asr": "Thank you for joining.",
         "translation": "谢谢加入。"}])
    first.save()
    corrected = copy.deepcopy(first)
    corrected.segments[0]["translation"] = "感谢收看。"
    corrected.save(str(root / "02-reviewed.json"))
    learned = memory.capture(first, corrected, "learning-studio")["candidates"][0]
    edit_cases = [
        {"name": "课程片尾用语", "context": context,
         "input": {"text": "Thank you for joining.", "translation": "谢谢加入。"},
         "expected": {"text": "Thank you for joining.", "translation": "感谢收看。"}},
        {"name": "会议发言保持原译", "context": {**context, "domains": ["meeting"]},
         "input": {"text": "Thank you for joining.", "translation": "感谢参加。"},
         "expected": {"text": "Thank you for joining.", "translation": "感谢参加。"}},
    ]
    (root / "edit-cases.json").write_text(json.dumps(edit_cases, ensure_ascii=False, indent=2), "utf-8")
    memory.add_cases(learned, edit_cases)
    edit_evaluation = memory.activate(learned, "original-demo-fixture")
    glossary = {"glossary": {"agent": "智能体"}, "aliases": {"agent": ["代理"]},
                "exclude": {"agent": ["real estate agent"]}}
    (root / "glossary.json").write_text(json.dumps(glossary, ensure_ascii=False), "utf-8")
    term = memory.import_kb(root / "glossary.json", context)["candidates"][0]
    term_cases = [
        {"name": "知识课程术语", "context": context,
         "input": {"text": "An agent learns.", "translation": "代理会学习。"},
         "expected": {"text": "An agent learns.", "translation": "智能体会学习。"}},
        {"name": "房产含义不可套用", "context": context,
         "input": {"text": "A real estate agent helps.", "translation": "房产经纪人提供帮助。"},
         "expected": {"text": "A real estate agent helps.", "translation": "房产经纪人提供帮助。"}},
    ]
    (root / "term-cases.json").write_text(json.dumps(term_cases, ensure_ascii=False, indent=2), "utf-8")
    memory.add_cases(term, term_cases)
    term_evaluation = memory.activate(term, "original-demo-fixture")
    second = Project(path=str(root / "03-next-video.json"), source_lang="en", target_lang="zh", domains=["education"], segments=[
        {"id": 1, "start": 0.0, "end": 4.0, "text": "An agent learns.", "asr": "An agent learns.", "translation": "代理会学习。"},
        {"id": 2, "start": 4.5, "end": 8.5, "text": "A real estate agent helps.", "asr": "A real estate agent helps.",
         "translation": "房产经纪人提供帮助。"},
        {"id": 3, "start": 9.0, "end": 13.0, "text": "Thank you for joining.", "asr": "Thank you for joining.",
         "translation": "谢谢加入。"},
    ])
    original = copy.deepcopy(second.segments)
    with open_policy(memory.path) as policy:
        policy.bind(second, "learning-studio")
    preview_report = preview(second, memory.path, root / "change-preview")
    with open_policy(memory.path) as policy:
        applied = policy.apply(second)
        policy.check(second)
        second.save()
    deliver(second, str(root / "delivery"), memory=memory.path)
    after = copy.deepcopy(second.segments)
    gates = []

    def expect_blocked(name, action):
        try:
            action()
        except ValueError as exc:
            gates.append({"name": name, "blocked": True, "reason": str(exc)})
        else:
            raise RuntimeError(f"demo invariant failed: {name}")

    expect_blocked("省略记忆库的正式导出", lambda: deliver(second, str(root / "should-not-exist")))
    tampered = copy.deepcopy(second)
    tampered.segments[0]["translation"] = "代理会学习。"
    expect_blocked("验证后修改字幕再导出", lambda: deliver(tampered, str(root / "tampered"), memory=memory.path))
    memory.revoke(term, "demonstrate revocation and undo")
    expect_blocked("规则撤销后沿用旧验证结果", lambda: deliver(second, str(root / "stale"), memory=memory.path))
    undo(second)
    if second.segments != original:
        raise RuntimeError("demo undo did not restore the original text")
    second.save(str(root / "04-undone.json"))
    with open_policy(memory.path) as policy:
        policy.apply(second)
        second.save(str(root / "05-after-revocation.json"))
    network = {"executed": False, "note": "offline demo; pass --online to fetch real public evidence"}
    if online:
        url = "https://docs.python.org/zh-cn/3/glossary.html"
        sid = memory.fetch(url, ["docs.python.org"])
        quote = "atomic operation -- 原子化操作"
        spec = {"kind": "term", "scope": context, "trigger": "atomic operation", "replacement": "原子化操作",
                "aliases": ["原子操作"], "exclude": []}
        rid = memory.propose(sid, spec, quote)
        network_cases = [
            {"name": "程序课程", "context": context,
             "input": {"text": "An atomic operation completes.", "translation": "原子操作会完成。"},
             "expected": {"text": "An atomic operation completes.", "translation": "原子化操作会完成。"}},
            {"name": "其他客户保留原译", "context": {**context, "profile": "other-client"},
             "input": {"text": "An atomic operation completes.", "translation": "保持原样。"},
             "expected": {"text": "An atomic operation completes.", "translation": "保持原样。"}},
        ]
        memory.add_cases(rid, network_cases)
        evaluation = memory.activate(rid, "official-glossary-demo")
        web_project = Project(path=str(root / "06-network-video.json"), source_lang="en", target_lang="zh", domains=["education"],
                              segments=[{"id": 1, "start": 0.0, "end": 4.0, "text": "An atomic operation completes.",
                                         "asr": "An atomic operation completes.", "translation": "原子操作会完成。"}])
        with open_policy(memory.path) as policy:
            policy.bind(web_project, "learning-studio")
            web_changes = policy.apply(web_project)
            web_project.save()
        deliver(web_project, str(root / "network-delivery"), memory=memory.path)
        with memory.db() as db:
            evidence = dict(memory.source(db, sid))
        network = {"executed": True, "url": url, "quote": quote, "source_sha": evidence["sha"],
                   "created": evidence["created"], "expires": evidence["expires"],
                   "evaluation": evaluation, "application": web_changes,
                   "before": "原子操作会完成。", "after": web_project.segments[0]["translation"]}
    results = {"kind": "original synthetic text fixtures; not an ASR/translation-accuracy benchmark",
               "preview": {k: preview_report[k] for k in ('changed_segments', 'blocked_segments', 'pending_translations')},
               "network": network,
               "edit_evaluation": edit_evaluation, "knowledge_evaluation": term_evaluation,
               "application": applied, "before": original, "after": after, "gates": gates,
               "undo_restored": True, "after_revocation": second.segments,
               "delivery_note": "delivery was valid at creation; library revocation intentionally invalidates its old receipt",
               "before_sha": digest(original), "after_sha": digest(after)}
    (root / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    rows = "".join(f'<tr><td>{html.escape(a["text"])}</td><td>{html.escape(b["translation"])}</td>'
                   f'<td class="{"changed" if a["translation"] != b["translation"] else ""}">{html.escape(a["translation"])}</td></tr>'
                   for b, a in zip(original, after))
    gate_rows = "".join(f'<li><strong>已拦截</strong> · {html.escape(g["name"])}<small>{html.escape(g["reason"])}</small></li>' for g in gates)
    network_html = ('<h2>联网知识也进入执行闭环</h2><p>实际抓取 Python 官方中文术语表，核对术语原文后通过正反例与旧案例回归。'
                    '<strong>原子操作会完成。 → 原子化操作会完成。</strong></p>'
                    '<p><a href="https://docs.python.org/zh-cn/3/glossary.html">查看资料来源</a> · '
                    '<a href="network-delivery/subtitles.srt">查看实际生成的字幕</a></p>') if online else (
                        '<h2>联网证据</h2><p>本次为离线演示。加上 <code>--online</code> 可以抓取官方资料并执行同一套学习和交付检查。</p>')
    (root / "index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>自进化字幕 · 可复现实验</title>
<style>body{margin:0;background:#f5f5f0;color:#19382e;font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1050px;margin:52px auto;padding:0 24px 60px}h1{font-size:44px;letter-spacing:-1px;line-height:1.2}
h2{font-size:25px;margin-top:38px}.eyebrow{font-size:13px;letter-spacing:2px;color:#4b7865}.intro{font-size:20px;max-width:760px}
.stats{display:flex;gap:16px;margin:28px 0}.stat{flex:1;background:#e3eee7;padding:20px;border-radius:14px}.stat b{font-size:32px;display:block}
table{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}th,td{text-align:left;padding:18px;border-bottom:1px solid #e2e9e4}
th{background:#173e32;color:white}td.changed{font-weight:700;color:#14734b}li{margin:15px 0}small{display:block;color:#5c7068;overflow-wrap:anywhere}
.note{background:#fff8df;padding:18px;border-left:4px solid #c0a34d;margin-top:24px}a{color:#176a4e}code{font-size:14px}
@media(max-width:600px){h1{font-size:32px}.stats{display:block}.stat{margin:10px 0}th,td{padding:10px;font-size:14px}}</style>
<main><div class="eyebrow">VIDEO SUBTITLER / EVOLUTION 0.5</div><h1>这次改过的，下一次少改。</h1>
<p class="intro">从改稿与本地词库形成候选经验，通过正例、反例和回归测试后，真正修改下一段字幕。生成、测试、拦截与撤销都由程序执行。</p>'''
        f'<div class="stats"><div class="stat"><b>{applied["changed_segments"]} / {len(original)}</b>下一段实际修改的字幕</div>'
        f'<div class="stat"><b>{term_evaluation["regression_cases"]}</b>新增术语时复测的旧案例</div>'
        f'<div class="stat"><b>{len(gates)}</b>违规交付尝试被拦截</div></div>'
        '<h2>学习结果直接进入字幕</h2><p><a href="change-preview/index.html">打开改前预览：逐句查看变化与证据</a></p>'
        '<table><tr><th>原文</th><th>学习前</th><th>学习后</th></tr>' + rows + '</table>'
        '<h2>错误路径也要能证明</h2><ul>' + gate_rows + '</ul>'
        '<h2>撤销后发生什么</h2><p>本演示已撤销术语规则，并验证自动修改可以完整撤回。重新运行后，课程片尾表达仍会复用；被撤销的术语不再改写字幕。</p>'
        + network_html +
        '<div class="note">这些是原创文本样例的实际执行结果，不是语音识别准确率或真实用户效率数据。联网是否执行以上面的记录为准。'
        'delivery 文件夹是撤销前的交付快照，其旧验证结果现在会被新版记忆库拦截。</div>'
        '<p><a href="results.json">查看实际结果 JSON</a> · <a href="delivery/review.html">查看交付检查</a> · '
        '<a href="delivery/subtitles.srt">查看生成的字幕</a></p></main></html>', "utf-8")
    return root
