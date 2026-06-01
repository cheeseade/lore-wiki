"""Lore Wiki — 결정적 커서 갱신(유닛 단위)."""
import argparse
import json
import os
from datetime import datetime


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_cursor_path(config_path):
    raw = load_json(config_path, {})
    cp = raw.get("cursor_path") or "~/.claude/lore-wiki/cursor.json"
    return os.path.expanduser(cp)


def find_unit(manifest, unit_id):
    for u in manifest.get("units", []):
        if u.get("unit_id") == unit_id:
            return u
    return None


def update_cursor(cursor, unit_sessions, now_iso):
    sessions = cursor.setdefault("sessions", {})
    for s in unit_sessions:
        sessions[s["sessionId"]] = {
            "mtime": s["mtime"],
            "size": s["size"],
            "byteOffset": s["byteOffset"],
            "lastUuid": s["lastUuid"],
            "lastTimestamp": s["lastTimestamp"],
        }
    cursor["lastRun"] = now_iso
    return cursor


def main(argv=None):
    p = argparse.ArgumentParser(description="Lore Wiki 유닛 커서 커밋")
    p.add_argument("--config", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--unit", type=int, required=True)
    args = p.parse_args(argv)

    manifest = load_json(args.manifest, None)
    if manifest is None:
        raise SystemExit("manifest 없음: %s" % args.manifest)
    unit = find_unit(manifest, args.unit)
    if unit is None:
        raise SystemExit("유닛 %d 가 manifest 에 없음" % args.unit)

    cursor_path = load_cursor_path(args.config)
    cursor = load_json(cursor_path, {"lastRun": None, "sessions": {}})
    now_iso = datetime.now().astimezone().isoformat()
    update_cursor(cursor, unit["sessions"], now_iso)

    dir_part = os.path.dirname(cursor_path)
    if dir_part:
        os.makedirs(dir_part, exist_ok=True)
    with open(cursor_path, "w", encoding="utf-8") as f:
        json.dump(cursor, f, ensure_ascii=False, indent=2)
    print("커서 갱신: 유닛 %d (%d 세션)" % (args.unit, len(unit["sessions"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
