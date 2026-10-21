"""CLI for evidence collection, reviewed promotion and deterministic reuse."""
import json

from .rules import validate_scope
from .runtime import open_policy, undo
from .sources import read_local
from .store import Memory


def scope_args(parser):
    parser.add_argument("--profile", required=True, help="channel/client/series identifier")
    parser.add_argument("--source-lang", required=True)
    parser.add_argument("--target-lang", required=True)
    parser.add_argument("--domain", action="append", required=True, help="explicit content domain; repeatable")


def scope(a):
    value = {"profile": a.profile, "source_lang": a.source_lang, "target_lang": a.target_lang, "domains": a.domain}
    validate_scope(value)
    return value


def run(a):
    from subtitler.cli import _load_project
    action = a.evolution_action
    if action == "demo":
        from .demo import demo
        print(demo(a.output, online=a.online))
        return 0
    if action == "init":
        result = Memory.create(a.memory).status()
    else:
        memory = Memory(a.memory)
        if action == "status":
            result = memory.status()
        elif action == "evidence":
            with memory.db() as db:
                result = dict(memory.source(db, a.source_id, fresh=False))
        elif action == "ingest":
            result = {"source_id": memory.ingest_local(a.file)}
        elif action == "import-kb":
            result = memory.import_kb(a.file, scope(a))
        elif action == "fetch":
            result = {"source_id": memory.fetch(a.url, a.allow_host, a.ttl_days)}
        elif action == "refresh":
            result = memory.refresh(a.source_id, a.allow_host, a.ttl_days)
        elif action == "capture":
            result = memory.capture(_load_project(a.before), _load_project(a.after), a.profile)
        elif action == "learn":
            import copy
            before = _load_project(a.project)
            proposed = copy.deepcopy(before)
            # A candidate draft never changes the original or bypasses its output gate.
            proposed.evolution = None
            proposed.apply(json.loads(read_local(a.file)), glossary=False)
            result = memory.capture(before, proposed, a.profile)
            result["project_unchanged"] = True
        elif action == "propose":
            proposal = json.loads(read_local(a.file))
            if not isinstance(proposal, dict) or set(proposal) != {"source_id", "rule", "quote"}:
                raise ValueError("proposal requires exactly source_id, rule and quote")
            result = {"rule_id": memory.propose(**proposal)}
        elif action == "cases":
            memory.add_cases(a.rule_id, json.loads(read_local(a.file)))
            result = {"rule_id": a.rule_id, "cases_saved": True}
        elif action == "evaluate":
            result = memory.evaluate(a.rule_id)
        elif action == "activate":
            result = memory.activate(a.rule_id, a.reviewer)
        elif action == "revoke":
            memory.revoke(a.rule_id, a.reason)
            result = {"rule_id": a.rule_id, "state": "revoked"}
        elif action in {"bind", "apply", "undo"}:
            project = _load_project(a.project)
            if action == "undo":
                # Undo remains possible when the latest rules/evidence are broken.
                with memory.db() as db:
                    store_id = db.execute("SELECT value FROM meta WHERE key='id'").fetchone()[0]
                if not project.evolution or project.evolution["store_id"] != store_id:
                    raise ValueError("wrong memory for undo")
                undo(project)
                project.save()
                result = {"restored": True, "next": "revoke bad rule, then evolve apply to validate again"}
            else:
                with open_policy(a.memory) as policy:
                    if action == "bind":
                        if a.domain:
                            project.domains = a.domain
                        policy.bind(project, a.profile)
                        result = {"bound": True, "next": "translate/review, then evolve apply"}
                    else:
                        result = policy.apply(project)
                    project.save()
        else:
            raise ValueError("unknown evolution command")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if action == "evaluate" and not result["passed"] else 0


def add_parser(sub):
    parser = sub.add_parser("evolve", help="learn from edits, local knowledge and web evidence under executable gates")
    commands = parser.add_subparsers(dest="evolution_action", required=True)

    def command(name, help_text):
        item = commands.add_parser(name, help=help_text)
        item.add_argument("--memory", required=True, help="explicit local SQLite knowledge memory")
        item.set_defaults(fn=run)
        return item

    command("init", "create a new memory; never overwrite")
    command("status", "show evidence, candidate/active/revoked rules and recent audit events")
    sp = command("evidence", "read the captured source before quoting it")
    sp.add_argument("source_id")
    sp = command("ingest", "capture a UTF-8 local text/Markdown/JSON document as evidence")
    sp.add_argument("file")
    sp = command("import-kb", "import a JSON glossary as candidates, never auto-activate")
    sp.add_argument("file")
    scope_args(sp)
    for name in ("fetch", "refresh"):
        sp = command(name, "capture/refresh public HTTPS evidence; changed sources invalidate old rules")
        sp.add_argument("url" if name == "fetch" else "source_id")
        sp.add_argument("--allow-host", action="append", required=True, help="exact approved hostname, repeatable")
        sp.add_argument("--ttl-days", type=int, default=30)
    sp = command("capture", "derive exact phrase candidates from before/after edited projects")
    sp.add_argument("before")
    sp.add_argument("after")
    sp.add_argument("--profile", required=True)
    sp = command("learn", "turn a reviewed edit JSON into candidates; preserve the original until activation")
    sp.add_argument("project")
    sp.add_argument("file")
    sp.add_argument("--profile", required=True)
    sp = command("propose", "register a closed-schema rule with a verifiable evidence quote")
    sp.add_argument("file")
    sp = command("cases", "add reviewed positive and negative cases to a candidate")
    sp.add_argument("rule_id")
    sp.add_argument("file")
    for name in ("evaluate", "activate", "revoke"):
        sp = command(name, {"evaluate": "test candidate plus every active regression case",
                            "activate": "retest and activate atomically; record the reviewer's label",
                            "revoke": "stop a rule; old project receipts become stale"}[name])
        sp.add_argument("rule_id")
        if name == "activate":
            sp.add_argument("--reviewer", required=True, help="local audit label, not authenticated identity")
        elif name == "revoke":
            sp.add_argument("--reason", required=True)
    for name in ("bind", "apply", "undo"):
        sp = command(name, {"bind": "bind a project to a memory and profile",
                            "apply": "apply active rules transactionally with undo snapshot and receipt",
                            "undo": "undo last automatic rewrite without losing later edits"}[name])
        sp.add_argument("project")
        if name == "bind":
            sp.add_argument("--profile", required=True)
            sp.add_argument("--domain", action="append")
    sp = commands.add_parser("demo", help="run a real local learning loop; no ASR/model/API required")
    sp.add_argument("--output", required=True)
    sp.add_argument("--online", action="store_true", help="also fetch an official Python glossary and execute a web-evidence learning cycle")
    sp.set_defaults(fn=run)
