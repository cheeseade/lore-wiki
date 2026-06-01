"""Lore Wiki — 결정적 선별·증분추출·신호필터·bin-packing 헬퍼."""
import fnmatch
import glob
import json
import os

DEFAULTS = {
    "session_root": "~/.claude/projects",
    "output_dir": None,
    "include": ["*"],
    "exclude": [],
    "cursor_path": "~/.claude/lore-wiki/cursor.json",
    "obsidian": False,
    "wikilink": False,
    "batch_max_bytes": 40000,
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_config(path):
    raw = load_json(path, {})
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in raw.items() if v is not None})
    cfg["session_root"] = os.path.expanduser(cfg["session_root"])
    cfg["cursor_path"] = os.path.expanduser(cfg["cursor_path"])
    if cfg["output_dir"]:
        cfg["output_dir"] = os.path.expanduser(cfg["output_dir"])
    return cfg


def pack_units(segments, cap):
    units = []
    current = []
    current_bytes = 0
    for seg in segments:
        sb = seg["extracted_bytes"]
        if sb > cap:
            if current:
                units.append(current)
                current, current_bytes = [], 0
            units.append([seg])
            continue
        if current and current_bytes + sb > cap:
            units.append(current)
            current, current_bytes = [], 0
        current.append(seg)
        current_bytes += sb
    if current:
        units.append(current)
    return units


def match_cwd(cwd, include, exclude):
    c = cwd or ""
    if include and not any(fnmatch.fnmatch(c, p) for p in include):
        return False
    if any(fnmatch.fnmatch(c, p) for p in exclude):
        return False
    return True


def list_session_files(session_root):
    pattern = os.path.join(session_root, "**", "*.jsonl")
    return sorted(glob.glob(pattern, recursive=True))


def _text_from_content(content):
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for b in content:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            parts.append(b.get("text", ""))
        elif t == "tool_use":
            name = b.get("name", "tool")
            inp = b.get("input", {}) or {}
            summary = inp.get("command") or inp.get("file_path") \
                or json.dumps(inp, ensure_ascii=False)[:200]
            parts.append("[tool_use %s] %s" % (name, summary))
        # thinking / tool_result / 기타: 제거
    return "\n".join(p for p in parts if p).strip()


def extract_signals(objs):
    blocks = []
    meta = {"sessionId": None, "cwd": None, "gitBranch": None,
            "lastUuid": None, "lastTimestamp": None}
    for o in objs:
        if not isinstance(o, dict):
            continue
        for k in ("sessionId", "cwd", "gitBranch"):
            if o.get(k):
                meta[k] = o[k]
        if o.get("uuid"):
            meta["lastUuid"] = o["uuid"]
        if o.get("timestamp"):
            meta["lastTimestamp"] = o["timestamp"]
        typ = o.get("type")
        msg = o.get("message")
        if typ in ("user", "assistant") and isinstance(msg, dict):
            txt = _text_from_content(msg.get("content"))
            if txt:
                blocks.append("## %s\n%s" % (typ, txt))
    meta["text"] = "\n\n".join(blocks).strip()
    return meta


def parse_jsonl_lines(lines):
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read_from(path, offset):
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    return data.decode("utf-8", errors="replace")


def _validate_offset(path, offset, last_uuid):
    # offset 직전 윈도우가 라인 경계(\n)로 끝나고, 그 안에 last_uuid 가
    # JSON uuid 키 값으로 존재해야 연속성 OK(재작성/오프셋 깨짐 아님).
    # 단순 부분문자열 매칭은 본문에 박힌 uuid 로 오탐(silent mis-read)나므로
    # keyed 매칭 + 경계 확인으로 안전하게 fallback 한다.
    if not offset or not last_uuid:
        return False
    window = 1 << 16
    start = max(0, offset - window)
    with open(path, "rb") as f:
        f.seek(start)
        chunk = f.read(offset - start)
    if not chunk.endswith(b"\n"):
        return False
    u = last_uuid.encode("utf-8")
    return (b'"uuid":"' + u + b'"') in chunk or (b'"uuid": "' + u + b'"') in chunk


