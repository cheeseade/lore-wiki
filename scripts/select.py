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
    # offset 직전 윈도우에 last_uuid 가 존재하면 연속성 OK(재작성 아님).
    if not offset or not last_uuid:
        return False
    window = 1 << 16
    start = max(0, offset - window)
    with open(path, "rb") as f:
        f.seek(start)
        chunk = f.read(offset - start)
    return last_uuid.encode("utf-8") in chunk


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
