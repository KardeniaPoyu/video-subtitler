"""Closed, deterministic rule language. Evidence and models never supply code."""
from __future__ import annotations

import copy
import hashlib
import json
import re

KINDS = {"term", "translation", "source"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def string(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError(f"{label} must be nonempty text (up to {limit} characters)")
    return value


def strings(value, label, maximum=32):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError(f"{label} must be an array of up to {maximum} strings")
    for item in value:
        string(item, label, 200)
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicates")
    return value


def validate_scope(scope):
    if not isinstance(scope, dict) or set(scope) != {"profile", "source_lang", "target_lang", "domains"}:
        raise ValueError("scope requires exactly profile, source_lang, target_lang and domains")
    for key in ("profile", "source_lang", "target_lang"):
        string(scope[key], key, 100)
    if not strings(scope["domains"], "domains", 16):
        raise ValueError("an explicit content domain is required; no global rules")


def validate_rule(rule):
    if not isinstance(rule, dict) or set(rule) != {"kind", "scope", "trigger", "replacement", "aliases", "exclude"}:
        raise ValueError("rule requires exactly kind, scope, trigger, replacement, aliases and exclude")
    if not isinstance(rule["kind"], str) or rule["kind"] not in KINDS:
        raise ValueError("only term, translation and source rules are executable")
    validate_scope(rule["scope"])
    string(rule["trigger"], "trigger")
    string(rule["replacement"], "replacement")
    strings(rule["aliases"], "aliases")
    strings(rule["exclude"], "exclude")
    if rule["kind"] != "term" and rule["aliases"]:
        raise ValueError("aliases are only valid for term rules")
    if rule["trigger"] == rule["replacement"]:
        raise ValueError("identity rules do not teach a change")
    if rule["replacement"] in rule["aliases"]:
        raise ValueError("a canonical term cannot be a rejected alias")
    if rule["kind"] == "term" and max(len(rule["trigger"]), len(rule["replacement"])) > 200:
        raise ValueError("term rules are limited to 200 characters; use an exact translation for sentences")


def pattern(text):
    # Escaped literal only: no user-defined regex, expressions or executable plugins.
    text = re.escape(text)
    return r"(?<![A-Za-z0-9_])" + text + r"(?![A-Za-z0-9_])" if text.isascii() else text


def contains(term, text):
    return bool(re.search(pattern(term), text, flags=re.IGNORECASE))


def in_scope(rule, context):
    a = rule["scope"]
    return all(a[k] == context[k] for k in ("profile", "source_lang", "target_lang")) and bool(
        set(a["domains"]) & set(context["domains"]))


def applicable(rule, segment, context):
    if not in_scope(rule, context) or any(contains(x, segment["text"]) for x in rule["exclude"]):
        return False
    if rule["kind"] == "term":
        return contains(rule["trigger"], segment["text"])
    return rule["trigger"] == segment["text"]


def conflicts(rules):
    for i, a in enumerate(rules):
        for b in rules[i + 1:]:
            if (a["kind"] == b["kind"] and a["trigger"].casefold() == b["trigger"].casefold()
                    and a["replacement"] != b["replacement"] and in_scope(a, b["scope"])):
                # Conservative even if exclusions could separate two rules. Require explicit scopes.
                raise ValueError("conflicting active rules; revoke the old rule or separate its scope")


def violations(rules, segment, context):
    result = []
    for rule in rules:
        if not applicable(rule, segment, context):
            continue
        text = segment.get("translation", "")
        if rule["kind"] == "term":
            # Protect canonical phrases before looking for forbidden aliases inside them.
            remainder = re.sub(pattern(rule["replacement"]), "", text, flags=re.IGNORECASE)
            ok = contains(rule["replacement"], text) and not any(contains(a, remainder) for a in rule["aliases"])
        elif rule["kind"] == "translation":
            ok = text == rule["replacement"]
        else:
            ok = False  # the old source sentence is still present
        if not ok:
            result.append({"kind": rule["kind"], "trigger": rule["trigger"], "expected": rule["replacement"]})
    return result


def transform(rules, segment, context):
    """One pass over the original segment, followed by a hard postcondition check.

    Simultaneous proposals never feed one another. Ambiguity is an error, not an
    order-dependent replacement. Unknown translations are not filled by term rules.
    """
    original = copy.deepcopy(segment)
    result = copy.deepcopy(segment)
    selected = [r for r in rules if applicable(r, original, context)]
    for kind, field in (("source", "text"), ("translation", "translation")):
        replacements = {r["replacement"] for r in selected if r["kind"] == kind}
        if len(replacements) > 1:
            raise ValueError(f"ambiguous {kind} rules")
        if replacements:
            result[field] = replacements.pop()
    proposals = []
    text = result.get("translation", "")
    for r in selected:
        if r["kind"] != "term":
            continue
        protected = [m.span() for m in re.finditer(pattern(r["replacement"]), text, re.IGNORECASE)]
        for alias in list(dict.fromkeys(r["aliases"] + [r["trigger"]])):
            for m in re.finditer(pattern(alias), text, re.IGNORECASE):
                if not any(lo <= m.start() and m.end() <= hi for lo, hi in protected):
                    proposals.append((m.start(), m.end(), r["replacement"]))
    proposals = sorted(set(proposals))
    for a, b in zip(proposals, proposals[1:]):
        if b[0] < a[1]:
            raise ValueError("overlapping term rewrites; review the conflicting rules")
    for start, end, replacement in reversed(proposals):
        text = text[:start] + replacement + text[end:]
    result["translation"] = text
    # Source correction can expose another rule; require a new reviewed pass, never cascade.
    failed = violations(rules, result, context)
    if failed:
        raise ValueError("unresolved learned constraints: " + canonical(failed))
    return result


def validate_case(case):
    if not isinstance(case, dict) or set(case) != {"name", "context", "input", "expected"}:
        raise ValueError("case requires name, context, input and expected")
    string(case["name"], "case name", 200)
    validate_scope(case["context"])
    for key in ("input", "expected"):
        value = case[key]
        if not isinstance(value, dict) or set(value) != {"text", "translation"}:
            raise ValueError(f"case {key} requires exactly text and translation")
        string(value["text"], "case text")
        if not isinstance(value["translation"], str) or len(value["translation"]) > 4000:
            raise ValueError("case translation must be text of up to 4000 characters")