def build_segment(path, action, entry):
    st = os.stat(path)
    fell_back = False
    if action == "append" and _validate_offset(
            path, entry.get("byteOffset", 0), entry.get("lastUuid")):
        raw = _read_from(path, entry["byteOffset"])
    else:
        if action == "append":
            fell_back = True
        raw = _read_from(path, 0)
    objs = parse_jsonl_lines(raw.splitlines())
    sig = extract_signals(objs)
    if not sig["text"]:
        # 신호 없는(노이즈만) append 는 유닛을 만들지 않아 커서가 전진하지 않는다.
        # → 다음 실행에 새 바이트만 재추출(LLM 미개입, 저비용). 의도된 v1 절충.
        return None
    return {
        "sessionId": sig["sessionId"] or session_id_of(path),
        "path": path,
        "cwd": sig["cwd"],
        "gitBranch": sig["gitBranch"],
        "mtime": st.st_mtime,
        "size": st.st_size,
        "byteOffset": st.st_size,
        "lastUuid": sig["lastUuid"],
        "lastTimestamp": sig["lastTimestamp"],
        "text": sig["text"],
        "extracted_bytes": len(sig["text"].encode("utf-8")),
        "fell_back": fell_back,
    }


def session_id_of(path):
    base = os.path.basename(path)
    return base[:-len(".jsonl")] if base.endswith(".jsonl") else base


def classify_file(path, cursor_sessions):
    sid = session_id_of(path)
    st = os.stat(path)
    entry = cursor_sessions.get(sid)
    if entry is None:
        return "new", None
    if st.st_size == entry.get("size") and st.st_mtime == entry.get("mtime"):
        return "skip", entry
    if st.st_size > entry.get("size", 0):
        return "append", entry
    return "rescan", entry


def write_run(run_dir, units):
    os.makedirs(run_dir, exist_ok=True)
    # 이전 실행 산출물(manifest.json, unit-*.md)만 제거 — run_dir 자체나
    # 무관한 파일은 건드리지 않는다(잘못 지정된 --run-dir 보호).
    for name in os.listdir(run_dir):
        if name == "manifest.json" or (name.startswith("unit-") and name.endswith(".md")):
            os.remove(os.path.join(run_dir, name))
    manifest = {"run_dir": run_dir, "units": []}
    meta_keys = ("sessionId", "path", "cwd", "gitBranch", "mtime",
                 "size", "byteOffset", "lastUuid", "lastTimestamp")
    for i, segs in enumerate(units, start=1):
        fname = "unit-%02d.md" % i
        parts = []
        sess_meta = []
        for seg in segs:
            header = "# session %s (cwd=%s, branch=%s, ts=%s)" % (
                seg["sessionId"], seg["cwd"], seg["gitBranch"],
                seg["lastTimestamp"])
            parts.append(header + "\n\n" + seg["text"])
            sess_meta.append({k: seg[k] for k in meta_keys})
        with open(os.path.join(run_dir, fname), "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(parts))
        manifest["units"].append({
            "unit_id": i,
            "file": fname,
            "extracted_bytes": sum(s["extracted_bytes"] for s in segs),
            "sessions": sess_meta,
        })
    return manifest


def _write_manifest(run_dir, manifest):
    with open(os.path.join(run_dir, "manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def run(config_path, run_dir):
    cfg = load_config(config_path)
    cursor = load_json(cfg["cursor_path"], {"lastRun": None, "sessions": {}})
    sessions = cursor.get("sessions", {})
    files = list_session_files(cfg["session_root"])
    scanned = skipped = 0
    segments = []
    for path in files:
        scanned += 1
        action, entry = classify_file(path, sessions)
        if action == "skip":
            skipped += 1
            continue
        seg = build_segment(path, action, entry or {})
        if seg is None:
            continue
        if not match_cwd(seg["cwd"], cfg["include"], cfg["exclude"]):
            continue
        segments.append(seg)
    units = pack_units(segments, cfg["batch_max_bytes"])
    manifest = write_run(run_dir, units)
    manifest["scanned"] = scanned
    manifest["skipped"] = skipped
    _write_manifest(run_dir, manifest)
    return manifest


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Lore Wiki 세션 선별·증분추출")
    p.add_argument("--config",
                   default=os.path.expanduser("~/.claude/lore-wiki/config.json"))
    p.add_argument("--run-dir",
                   default=os.path.expanduser("~/.claude/lore-wiki/run"))
    args = p.parse_args(argv)
    run(args.config, args.run_dir)
    print(args.run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
