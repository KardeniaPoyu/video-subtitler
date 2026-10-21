"""
Subtitle project file (``<video>.subtitler.json``): the single editable source of truth between
transcription and rendering.

    {
      "version": 1,
      "video": "D:/.../video.mp4",
      "video_info": {"width": 1920, "height": 1080, "duration": 812.4, "fps": 29.97},
      "source_lang": "ja", "target_lang": "zh",
      "domains": ["gaming_nintendo"], "kb_files": [],
      "notes": "free text: speaker, topic, tone - shown to translators",
      "segments": [
        {"id": 1, "start": 0.0, "end": 2.1, "text": "corrected source", "asr": "raw ASR", "translation": ""}
      ]
    }

The agent-in-the-loop workflow is:
    transcribe -> batch (print N lines with context + glossary hints)
               -> agent writes {"id": "translation"} JSON -> apply -> ... -> check -> render -> burn
"""

from __future__ import annotations

import json
import hashlib
import copy
import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from subtitler.asr import SubtitleSegment
from subtitler.safe_io import project_lock

PROJECT_SUFFIX = ".subtitler.json"


def default_project_path(video_path: str) -> str:
    return os.path.splitext(video_path)[0] + PROJECT_SUFFIX


def _fmt_t(t: float) -> str:
    t = round(max(0.0, t), 1)  # round first so 59.96 never prints as "60.0"
    m, s = divmod(t, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"


@dataclass
class Project:
    path: str
    video: str = ""
    video_info: Dict[str, Any] = field(default_factory=dict)
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    domains: List[str] = field(default_factory=list)
    kb_files: List[str] = field(default_factory=list)
    notes: str = ""
    model: str = ""
    segments: List[Dict[str, Any]] = field(default_factory=list)
    applied_splits: Dict[str, Any] = field(default_factory=dict)
    evolution: Optional[Dict[str, Any]] = None
    _revision: Optional[str] = field(default=None, repr=False)
    _saved_path: Optional[str] = field(default=None, repr=False)

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, "rb") as f:
            raw = f.read()
        data = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
            raise ValueError("项目必须是包含 segments 数组的 JSON 对象。")
        if data.get("version", 1) != 1:
            raise ValueError("不支持的项目版本。")
        segs = data.get("segments", [])
        for k, s in enumerate(segs, 1):
            if not isinstance(s, dict):
                raise ValueError(f"第 {k} 条字幕必须是对象。")
            s.setdefault("id", k)
            s.setdefault("translation", "")
            s.setdefault("asr", s.get("text", ""))
        project = cls(
            path=path,
            video=data.get("video", ""),
            video_info=data.get("video_info", {}),
            source_lang=data.get("source_lang"),
            target_lang=data.get("target_lang"),
            domains=data.get("domains", []),
            kb_files=data.get("kb_files", []),
            notes=data.get("notes", ""),
            model=data.get("model", ""),
            segments=segs,
            applied_splits=data.get("applied_splits", {}),
            evolution=data.get("evolution"),
            _revision=hashlib.sha256(raw).hexdigest(),
            _saved_path=os.path.abspath(path),
        )
        project.validate()
        return project

    def validate(self) -> None:
        """Reject malformed projects before rendering or modifying their contents."""
        from subtitler.evolution.runtime import validate_binding
        validate_binding(self.evolution)
        if not isinstance(self.video_info, dict):
            raise ValueError("video_info 必须是对象。")
        if not isinstance(self.applied_splits, dict):
            raise ValueError("applied_splits 必须是对象。")
        def finite_nonnegative(value):
            try:
                return type(value) in (int, float) and math.isfinite(value) and value >= 0
            except OverflowError:
                return False
        for key in ("width", "height", "duration", "fps"):
            if key in self.video_info and not finite_nonnegative(self.video_info[key]):
                raise ValueError(f"video_info.{key} 必须是有限非负数。")
        if not isinstance(self.segments, list):
            raise ValueError("segments 必须是数组。")
        for key in ("domains", "kb_files"):
            value = getattr(self, key)
            if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                raise ValueError(f"{key} 必须是字符串数组。")
        for key in ("video", "notes", "model"):
            if not isinstance(getattr(self, key), str):
                raise ValueError(f"{key} 必须是字符串。")
        for key in ("source_lang", "target_lang"):
            if getattr(self, key) is not None and not isinstance(getattr(self, key), str):
                raise ValueError(f"{key} 必须是字符串或 null。")
        seen = set()
        previous_start = -1
        for segment in self.segments:
            if not isinstance(segment, dict):
                raise ValueError("字幕必须是对象。")
            sid = segment.get("id")
            if type(sid) is not int or sid <= 0 or sid in seen:
                raise ValueError(f"字幕 id 必须是唯一正整数：{sid!r}")
            seen.add(sid)
            for key in ("start", "end"):
                value = segment.get(key)
                if not finite_nonnegative(value):
                    raise ValueError(f"字幕 {sid} 的 {key} 必须是有限非负数。")
            if segment["end"] <= segment["start"]:
                raise ValueError(f"字幕 {sid} 的结束时间必须晚于开始时间。")
            if segment["start"] < previous_start:
                raise ValueError("字幕必须按开始时间排序；请先调整时间轴。")
            previous_start = segment["start"]
            for key in ("text", "asr", "translation"):
                if not isinstance(segment.get(key, ""), str):
                    raise ValueError(f"字幕 {sid} 的 {key} 必须是字符串。")

    def save(self, path: Optional[str] = None, *, overwrite: bool = False) -> str:
        self.validate()
        path = path or self.path
        data = {
            "version": 1,
            "video": self.video,
            "video_info": self.video_info,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "domains": self.domains,
            "kb_files": self.kb_files,
            "notes": self.notes,
            "model": self.model,
            "segments": self.segments,
            "applied_splits": self.applied_splits,
            "evolution": self.evolution,
        }
        d = os.path.dirname(os.path.abspath(path))
        payload = json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
        with project_lock(os.path.abspath(path)):
            if os.path.lexists(path):
                if os.path.islink(path):
                    raise ValueError("拒绝通过符号链接保存项目。")
                with open(path, "rb") as existing:
                    revision = hashlib.sha256(existing.read()).hexdigest()
                if self._saved_path == os.path.abspath(path):
                    if self._revision != revision:
                        raise RuntimeError("项目已被其他任务修改；请重新加载后应用本次编辑。")
                elif not overwrite:
                    raise FileExistsError(f"项目已存在：{path}")
            elif self._saved_path == os.path.abspath(path) and self._revision is not None:
                raise RuntimeError("项目已被其他任务移除；请重新加载或另存为。")
            fd, tmp = tempfile.mkstemp(prefix=".subtitler_", suffix=".json", dir=d)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        self.path = path
        self._saved_path = os.path.abspath(path)
        self._revision = hashlib.sha256(payload).hexdigest()
        return path

    # ------------------------------------------------------------------ conversion
    @classmethod
    def from_segments(cls, path: str, segments: List[SubtitleSegment], **meta) -> "Project":
        # ASR backends can return NumPy scalars; the project format uses JSON-native numbers.
        segs = [{"id": i, "start": round(float(s.start), 3), "end": round(float(s.end), 3), "text": s.text,
                 "asr": s.text, "translation": s.translation or ""}
                for i, s in enumerate(segments, 1)]
        return cls(path=path, segments=segs, **meta)

    def to_segments(self) -> List[SubtitleSegment]:
        return [SubtitleSegment(float(s["start"]), float(s["end"]), s.get("text", ""),
                                (s.get("translation") or None)) for s in self.segments]

    def by_id(self) -> Dict[int, Dict[str, Any]]:
        return {int(s["id"]): s for s in self.segments}

    # ------------------------------------------------------------------ status
    def untranslated_ids(self) -> List[int]:
        return [int(s["id"]) for s in self.segments
                if s.get("text", "").strip() and not (s.get("translation") or "").strip()]

    def status(self) -> str:
        total = len(self.segments)
        missing = self.untranslated_ids()
        done = total - len(missing)
        dur = self.video_info.get("duration") or (self.segments[-1]["end"] if self.segments else 0)
        lines = [
            f"Project : {self.path}",
            f"Video   : {self.video}",
            f"Langs   : {self.source_lang or '?'} -> {self.target_lang or '(none)'}   domains: {', '.join(self.domains) or '-'}",
            f"Lines   : {total}   duration {_fmt_t(dur)}",
        ]
        if self.target_lang:
            nxt = missing[0] if missing else None
            lines.append(f"Translated: {done}/{total}" + (f"   next untranslated id: {nxt}" if nxt else "   (complete)"))
        return "\n".join(lines)

    # ------------------------------------------------------------------ agent batches
    def batch_text(self, start_id: Optional[int] = None, size: int = 60, context: int = 4,
                   knowledge=None, only_missing: bool = True) -> Tuple[str, List[int]]:
        """
        Render a batch for the agent to translate / proofread. Returns (text, ids_in_batch).
        If ``start_id`` is None, starts at the first untranslated line.
        """
        segs = self.segments
        if not segs:
            return "(project has no segments)", []
        index = {int(s["id"]): k for k, s in enumerate(segs)}
        if start_id is None:
            missing = self.untranslated_ids()
            if not missing and only_missing:
                return "All lines are translated. Run `subtitler check` next.", []
            start_id = missing[0] if missing else int(segs[0]["id"])
        k0 = index.get(start_id, 0)
        chosen = segs[k0:k0 + size]
        ids = [int(s["id"]) for s in chosen]

        out: List[str] = []
        total = len(segs)
        out.append(f"# BATCH ids {ids[0]}-{ids[-1]} of {total}  ({self.source_lang or '?'} -> {self.target_lang or '?'})")
        if self.notes:
            out.append(f"# NOTES: {self.notes}")
        if knowledge is not None and self.domains:
            hints = knowledge.glossary_hints("\n".join(s.get("text", "") for s in chosen), self.domains)
            if hints:
                out.append("# GLOSSARY (use exactly): " + "; ".join(f"{a} => {b}" for a, b in hints))
        before = segs[max(0, k0 - context):k0]
        if before:
            out.append("# CONTEXT (already done, do not output):")
            for s in before:
                tr = s.get("translation") or ""
                out.append(f"  [{s['id']}] {s.get('text', '')}" + (f"  => {tr}" if tr else ""))
        out.append("# LINES:")
        for s in chosen:
            tr = s.get("translation") or ""
            mark = f"  (current: {tr})" if tr else ""
            out.append(f"[{s['id']}] {_fmt_t(s['start'])}-{_fmt_t(s['end'])} | {s.get('text', '')}{mark}")
        after = segs[k0 + size:k0 + size + context]
        if after:
            out.append("# FOLLOWING (context only):")
            for s in after:
                out.append(f"  [{s['id']}] {s.get('text', '')}")
        out.append('# OUTPUT: a JSON file {"<id>": "<translation>"} (or {"<id>": {"text": "<fixed source>", '
                   '"translation": "..."}}), then: subtitler apply <project> <file.json>')
        return "\n".join(out), ids

    # ------------------------------------------------------------------ apply edits
    def apply(self, edits: Any, knowledge=None, glossary: bool = True, policy=None) -> Dict[str, Any]:
        """Apply all edits transactionally; invalid changes leave the project untouched."""
        from subtitler.evolution.runtime import require_policy
        require_policy(self, policy)
        if not isinstance(edits, (dict, list)):
            raise ValueError("编辑内容必须是 JSON 对象或数组。")
        has_split = isinstance(edits, dict) and any(
            str(k).isdigit() and isinstance(v, list) for k, v in edits.items())
        request = hashlib.sha256(json.dumps(edits, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if has_split and request in self.applied_splits:
            if policy is not None:
                policy.check(self)
            return {**copy.deepcopy(self.applied_splits[request]), "replayed": True}
        candidate = copy.deepcopy(self)
        result = candidate._apply(copy.deepcopy(edits), knowledge, glossary)
        candidate.validate()
        if policy is not None:
            result["evolution"] = policy.apply(candidate)
        self.segments = candidate.segments
        self.evolution = candidate.evolution
        if has_split:
            self.applied_splits[request] = copy.deepcopy(result)
        return result

    def _apply(self, edits: Any, knowledge=None, glossary: bool = True) -> Dict[str, Any]:
        """
        Merge agent edits. Accepted shapes:
          {"12": "译文"}                                   -> translation
          {"12": {"text": "修正原文", "translation": "译文", "start": 1.0, "end": 2.5}}
          [{"id": 12, "translation": "...", "text": "..."}]
          {"segments": [...]}                              (same as list)
          {"delete": [3, 4]}                               (drop lines, e.g. hallucinations)
          {"12": [{"text": "前半", "translation": "前半译文"},   (split one line into several;
                  {"text": "後半", "translation": "后半译文"}]}    times optional, proportional)
        Returns a report dict.
        """
        if isinstance(edits, dict) and "segments" in edits and isinstance(edits["segments"], list):
            deletes = edits.get("delete", [])
            edits = edits["segments"]
        elif isinstance(edits, dict):
            deletes = edits.pop("delete", []) if "delete" in edits else []
        else:
            deletes = []
        items: List[Tuple[int, Dict[str, Any]]] = []
        splits: List[Tuple[int, List[Dict[str, Any]]]] = []
        if isinstance(edits, dict):
            for k, v in edits.items():
                try:
                    sid = int(k)
                except (TypeError, ValueError):
                    continue
                if isinstance(v, list):
                    splits.append((sid, v))
                else:
                    items.append((sid, v if isinstance(v, dict) else {"translation": v}))
        elif isinstance(edits, list):
            for v in edits:
                if isinstance(v, dict) and "id" in v:
                    items.append((int(v["id"]), v))

        idx = self.by_id()
        report = {"translations": 0, "source_fixes": 0, "timing": 0, "unknown_ids": [], "deleted": 0}
        for sid, e in items:
            seg = idx.get(sid)
            if seg is None:
                report["unknown_ids"].append(sid)
                continue
            if "text" in e and e["text"] is not None and str(e["text"]).strip() != seg.get("text", ""):
                seg["text"] = str(e["text"]).strip()
                report["source_fixes"] += 1
            tr = e.get("translation", e.get("tgt", e.get("zh")))
            if tr is not None:
                tr = str(tr).strip()
                if glossary and knowledge is not None and self.domains:
                    tr = knowledge.apply_glossary(tr, self.domains)
                seg["translation"] = tr
                report["translations"] += 1
            for key in ("start", "end"):
                if key in e and e[key] is not None:
                    seg[key] = round(float(e[key]), 3)
                    report["timing"] += 1
        report["split"] = 0
        for sid, parts in splits:
            seg = idx.get(sid)
            if seg is None or not parts:
                report["unknown_ids"].append(sid)
                continue
            new_segs = self._split_segment(seg, parts, knowledge if glossary else None)
            pos = self.segments.index(seg)
            self.segments[pos:pos + 1] = new_segs
            report["split"] += len(new_segs) - 1
        if deletes:
            ds = {int(d) for d in deletes}
            before = len(self.segments)
            self.segments = [s for s in self.segments if int(s["id"]) not in ds]
            report["deleted"] = before - len(self.segments)
        return report

    def _split_segment(self, seg: Dict[str, Any], parts: List[Any], knowledge=None) -> List[Dict[str, Any]]:
        """
        Replace one line with several. ``parts`` items are dicts with text / translation and optional
        start / end; missing times are distributed proportionally to text length. The first part keeps
        the original id, the others get new ids (max id + 1, ...).
        """
        from subtitler.wrapper import display_width
        parts = [p if isinstance(p, dict) else {"translation": str(p)} for p in parts]
        weights = [max(1.0, display_width(str(p.get("translation") or p.get("text") or ""))) for p in parts]
        t0, t1 = float(seg["start"]), float(seg["end"])
        total = sum(weights)
        next_id = max(int(s["id"]) for s in self.segments) + 1
        out, cursor = [], t0
        for k, (p, w) in enumerate(zip(parts, weights)):
            start = float(p.get("start", cursor))
            end = float(p.get("end", t1 if k == len(parts) - 1 else cursor + (t1 - t0) * w / total))
            cursor = end
            tr = str(p.get("translation", "")).strip()
            if knowledge is not None and self.domains and tr:
                tr = knowledge.apply_glossary(tr, self.domains)
            out.append({
                "id": int(seg["id"]) if k == 0 else next_id + k - 1,
                "start": round(start, 3), "end": round(end, 3),
                "text": str(p.get("text", seg.get("text", "") if k == 0 else "")).strip(),
                "asr": seg.get("asr", "") if k == 0 else "",
                "translation": tr,
            })
        return out
