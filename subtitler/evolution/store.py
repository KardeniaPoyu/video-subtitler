"""Transactional evidence -> candidate -> regression -> activation state machine."""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .rules import (applicable, canonical, conflicts, contains, digest, string, transform,
                    validate_case, validate_rule)
from .sources import MAX_BYTES, fetch_public, read_local

SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sources(id TEXT PRIMARY KEY, kind TEXT NOT NULL, locator TEXT NOT NULL,
 text TEXT NOT NULL, sha TEXT NOT NULL, created REAL NOT NULL, expires REAL,
 revoked INTEGER NOT NULL DEFAULT 0, metadata TEXT NOT NULL);
CREATE TABLE rules(id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 spec TEXT NOT NULL, quote TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('candidate','active','revoked')),
 proof TEXT, reviewer TEXT, UNIQUE(source_id, spec));
CREATE TABLE cases(id TEXT PRIMARY KEY, rule_id TEXT NOT NULL REFERENCES rules(id), spec TEXT NOT NULL,
 UNIQUE(rule_id,spec));
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
"""


class Memory:
    def __init__(self, path):
        self.path = Path(path).absolute()

    @classmethod
    def create(cls, path):
        memory = cls(path)
        memory.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(memory.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with sqlite3.connect(str(memory.path)) as db:
                db.executescript(SCHEMA)
                db.executemany("INSERT INTO meta VALUES (?,?)", [
                    ("schema", "1"), ("id", str(uuid.uuid4())), ("revision", "0")])
        except BaseException:
            memory.path.unlink()
            raise
        return memory

    @contextmanager
    def db(self, write=False):
        if not stat.S_ISREG(os.lstat(self.path).st_mode):
            raise ValueError("memory must be an existing regular SQLite file")
        connection = None
        try:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            # WAL readers do not block writer commits: they cannot protect the
            # validation-to-publication interval this store promises to hold.
            if connection.execute("PRAGMA journal_mode").fetchone()[0].lower() not in {"delete", "truncate", "persist"}:
                raise ValueError("memory requires rollback journaling; close other connections and use PRAGMA journal_mode=DELETE")
            schema = connection.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if not schema or schema[0] != "1":
                raise ValueError("unsupported evolution memory schema")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            if connection is not None:
                connection.rollback()
            raise ValueError(f"evolution memory database error: {exc}") from exc
        except BaseException:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def event(db, action, payload, bump=False):
        db.execute("INSERT INTO events(at,action,payload) VALUES (?,?,?)", (time.time(), action, canonical(payload)))
        if bump:
            db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

    @staticmethod
    def source(db, source_id, fresh=True):
        row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            raise ValueError("unknown evidence source")
        if digest(row["text"]) != row["sha"]:
            raise ValueError("evidence snapshot hash mismatch")
        if fresh and (row["revoked"] or (row["expires"] is not None and row["expires"] <= time.time())):
            raise ValueError("evidence is revoked or expired; refresh and review before reuse")
        return row

    @staticmethod
    def add_source(db, kind, locator, text, ttl_days=None, metadata=None):
        string(text, "evidence", MAX_BYTES)
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("evidence exceeds 1 MiB")
        if kind not in {"edits", "local", "web"}:
            raise ValueError("unknown evidence kind")
        if kind == "web" and (type(ttl_days) is not int or not 1 <= ttl_days <= 90):
            raise ValueError("web evidence TTL must be 1..90 days")
        now = time.time()
        source_id = "s_" + uuid.uuid4().hex[:16]
        db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,0,?)", (
            source_id, kind, locator, text, digest(text), now,
            now + ttl_days * 86400 if ttl_days is not None else None, canonical(metadata or {})))
        Memory.event(db, "evidence_added", {"source_id": source_id, "kind": kind, "sha": digest(text)})
        return source_id

    @staticmethod
    def propose_in(db, source_id, rule, quote):
        validate_rule(rule)
        source = Memory.source(db, source_id)
        string(quote, "evidence quote", 12000)
        if quote not in source["text"]:
            raise ValueError("the quoted evidence does not exist in the stored snapshot")
        if rule["trigger"] not in quote or rule["replacement"] not in quote:
            raise ValueError("quote must contain both the source phrase and proposed replacement")
        spec = canonical(rule)
        old = db.execute("SELECT id FROM rules WHERE source_id=? AND spec=?", (source_id, spec)).fetchone()
        if old:
            return old[0]
        rid = "r_" + uuid.uuid4().hex[:16]
        db.execute("INSERT INTO rules VALUES (?,?,?,?, 'candidate',NULL,NULL)", (rid, source_id, spec, quote))
        Memory.event(db, "candidate_created", {"rule_id": rid, "source_id": source_id, "spec_hash": digest(rule)})
        return rid

    def propose(self, source_id, rule, quote):
        with self.db(write=True) as db:
            return self.propose_in(db, source_id, rule, quote)

    def ingest_local(self, path):
        text = read_local(path)
        with self.db(write=True) as db:
            return self.add_source(db, "local", str(Path(path).absolute()), text)

    def fetch(self, url, allowed_hosts, ttl_days=30):
        if type(ttl_days) is not int or not 1 <= ttl_days <= 90:
            raise ValueError("web evidence TTL must be 1..90 days")
        result = fetch_public(url, allowed_hosts)
        with self.db(write=True) as db:
            return self.add_source(db, "web", url, result["text"], ttl_days,
                                   {k: v for k, v in result.items() if k != "text"})

    def refresh(self, source_id, allowed_hosts, ttl_days=30):
        if type(ttl_days) is not int or not 1 <= ttl_days <= 90:
            raise ValueError("web evidence TTL must be 1..90 days")
        with self.db() as db:
            old = dict(self.source(db, source_id, fresh=False))
        if old["kind"] != "web":
            raise ValueError("refresh is for web evidence; import local changes as a new source")
        result = fetch_public(old["locator"], allowed_hosts)
        with self.db(write=True) as db:
            current = self.source(db, source_id, fresh=False)
            if current["revoked"]:
                raise ValueError("source was revoked; fetch it as a new source and review")
            if digest(result["text"]) == old["sha"]:
                db.execute("UPDATE sources SET expires=? WHERE id=?", (time.time() + ttl_days * 86400, source_id))
                new_id = source_id
                changed = False
            else:
                db.execute("UPDATE sources SET revoked=1 WHERE id=?", (source_id,))
                new_id = self.add_source(db, "web", old["locator"], result["text"], ttl_days,
                                         {k: v for k, v in result.items() if k != "text"})
                changed = True
            self.event(db, "evidence_refreshed", {"old": source_id, "new": new_id, "changed": changed}, bump=True)
            return {"source_id": new_id, "changed": changed,
                    "next": "review new evidence; old dependent rules are blocked" if changed else "reapply memory to refresh project receipt"}

    def import_kb(self, path, scope):
        text = read_local(path)
        data = json.loads(text)
        glossary = data.get("glossary") if isinstance(data, dict) else None
        if not isinstance(glossary, dict) or not 1 <= len(glossary) <= 200:
            raise ValueError("knowledge file needs 1..200 glossary entries")
        aliases, exclude = data.get("aliases", {}), data.get("exclude", {})
        if not isinstance(aliases, dict) or not isinstance(exclude, dict):
            raise ValueError("aliases and exclude must be objects keyed by source term")
        with self.db(write=True) as db:
            sid = self.add_source(db, "local", str(Path(path).absolute()), text)
            ids = []
            for source, target in glossary.items():
                # Normalized JSON pair is a traceable extraction of the original parsed document.
                rule = {"kind": "term", "scope": scope, "trigger": source, "replacement": target,
                        "aliases": aliases.get(source, []), "exclude": exclude.get(source, [])}
                validate_rule(rule)
                # Raw JSON may use unicode escapes. Keep normalized structured extraction as evidence.
                if source not in text or target not in text or len(text) > 12000:
                    normalized = f"Source:\n{source}\nReplacement:\n{target}"
                    derived = self.add_source(db, "local", str(Path(path).absolute()), normalized,
                                              metadata={"parent_source": sid, "parent_sha": digest(text)})
                    ids.append(self.propose_in(db, derived, rule, normalized))
                else:
                    ids.append(self.propose_in(db, sid, rule, text))
            return {"source_id": sid, "candidates": ids}

    def capture(self, before, after, profile):
        before.validate()
        after.validate()
        if (before.source_lang, before.target_lang, before.domains) != (after.source_lang, after.target_lang, after.domains):
            raise ValueError("before/after must have identical languages and domains")
        if set(before.by_id()) != set(after.by_id()):
            raise ValueError("capture requires matching segment IDs; split/delete edits need separate review")
        scope = {"profile": profile, "source_lang": after.source_lang or "und",
                 "target_lang": after.target_lang or "und", "domains": after.domains}
        entries = []
        for sid, b in before.by_id().items():
            a = after.by_id()[sid]
            for field, kind in (("text", "source"), ("translation", "translation")):
                if a.get(field, "") and a.get(field, "") != b.get(field, ""):
                    trigger = b["text"] if kind == "source" else a["text"]
                    rule = {"kind": kind, "scope": scope, "trigger": trigger,
                            "replacement": a[field], "aliases": [], "exclude": []}
                    validate_rule(rule)
                    evidence = (f"Segment {sid}\nSOURCE BEFORE:\n{b['text']}\nSOURCE AFTER:\n{a['text']}"
                                f"\nTRANSLATION BEFORE:\n{b.get('translation', '')}"
                                f"\nTRANSLATION AFTER:\n{a.get('translation', '')}")
                    entries.append((rule, evidence))
        with self.db(write=True) as db:
            ids = []
            for rule, evidence in entries:
                source_id = self.add_source(db, "edits", "confirmed-edit-diff", evidence,
                                            metadata={"before_hash": digest(before.segments), "after_hash": digest(after.segments)})
                ids.append(self.propose_in(db, source_id, rule, evidence))
            return {"candidates": ids, "note": "exact phrase rules only; timing changes are not generalized"}

    @staticmethod
    def rule(db, rid):
        row = db.execute("SELECT * FROM rules WHERE id=?", (rid,)).fetchone()
        if not row:
            raise ValueError("unknown rule")
        spec = json.loads(row["spec"])
        validate_rule(spec)
        return row, spec

    @staticmethod
    def cases_for(db, rid):
        cases = [json.loads(r[0]) for r in db.execute("SELECT spec FROM cases WHERE rule_id=? ORDER BY id", (rid,))]
        for case in cases:
            validate_case(case)
        return cases

    def add_cases(self, rid, cases):
        if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
            raise ValueError("supply 1..200 review cases")
        for case in cases:
            validate_case(case)
        with self.db(write=True) as db:
            row, _ = self.rule(db, rid)
            if row["state"] == "active":
                raise ValueError("active rules and their cases are immutable; revoke before revalidation")
            for case in cases:
                db.execute("INSERT OR IGNORE INTO cases VALUES (?,?,?)", (digest([rid, case]), rid, canonical(case)))
            self.event(db, "cases_added", {"rule_id": rid, "count": len(cases)})

    @classmethod
    def active_in(cls, db):
        result = []
        for item in db.execute("SELECT id FROM rules WHERE state='active' ORDER BY id").fetchall():
            row, spec = cls.rule(db, item[0])
            source = cls.source(db, row["source_id"])
            cases = cls.cases_for(db, row["id"])
            expected = {"rule_sha": digest(spec), "source_sha": source["sha"], "cases_sha": digest(cases),
                        "quote_sha": digest(row["quote"])}
            proof = json.loads(row["proof"] or "null")
            if proof != expected or not row["reviewer"]:
                raise ValueError("active rule validation receipt is missing or changed")
            if row["quote"] not in source["text"]:
                raise ValueError("active rule evidence quote mismatch")
            result.append({"id": row["id"], "source_id": row["source_id"], "spec": spec, "cases": cases,
                           "source_expires": source["expires"],
                           "evidence": {"kind": source["kind"], "locator": source["locator"],
                                        "sha": source["sha"], "quote": row["quote"]}})
        specs = [r["spec"] for r in result]
        conflicts(specs)
        for row in result:
            for case in row["cases"]:
                if transform(specs, case["input"], case["context"]) != case["expected"]:
                    raise ValueError("active rule regression failed; revoke the conflicting rule")
        return result

    @classmethod
    def evaluate_in(cls, db, rid):
        row, candidate = cls.rule(db, rid)
        cls.source(db, row["source_id"])
        if row["state"] == "active":
            raise ValueError("rule is already active")
        active = cls.active_in(db)
        baseline = [r["spec"] for r in active]
        proposed = baseline + [candidate]
        cases = cls.cases_for(db, rid)
        failures, improved, negatives, positives = [], 0, 0, 0
        try:
            conflicts(proposed)
        except ValueError as exc:
            failures.append(str(exc))
        for case in cases:
            is_match = applicable(candidate, case["input"], case["context"])
            positives += bool(is_match)
            negatives += bool(not is_match and contains(candidate["trigger"], case["input"]["text"])
                              and case["input"] == case["expected"])
            try:
                new = transform(proposed, case["input"], case["context"])
                old = transform(baseline, case["input"], case["context"])
                improved += bool(is_match and new == case["expected"] and old != case["expected"])
                if new != case["expected"]:
                    failures.append(f"candidate case failed: {case['name']}")
            except ValueError as exc:
                failures.append(f"candidate case {case['name']}: {exc}")
        regression_count = 0
        for old in active:
            for case in old["cases"]:
                regression_count += 1
                try:
                    if transform(proposed, case["input"], case["context"]) != case["expected"]:
                        failures.append(f"regression: {case['name']}")
                except ValueError as exc:
                    failures.append(f"regression {case['name']}: {exc}")
        if not positives or not improved:
            failures.append("need a matching case with a verified improvement over current behavior")
        if not negatives:
            failures.append("need an unchanged negative case containing the trigger outside its scope or exclusion")
        return {"passed": not failures, "cases": len(cases), "improved_cases": improved,
                "negative_cases": negatives, "regression_cases": regression_count, "failures": failures}

    def evaluate(self, rid):
        with self.db() as db:
            return self.evaluate_in(db, rid)

    def activate(self, rid, reviewer):
        string(reviewer, "reviewer", 100)
        with self.db(write=True) as db:
            report = self.evaluate_in(db, rid)
            if not report["passed"]:
                raise ValueError("activation blocked: " + canonical(report))
            row, spec = self.rule(db, rid)
            proof = {"rule_sha": digest(spec), "source_sha": self.source(db, row["source_id"])["sha"],
                     "cases_sha": digest(self.cases_for(db, rid)), "quote_sha": digest(row["quote"])}
            db.execute("UPDATE rules SET state='active',proof=?,reviewer=? WHERE id=?", (canonical(proof), reviewer, rid))
            self.event(db, "rule_activated", {"rule_id": rid, "reviewer": reviewer, "tests": report, "proof": proof}, bump=True)
            return report

    def revoke(self, rid, reason):
        string(reason, "revocation reason", 1000)
        with self.db(write=True) as db:
            row, _ = self.rule(db, rid)
            if row["state"] == "revoked":
                return
            db.execute("UPDATE rules SET state='revoked' WHERE id=?", (rid,))
            self.event(db, "rule_revoked", {"rule_id": rid, "reason": reason}, bump=row["state"] == "active")

    def snapshot(self):
        with self.db() as db:
            return self.snapshot_in(db)

    @classmethod
    def snapshot_in(cls, db):
        active = cls.active_in(db)
        meta = dict(db.execute("SELECT key,value FROM meta").fetchall())
        return {"store_id": meta["id"], "revision": int(meta["revision"]), "rules": active,
                "rules_sha": digest([{k: row[k] for k in ("id", "source_id", "spec")} for row in active])}

    def status(self):
        with self.db() as db:
            return {"meta": dict(db.execute("SELECT key,value FROM meta").fetchall()),
                    "sources": [dict(r) for r in db.execute("SELECT id,kind,locator,sha,expires,revoked FROM sources")],
                    "rules": [{**dict(r), "spec": json.loads(r["spec"])} for r in db.execute(
                        "SELECT id,source_id,spec,state,reviewer FROM rules ORDER BY rowid")],
                    "events": [{**dict(r), "payload": json.loads(r["payload"])} for r in db.execute(
                        "SELECT * FROM events ORDER BY seq DESC LIMIT 30")]}
