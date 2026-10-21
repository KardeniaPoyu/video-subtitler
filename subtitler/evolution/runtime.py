"""Mandatory execution and publication gates for memory-bound subtitle projects."""
from __future__ import annotations

import copy
import time
from contextlib import contextmanager

from .rules import applicable, digest, string, transform, validate_scope, violations
from .store import Memory


def content_hash(project):
    segments = [{**s, "asr": s.get("asr", s.get("text", "")), "translation": s.get("translation", "")}
                for s in project.segments]
    return digest({"source_lang": project.source_lang, "target_lang": project.target_lang,
                   "domains": project.domains, "segments": segments})


def validate_binding(binding):
    if binding is None:
        return
    if not isinstance(binding, dict) or set(binding) != {"store_id", "profile", "revision", "rules_sha", "receipt", "history"}:
        raise ValueError("invalid evolution binding")
    for key in ("store_id", "profile"):
        string(binding[key], key, 100)
    if type(binding["revision"]) is not int or binding["revision"] < 0:
        raise ValueError("invalid evolution revision")
    if not isinstance(binding["rules_sha"], str) or not isinstance(binding["receipt"], dict):
        raise ValueError("invalid evolution receipt")
    if not isinstance(binding["history"], list) or len(binding["history"]) > 20:
        raise ValueError("invalid evolution history")


class Policy:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.rules = [row["spec"] for row in snapshot["rules"]]

    def context(self, project):
        if any(row["source_expires"] is not None and row["source_expires"] <= time.time()
               for row in self.snapshot["rules"]):
            raise ValueError("evidence expired during processing; refresh before continuing")
        if project.evolution is None:
            raise ValueError("bind the project with evolve bind before using memory")
        validate_binding(project.evolution)
        if project.evolution["store_id"] != self.snapshot["store_id"]:
            raise ValueError("wrong memory database for this project")
        context = {"profile": project.evolution["profile"], "source_lang": project.source_lang or "und",
                   "target_lang": project.target_lang or "und", "domains": project.domains}
        validate_scope(context)
        return context

    def bind(self, project, profile):
        string(profile, "profile", 100)
        if project.evolution is not None:
            self.context(project)
            if project.evolution["profile"] != profile:
                raise ValueError("cannot silently switch an already bound profile")
            return
        project.evolution = {"store_id": self.snapshot["store_id"], "profile": profile,
                             "revision": self.snapshot["revision"], "rules_sha": self.snapshot["rules_sha"],
                             "receipt": {}, "history": []}
        self.context(project)

    def apply(self, project):
        context = self.context(project)
        before = copy.deepcopy(project.segments)
        for segment in before:
            segment.setdefault("asr", segment["text"])
            segment.setdefault("translation", "")
        after, changes = [], []
        for segment in before:
            updated = transform(self.rules, segment, context)
            after.append(updated)
            if updated != segment:
                changes.append({"segment_id": segment["id"], "rule_ids": [
                    row["id"] for row in self.snapshot["rules"] if applicable(row["spec"], segment, context)]})
        candidate = copy.deepcopy(project)
        candidate.segments = after
        candidate.validate()
        final_hash = content_hash(candidate)
        binding = copy.deepcopy(project.evolution)
        if changes:
            if len(binding["history"]) >= 20:
                raise ValueError("20 undo snapshots reached; archive this project and start a new one")
            binding["history"].append({"before_segments": before, "after_hash": final_hash,
                                        "revision": self.snapshot["revision"]})
        binding.update(revision=self.snapshot["revision"], rules_sha=self.snapshot["rules_sha"],
                       receipt={"content_sha": final_hash, "changes": changes})
        project.segments, project.evolution = after, binding
        return {"changed_segments": len(changes), "changes": changes, "revision": binding["revision"]}

    def check(self, project):
        context = self.context(project)
        binding = project.evolution
        if binding["revision"] != self.snapshot["revision"] or binding["rules_sha"] != self.snapshot["rules_sha"]:
            raise ValueError("memory revision changed; run evolve apply before final output")
        if binding["receipt"].get("content_sha") != content_hash(project):
            raise ValueError("subtitle content changed after validation; run evolve apply")
        for segment in project.segments:
            failed = violations(self.rules, segment, context)
            if failed:
                raise ValueError(f"learned constraints violated in segment {segment['id']}: {failed}")


@contextmanager
def open_policy(memory_path):
    if memory_path is None:
        yield None
        return
    memory = Memory(memory_path)
    # Hold the read transaction until save/export finishes, so an activation cannot
    # commit between the check and publication. No receipts from an unverified cache.
    with memory.db() as db:
        yield Policy(memory.snapshot_in(db))


def require_policy(project, policy, *, final=False):
    if project.evolution is not None:
        if policy is None:
            raise ValueError("memory-bound project requires --memory; learned constraints cannot be skipped")
        policy.context(project)
        if final:
            policy.check(project)
    elif policy is not None:
        raise ValueError("use evolve bind to choose the profile explicitly")


def undo(project):
    validate_binding(project.evolution)
    if not project.evolution or not project.evolution["history"]:
        raise ValueError("no evolution changes to undo")
    entry = project.evolution["history"][-1]
    if entry["after_hash"] != content_hash(project):
        raise ValueError("project was edited after this change; undo would overwrite those edits")
    candidate = copy.deepcopy(project)
    candidate.segments = copy.deepcopy(entry["before_segments"])
    candidate.evolution["history"].pop()
    candidate.evolution["receipt"] = {}  # restoring content never silently certifies it
    candidate.validate()
    project.segments, project.evolution = candidate.segments, candidate.evolution
