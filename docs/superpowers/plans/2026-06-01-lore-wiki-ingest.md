# Lore Wiki ingest 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code 세션 JSONL을 증류해 마크다운 지식 위키로 쌓는 `/lore-wiki ingest` 도구를, 결정적 Python 헬퍼 + LLM 오케스트레이션 명령으로 구성된 Claude Code 플러그인으로 구현한다.

**Architecture:** 결정적 헬퍼(`select.py`=선별·증분추출·신호필터·bin-packing, `commit_cursor.py`=커서 갱신)가 깨끗한 증류용 유닛을 산출하면, 명령(`commands/lore-wiki.md`)이 유닛 단위로 LLM 증류 → 기존 페이지 병합/신규 생성 → 커서 커밋을 오케스트레이션한다. 결정적/LLM 경계를 엄격히 분리한다.

**Tech Stack:** Python 3.9+ (stdlib only — `json`, `os`, `glob`, `fnmatch`, `shutil`, `argparse`, `datetime`, `importlib`), `unittest`(테스트), Claude Code 플러그인(plugin.json + commands/). 외부 의존 0.

**스펙:** `docs/superpowers/specs/2026-06-01-lore-wiki-design.md`

---

## 파일 구조

| 파일 | 책임 |
| --- | --- |
| `.claude-plugin/plugin.json` | 플러그인 매니페스트 (이름/버전/설명) |
| `config.example.json` | config 템플릿 (개인 경로 미포함) |
| `.gitignore` | `__pycache__`, 로컬 산출물 제외 |
| `scripts/select.py` | 결정적: config 로드 · 파일 나열 · stat 분류 · 증분 추출 · 신호 필터 · cwd glob · bin-packing · run_dir 작성 · CLI |
| `scripts/commit_cursor.py` | 결정적: 유닛 단위 cursor.json 갱신 · CLI |
| `commands/lore-wiki.md` | LLM 오케스트레이션 (서브커맨드 파싱 · 첫실행 스캐폴딩 · 유닛 루프 증류 · log.md · 커밋 호출) |
| `templates/schema.CLAUDE.md` | 스캐폴딩용 최소 시드 schema |
| `README.md` | 설치 · 설정 · 사용법 |
| `tests/loader.py` | `importlib`로 `scripts/*.py`를 별칭 모듈로 로드(이름 충돌 회피) |
| `tests/test_select.py` | `select.py` 단위/통합 테스트 |
| `tests/test_commit_cursor.py` | `commit_cursor.py` 단위/통합 테스트 |

**설계 결정:**
- `select.py`/`commit_cursor.py`는 함수 단위로 작성하고, `if __name__ == "__main__"`에서만 CLI 실행 → 테스트가 함수를 직접 호출.
- 테스트 실행: 각 테스트 파일을 직접 실행 — `python3 tests/test_select.py -v`. 패키지(`__init__.py`) 불필요.
- 작은 헬퍼 `load_json`은 두 스크립트에 각각 둔다(4줄, 교차 import의 이름 충돌 회피 위해 의도적 중복).
- 커밋 메시지는 **한글**(사용자 전역 규약).

---

## Task 1: 플러그인 스캐폴딩

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `config.example.json`
- Create: `.gitignore`
- Create: `tests/loader.py`

- [ ] **Step 1: 플러그인 매니페스트 작성**

`.claude-plugin/plugin.json`:
```json
{
  "name": "lore-wiki",
  "version": "0.1.0",
  "description": "Claude Code 세션을 증류해 마크다운 지식 위키로 쌓는 ingest 도구"
}
```

- [ ] **Step 2: config 템플릿 작성**

`config.example.json`:
```json
{
  "session_root": "~/.claude/projects",
  "output_dir": null,
  "include": ["*"],
  "exclude": [],
  "cursor_path": "~/.claude/lore-wiki/cursor.json",
  "obsidian": false,
  "wikilink": false,
  "batch_max_bytes": 40000
}
```

- [ ] **Step 3: .gitignore 작성**

`.gitignore`:
```
__pycache__/
*.pyc
```

- [ ] **Step 4: 테스트 로더 작성**

`tests/loader.py`:
```python
"""scripts/*.py 를 별칭 모듈로 로드한다(select.py 가 stdlib select 와 겹치는 문제 회피)."""
import importlib.util
import os

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")


def load(modname, filename):
    path = os.path.abspath(os.path.join(SCRIPTS, filename))
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
```

- [ ] **Step 5: JSON 유효성 검증**

Run: `python3 -c "import json; json.load(open('.claude-plugin/plugin.json')); json.load(open('config.example.json')); print('OK')"`
Expected: `OK`

- [ ] **Step 6: 커밋**

```bash
git add .claude-plugin/plugin.json config.example.json .gitignore tests/loader.py
git commit -m "플러그인 스캐폴딩: 매니페스트·config 예시·테스트 로더"
```

---

## Task 2: config 로딩 (`load_config`, `load_json`)

**Files:**
- Create: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_select.py`:
```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from loader import load

sel = load("lore_select", "select.py")


class TestLoadConfig(unittest.TestCase):
    def test_defaults_filled_and_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.json")
            with open(p, "w") as f:
                json.dump({"output_dir": "/tmp/wiki", "include": ["/work/*"]}, f)
            cfg = sel.load_config(p)
            self.assertEqual(cfg["include"], ["/work/*"])
            self.assertEqual(cfg["exclude"], [])           # default
            self.assertEqual(cfg["batch_max_bytes"], 40000)  # default
            self.assertEqual(cfg["output_dir"], "/tmp/wiki")

    def test_tilde_expansion(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "config.json")
            with open(p, "w") as f:
                json.dump({"output_dir": "/tmp/wiki"}, f)
            cfg = sel.load_config(p)
            self.assertTrue(cfg["session_root"].startswith(os.path.expanduser("~")))
            self.assertNotIn("~", cfg["cursor_path"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `ModuleNotFoundError`/`AttributeError` (select.py 없음 또는 `load_config` 미정의)

- [ ] **Step 3: 최소 구현**

`scripts/select.py`:
```python
"""Lore Wiki — 결정적 선별·증분추출·신호필터·bin-packing 헬퍼."""
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: config 로딩(기본값·~ 확장) 추가"
```

---

## Task 3: 세션 파일 나열 (`list_session_files`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_select.py` 에 클래스 추가:
```python
class TestListSessionFiles(unittest.TestCase):
    def test_lists_jsonl_recursively_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "projA"))
            os.makedirs(os.path.join(d, "projB", "sub"))
            open(os.path.join(d, "projA", "b.jsonl"), "w").close()
            open(os.path.join(d, "projA", "a.jsonl"), "w").close()
            open(os.path.join(d, "projB", "sub", "c.jsonl"), "w").close()
            open(os.path.join(d, "projA", "note.txt"), "w").close()
            files = sel.list_session_files(d)
            self.assertEqual(len(files), 3)
            self.assertTrue(all(f.endswith(".jsonl") for f in files))
            self.assertEqual(files, sorted(files))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'list_session_files'`

- [ ] **Step 3: 최소 구현**

`scripts/select.py` 에 추가:
```python
import glob


def list_session_files(session_root):
    pattern = os.path.join(session_root, "**", "*.jsonl")
    return sorted(glob.glob(pattern, recursive=True))
```
(`import glob` 은 파일 상단 import 블록으로 옮겨도 됨.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: 세션 JSONL 재귀 나열 추가"
```

---

## Task 4: stat 분류 (`session_id_of`, `classify_file`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestClassifyFile(unittest.TestCase):
    def _make(self, d, name, content):
        p = os.path.join(d, name)
        with open(p, "w") as f:
            f.write(content)
        return p

    def test_new_skip_append_rescan(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._make(d, "s1.jsonl", "line1\n")
            self.assertEqual(sel.session_id_of(p), "s1")

            # 커서에 없음 → new
            action, entry = sel.classify_file(p, {})
            self.assertEqual(action, "new")
            self.assertIsNone(entry)

            st = os.stat(p)
            cur = {"s1": {"size": st.st_size, "mtime": st.st_mtime,
                          "byteOffset": st.st_size, "lastUuid": "u"}}
            # 동일 → skip
            self.assertEqual(sel.classify_file(p, cur)[0], "skip")

            # 증가 → append
            with open(p, "a") as f:
                f.write("line2\n")
            self.assertEqual(sel.classify_file(p, cur)[0], "append")

            # 감소 → rescan
            cur2 = {"s1": {"size": 9999, "mtime": st.st_mtime,
                           "byteOffset": 9999, "lastUuid": "u"}}
            self.assertEqual(sel.classify_file(p, cur2)[0], "rescan")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'session_id_of'`

- [ ] **Step 3: 최소 구현**

`scripts/select.py` 에 추가:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: stat 기반 파일 분류(new/skip/append/rescan) 추가"
```

---

## Task 5: 관용적 JSONL 파싱 (`parse_jsonl_lines`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestParseJsonl(unittest.TestCase):
    def test_skips_blank_and_broken(self):
        lines = [
            '{"type":"user","uuid":"1"}',
            '',
            'not json at all',
            '   ',
            '{"type":"mode","uuid":"2"}',
        ]
        objs = sel.parse_jsonl_lines(lines)
        self.assertEqual(len(objs), 2)
        self.assertEqual(objs[0]["uuid"], "1")
        self.assertEqual(objs[1]["type"], "mode")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'parse_jsonl_lines'`

- [ ] **Step 3: 최소 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: 관용적 JSONL 파싱(빈 줄·깨진 줄 skip) 추가"
```

---

## Task 6: 신호 추출 (`_text_from_content`, `extract_signals`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestExtractSignals(unittest.TestCase):
    def test_keeps_signals_drops_noise(self):
        objs = [
            {"type": "user", "uuid": "u1", "timestamp": "T1",
             "sessionId": "S", "cwd": "/work/app", "gitBranch": "main",
             "message": {"role": "user", "content": "에러 어떻게 고쳐?"}},
            {"type": "assistant", "uuid": "a1", "timestamp": "T2",
             "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "음 노이즈"},
                 {"type": "text", "text": "이렇게 고치면 됩니다"},
                 {"type": "tool_use", "name": "Bash",
                  "input": {"command": "npm test"}},
             ]}},
            {"type": "ai-title", "uuid": "x1", "title": "무시"},
        ]
        sig = sel.extract_signals(objs)
        self.assertIn("에러 어떻게 고쳐?", sig["text"])
        self.assertIn("이렇게 고치면 됩니다", sig["text"])
        self.assertIn("npm test", sig["text"])
        self.assertNotIn("음 노이즈", sig["text"])   # thinking 제거
        self.assertEqual(sig["lastUuid"], "x1")        # 마지막 uuid
        self.assertEqual(sig["cwd"], "/work/app")
        self.assertEqual(sig["gitBranch"], "main")
        self.assertEqual(sig["sessionId"], "S")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'extract_signals'`

- [ ] **Step 3: 최소 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: 신호 추출(user/assistant/tool_use 보존, thinking·noise 제거) 추가"
```

---

## Task 7: 증분 읽기 + offset 검증 (`_read_from`, `_validate_offset`, `build_segment`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestBuildSegment(unittest.TestCase):
    def _session_lines(self):
        return [
            json.dumps({"type": "user", "uuid": "u1", "parentUuid": None,
                        "timestamp": "T1", "sessionId": "S",
                        "cwd": "/work/app", "gitBranch": "main",
                        "message": {"role": "user", "content": "Q1"}}),
            json.dumps({"type": "assistant", "uuid": "a1", "parentUuid": "u1",
                        "timestamp": "T2",
                        "message": {"role": "assistant",
                                    "content": [{"type": "text", "text": "A1"}]}}),
        ]

    def test_new_reads_all(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "S.jsonl")
            with open(p, "w") as f:
                f.write("\n".join(self._session_lines()) + "\n")
            seg = sel.build_segment(p, "new", {})
            self.assertIn("Q1", seg["text"])
            self.assertIn("A1", seg["text"])
            self.assertEqual(seg["byteOffset"], os.stat(p).st_size)
            self.assertEqual(seg["lastUuid"], "a1")
            self.assertGreater(seg["extracted_bytes"], 0)

    def test_append_valid_offset_reads_only_new(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "S.jsonl")
            first = self._session_lines()[0] + "\n"
            with open(p, "w") as f:
                f.write(first)
            off = os.stat(p).st_size
            entry = {"byteOffset": off, "lastUuid": "u1",
                     "size": off, "mtime": os.stat(p).st_mtime}
            with open(p, "a") as f:
                f.write(self._session_lines()[1] + "\n")
            seg = sel.build_segment(p, "append", entry)
            self.assertIn("A1", seg["text"])
            self.assertNotIn("Q1", seg["text"])      # 이전 분은 안 읽음
            self.assertFalse(seg["fell_back"])

    def test_append_broken_offset_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "S.jsonl")
            with open(p, "w") as f:
                f.write("\n".join(self._session_lines()) + "\n")
            # lastUuid 가 파일에 없음 → 재작성 의심 → fallback
            entry = {"byteOffset": 5, "lastUuid": "GHOST",
                     "size": 5, "mtime": 0}
            seg = sel.build_segment(p, "append", entry)
            self.assertTrue(seg["fell_back"])
            self.assertIn("Q1", seg["text"])         # 전체 재읽기
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'build_segment'`

- [ ] **Step 3: 최소 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (9 tests — 위 3개 추가)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: 증분 읽기 + offset 검증 fallback(build_segment) 추가"
```

---

## Task 8: cwd glob 필터 (`match_cwd`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestMatchCwd(unittest.TestCase):
    def test_include_exclude(self):
        self.assertTrue(sel.match_cwd("/work/app", ["/work/*"], []))
        self.assertFalse(sel.match_cwd("/home/x", ["/work/*"], []))
        self.assertFalse(sel.match_cwd("/work/sandbox", ["/work/*"], ["*/sandbox"]))
        self.assertTrue(sel.match_cwd("/anything", ["*"], []))       # 기본 전체
        self.assertTrue(sel.match_cwd(None, ["*"], []))              # cwd 없음 허용
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'match_cwd'`

- [ ] **Step 3: 최소 구현**

```python
import fnmatch


def match_cwd(cwd, include, exclude):
    c = cwd or ""
    if include and not any(fnmatch.fnmatch(c, p) for p in include):
        return False
    if any(fnmatch.fnmatch(c, p) for p in exclude):
        return False
    return True
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: cwd 기준 include/exclude glob 필터 추가"
```

---

## Task 9: 유닛 bin-packing (`pack_units`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestPackUnits(unittest.TestCase):
    def _seg(self, sid, n):
        return {"sessionId": sid, "extracted_bytes": n}

    def test_batches_small_and_isolates_oversize(self):
        segs = [
            self._seg("a", 10),
            self._seg("b", 10),
            self._seg("big", 100),   # cap 초과 → 단독
            self._seg("c", 10),
        ]
        units = sel.pack_units(segs, cap=25)
        # a+b (20<=25), big 단독, c
        self.assertEqual([[s["sessionId"] for s in u] for u in units],
                         [["a", "b"], ["big"], ["c"]])

    def test_boundary_exact_cap(self):
        segs = [self._seg("a", 25), self._seg("b", 1)]
        units = sel.pack_units(segs, cap=25)
        # a 채워 25, b 추가하면 26>25 → 새 유닛
        self.assertEqual([[s["sessionId"] for s in u] for u in units],
                         [["a"], ["b"]])
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'pack_units'`

- [ ] **Step 3: 최소 구현**

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: 추출 크기 기반 유닛 bin-packing 추가"
```

---

## Task 10: run_dir 작성 + CLI (`write_run`, `run`, `main`)

**Files:**
- Modify: `scripts/select.py`
- Test: `tests/test_select.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
class TestRunIntegration(unittest.TestCase):
    def _write_session(self, root, proj, sid, q, a, cwd):
        pdir = os.path.join(root, proj)
        os.makedirs(pdir, exist_ok=True)
        lines = [
            json.dumps({"type": "user", "uuid": sid + "-u", "parentUuid": None,
                        "timestamp": "T1", "sessionId": sid, "cwd": cwd,
                        "gitBranch": "main",
                        "message": {"role": "user", "content": q}}),
            json.dumps({"type": "assistant", "uuid": sid + "-a",
                        "parentUuid": sid + "-u", "timestamp": "T2",
                        "message": {"role": "assistant",
                                    "content": [{"type": "text", "text": a}]}}),
        ]
        with open(os.path.join(pdir, sid + ".jsonl"), "w") as f:
            f.write("\n".join(lines) + "\n")

    def test_end_to_end_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "projects")
            self._write_session(root, "projA", "S1", "질문1", "답1", "/work/app")
            self._write_session(root, "projB", "S2", "질문2", "답2", "/home/x")
            cfg_path = os.path.join(d, "config.json")
            with open(cfg_path, "w") as f:
                json.dump({"session_root": root,
                           "cursor_path": os.path.join(d, "cursor.json"),
                           "include": ["/work/*"]}, f)
            run_dir = os.path.join(d, "run")
            manifest = sel.run(cfg_path, run_dir)

            # /home/x 는 include 에서 제외 → S1 만 ingest
            self.assertEqual(len(manifest["units"]), 1)
            unit = manifest["units"][0]
            self.assertEqual(unit["sessions"][0]["sessionId"], "S1")
            # 유닛 파일 존재 + 내용
            with open(os.path.join(run_dir, unit["file"])) as f:
                body = f.read()
            self.assertIn("질문1", body)
            self.assertIn("답1", body)
            # manifest.json 디스크 기록 확인
            with open(os.path.join(run_dir, "manifest.json")) as f:
                disk = json.load(f)
            self.assertIn("scanned", disk)
            self.assertEqual(disk["units"][0]["sessions"][0]["sessionId"], "S1")
            # 유닛 파일엔 text 미포함(매니페스트는 메타만)
            self.assertNotIn("text", unit["sessions"][0])
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_select.py -v`
Expected: FAIL — `AttributeError: ... 'run'`

- [ ] **Step 3: 최소 구현**

```python
import shutil


def write_run(run_dir, units):
    if os.path.isdir(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_select.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: 커밋**

```bash
git add scripts/select.py tests/test_select.py
git commit -m "select: run_dir 작성(manifest+unit 파일)·run·CLI main 추가"
```

---

## Task 11: 커서 커밋 (`commit_cursor.py`)

**Files:**
- Create: `scripts/commit_cursor.py`
- Test: `tests/test_commit_cursor.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_commit_cursor.py`:
```python
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from loader import load

cc = load("lore_commit_cursor", "commit_cursor.py")


class TestUpdateCursor(unittest.TestCase):
    def test_update_sets_entries_and_lastrun(self):
        cursor = {"lastRun": None, "sessions": {}}
        unit_sessions = [
            {"sessionId": "S1", "mtime": 1.0, "size": 100,
             "byteOffset": 100, "lastUuid": "u1", "lastTimestamp": "T1"},
        ]
        out = cc.update_cursor(cursor, unit_sessions, "NOW")
        self.assertEqual(out["lastRun"], "NOW")
        self.assertEqual(out["sessions"]["S1"]["byteOffset"], 100)
        self.assertEqual(out["sessions"]["S1"]["lastUuid"], "u1")


class TestCommitMain(unittest.TestCase):
    def test_main_writes_cursor_for_unit(self):
        with tempfile.TemporaryDirectory() as d:
            cursor_path = os.path.join(d, "sub", "cursor.json")
            cfg_path = os.path.join(d, "config.json")
            with open(cfg_path, "w") as f:
                json.dump({"cursor_path": cursor_path}, f)
            run_dir = os.path.join(d, "run")
            os.makedirs(run_dir)
            manifest = {"run_dir": run_dir, "units": [
                {"unit_id": 1, "file": "unit-01.md", "extracted_bytes": 5,
                 "sessions": [{"sessionId": "S1", "mtime": 1.0, "size": 100,
                               "byteOffset": 100, "lastUuid": "u1",
                               "lastTimestamp": "T1"}]},
            ]}
            mpath = os.path.join(run_dir, "manifest.json")
            with open(mpath, "w") as f:
                json.dump(manifest, f)

            rc = cc.main(["--config", cfg_path, "--manifest", mpath, "--unit", "1"])
            self.assertEqual(rc, 0)
            with open(cursor_path) as f:
                cur = json.load(f)
            self.assertEqual(cur["sessions"]["S1"]["lastUuid"], "u1")
            self.assertIsNotNone(cur["lastRun"])

    def test_main_unknown_unit_errors(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = os.path.join(d, "config.json")
            with open(cfg_path, "w") as f:
                json.dump({"cursor_path": os.path.join(d, "cursor.json")}, f)
            mpath = os.path.join(d, "manifest.json")
            with open(mpath, "w") as f:
                json.dump({"run_dir": d, "units": []}, f)
            with self.assertRaises(SystemExit):
                cc.main(["--config", cfg_path, "--manifest", mpath, "--unit", "9"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 tests/test_commit_cursor.py -v`
Expected: FAIL — `commit_cursor.py` 없음

- [ ] **Step 3: 최소 구현**

`scripts/commit_cursor.py`:
```python
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

    os.makedirs(os.path.dirname(cursor_path), exist_ok=True)
    with open(cursor_path, "w", encoding="utf-8") as f:
        json.dump(cursor, f, ensure_ascii=False, indent=2)
    print("커서 갱신: 유닛 %d (%d 세션)" % (args.unit, len(unit["sessions"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 tests/test_commit_cursor.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 전체 테스트 회귀 확인 + 커밋**

Run: `python3 tests/test_select.py && python3 tests/test_commit_cursor.py`
Expected: 둘 다 OK

```bash
git add scripts/commit_cursor.py tests/test_commit_cursor.py
git commit -m "commit_cursor: 유닛 단위 커서 갱신 헬퍼 추가"
```

---

## Task 12: 명령 오케스트레이션 (`commands/lore-wiki.md`)

**Files:**
- Create: `commands/lore-wiki.md`

LLM 오케스트레이션 명령. 코드 테스트 없음 — 전체 내용을 작성하고 frontmatter·핵심 절차 존재를 검증한다.

- [ ] **Step 1: 명령 파일 작성**

`commands/lore-wiki.md`:
````markdown
---
name: lore-wiki
description: Claude Code 세션을 증류해 마크다운 지식 위키로 ingest 한다 (기본 서브커맨드 ingest)
---

Claude Code 세션 JSONL 을 raw source 로 읽어 지식노트(entity/decision/how-to)로 증류·누적한다. 결정적 선별·증분추출은 플러그인 헬퍼(`scripts/select.py`, `scripts/commit_cursor.py`)가, 증류는 이 명령(LLM)이 담당한다.

## 호출 인터페이스

| 인자 | 의미 |
|---|---|
| (없음) | `ingest` 와 동일 (기본) |
| `ingest` | 새 세션 증분 ingest |

`query`·`lint` 는 후속 스펙. 현재는 ingest 만.

## 경로

- 헬퍼: `${CLAUDE_PLUGIN_ROOT}/scripts/select.py`, `${CLAUDE_PLUGIN_ROOT}/scripts/commit_cursor.py` (플러그인 번들 파일은 `${CLAUDE_PLUGIN_ROOT}` 로 참조)
- config: `~/.claude/lore-wiki/config.json` (없으면 첫 실행 플로우)
- 이 명령은 **출력 디렉토리(위키)에서** 실행되는 것을 전제 — 그곳 `CLAUDE.md`(schema)가 자동 로드되어 증류 규약을 제공한다.

## 절차

### 0. config 확인 / 첫 실행 스캐폴딩

1. `~/.claude/lore-wiki/config.json` 존재 확인.
2. **없으면 첫 실행**:
   - 사용자에게 **출력 디렉토리(위키 저장 위치)** 를 묻는다.
   - `${CLAUDE_PLUGIN_ROOT}/config.example.json` 을 복사해 `output_dir` 를 채운 `~/.claude/lore-wiki/config.json` 작성. (`session_root`·`include` 등은 기본값 유지, 사용자가 조정 원하면 안내)
   - 출력 디렉토리에 스캐폴딩: `${CLAUDE_PLUGIN_ROOT}/templates/schema.CLAUDE.md` → `<output_dir>/CLAUDE.md` 복사, 빈 `<output_dir>/index.md`·`<output_dir>/log.md` 생성. (이미 있으면 덮어쓰지 않음)
3. config 의 `output_dir` 가 비었거나 경로가 없으면 명확히 에러 보고 후 중단(파괴적 동작 금지).

### 1. 선별 (결정적)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/select.py --config ~/.claude/lore-wiki/config.json
```
- stdout 마지막 줄 = `run_dir`. `<run_dir>/manifest.json` 을 읽는다.
- `manifest.units` 가 비었으면 **"위키 최신 — ingest 할 새 세션 없음"** 보고 후 종료.

### 2. 유닛 루프 (각 unit)

`manifest.units` 를 순서대로:

1. `<run_dir>/<unit.file>` 를 Read. (세션 헤더 + 증류용 텍스트)
2. **증류** — 출력 디렉토리 `CLAUDE.md`(schema) 규약을 따른다:
   - `index.md` 를 읽어 관련 기존 페이지를 찾는다.
   - 같은 사실/엔티티/결정/해법이 기존 페이지에 있으면 **그 페이지에 병합**(read-modify-write). 없으면 schema 의 페이지 타입·네이밍·frontmatter 규약대로 신규 생성.
   - 새 페이지 생성 시 `index.md` 갱신(카테고리별 링크 + 한 줄 요약).
   - frontmatter 의 provenance 에 `unit.sessions[*]` 의 `sessionId`·`lastTimestamp` 를 기록.
3. **`log.md` append** — schema 의 log 포맷(일관 prefix)으로 한 항목: 어느 세션(들)에서 어느 페이지를 만들었/갱신했는지 + provenance.
4. **커서 커밋** (결정적):
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/commit_cursor.py \
     --config ~/.claude/lore-wiki/config.json \
     --manifest <run_dir>/manifest.json --unit <unit.unit_id>
   ```

### 3. 정리 / 보고

- 처리한 유닛 수·생성/갱신 페이지 수·스캔/스킵 세션 수를 요약 보고.
- (선택) `run_dir` 정리. 다음 실행이 어차피 덮어쓰므로 실패해도 무방.

## 원칙

- **결정적 경계 침범 금지**: 파일 선별·증분·커서 갱신은 헬퍼에 위임. 이 명령은 증류·병합·log 작성만.
- **병합 우선(dedup)**: 같은 지식의 중복 페이지를 만들지 않는다. 항상 `index.md` → 기존 페이지 확인 후 병합.
- **schema 준수**: 페이지 타입·네이밍·링크·frontmatter 는 출력 디렉토리 `CLAUDE.md` 를 단일 출처로 삼는다.
````

- [ ] **Step 2: frontmatter·핵심 절차 존재 검증**

Run:
```bash
python3 - <<'PY'
t = open("commands/lore-wiki.md", encoding="utf-8").read()
assert t.startswith("---"), "frontmatter 누락"
for kw in ["select.py", "commit_cursor.py", "manifest.json",
           "첫 실행", "유닛 루프", "log.md", "병합"]:
    assert kw in t, "누락: " + kw
print("OK")
PY
```
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add commands/lore-wiki.md
git commit -m "command: /lore-wiki ingest 오케스트레이션 작성"
```

---

## Task 13: 시드 schema (`templates/schema.CLAUDE.md`)

**Files:**
- Create: `templates/schema.CLAUDE.md`

스캐폴딩 시 출력 디렉토리로 복사되는 최소 골격. 사용자가 쓰면서 고쳐나간다.

- [ ] **Step 1: 시드 schema 작성**

`templates/schema.CLAUDE.md`:
````markdown
# Lore Wiki Schema

> 이 파일은 위키의 **규약(schema)** 이다. `/lore-wiki ingest` 가 이 디렉토리에서 실행될 때
> 자동 로드되어 증류 규칙을 제공한다. **최소 시드** 상태이며, 쓰면서 본인 도메인에 맞게
> 자유롭게 고쳐나가라(co-development).

## 페이지 타입 (3종)

- **entity** — 도메인 사실. 시스템·API·개념·용어 등 "무엇"에 대한 지속적 사실.
  예: `wafl-console`, `screenpop-api`.
- **decision** — 결정과 근거. "왜 X 대신 Y 를 골랐나" + 검토한 대안.
- **how-to** — 해법/절차. "X 문제 → Y 절차로 해결".

## 네이밍

- 파일명: `kebab-case.md` (소문자, 공백→하이픈).
- 타입은 frontmatter `type` 으로 구분(접두사 불필요). 충돌 시 짧은 한정어 추가.

## frontmatter (필수 필드)

```yaml
---
type: entity        # entity | decision | how-to
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
sessions:           # provenance — 이 지식이 나온 세션
  - { sessionId: "...", timestamp: "..." }
---
```

## index.md

콘텐츠 카탈로그. 카테고리(Entities / Decisions / How-tos)별로:
- `- [[페이지]] — 한 줄 요약` (wikilink off 면 `- [한 줄 요약](상대경로.md)`).

## log.md

append-only 이력. 항목마다 일관 prefix:
```
## [YYYY-MM-DD] ingest | <요지>
- sessions: <sessionId> (<timestamp>)
- pages: [[페이지A]] 생성, [[페이지B]] 갱신
```

## 링크 규약

- config `wikilink: true` → `[[페이지]]`. `false` → 표준 상대경로 md 링크.
- 페이지 간 상호참조를 적극적으로 건다(관련 entity/decision/how-to).

## 증류 지침 (채워나갈 영역)

> 아래는 출발점 가이드. 본인 세션 패턴에 맞게 구체화하라.

- **세그멘테이션**: 한 세션에서 여러 지식 단위가 나올 수 있다. Q→A 흐름·주제 전환을 경계로 본다.
- **dedup/병합**: 같은 사실이 여러 세션에 나오면 기존 페이지에 병합. 중복 페이지 금지.
- **노이즈 필터**: 삽질·왕복·실패한 시도에서 *결과적으로 통한 지식*만 남긴다.
- **무엇을 남길까**: 도메인 사실·결정 근거·해법. 일회성 잡담·진행 로그는 제외.
````

- [ ] **Step 2: 검증**

Run:
```bash
python3 - <<'PY'
t = open("templates/schema.CLAUDE.md", encoding="utf-8").read()
for kw in ["entity", "decision", "how-to", "frontmatter", "sessions",
           "index.md", "log.md", "wikilink", "dedup"]:
    assert kw in t, "누락: " + kw
print("OK")
PY
```
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add templates/schema.CLAUDE.md
git commit -m "template: 최소 시드 schema(CLAUDE.md) 작성"
```

---

## Task 14: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: README 작성**

`README.md`:
````markdown
# Lore Wiki

Claude Code 대화 세션(JSONL)을 LLM 으로 증류해, 지속 누적·갱신되는 **마크다운 지식 위키**로
쌓는 Claude Code 플러그인. [Karpathy 의 LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
모델을 차용했다.

- **Raw sources**: `~/.claude/projects/**/*.jsonl` (불변, 읽기만)
- **Wiki**: 출력 디렉토리의 entity/decision/how-to 페이지 + `index.md` + `log.md`
- **Schema**: 출력 디렉토리의 `CLAUDE.md` (규약 — 쓰면서 공동 진화)

현재 범위는 **ingest** 연산. `query`·`lint` 는 후속.

## 설치

Claude Code 플러그인으로 이 디렉토리를 등록한다(플러그인 매니페스트: `.claude-plugin/plugin.json`).
명령 `/lore-wiki` 가 추가된다.

요구사항: **Python 3.9+** (외부 의존 없음 — stdlib 만 사용).

## 설정

`config.example.json` 을 `~/.claude/lore-wiki/config.json` 으로 복사해 편집한다.
(첫 실행 시 `/lore-wiki` 가 출력 디렉토리를 물어 자동 생성도 해 준다.)

| 키 | 기본값 | 의미 |
|---|---|---|
| `session_root` | `~/.claude/projects` | 세션 JSONL 루트 |
| `output_dir` | (필수) | 위키 md 저장 위치 |
| `include` / `exclude` | `["*"]` / `[]` | 세션 `cwd` 기준 프로젝트 glob 필터 |
| `cursor_path` | `~/.claude/lore-wiki/cursor.json` | 증분 커서(출력 dir 밖 — git 노이즈 회피) |
| `obsidian` | `false` | Obsidian vault 전용 기능 사용 |
| `wikilink` | `false` | `[[..]]` wikilink vs 표준 md 링크 |
| `batch_max_bytes` | `40000` | 소형 세션 묶음 유닛 cap(추출 바이트) |

다중 위키는 `--config <경로>` 로 분리(각각 `cursor_path` 도 다르게).

## 사용

위키 디렉토리(`output_dir`)에서:

```
/lore-wiki            # = /lore-wiki ingest
/lore-wiki ingest     # 새 세션 증분 ingest
```

## 동작 개요

```
select.py (결정적): 파일 나열 → stat 비교 → byteOffset 증분 → 신호 추출 → 유닛 bin-packing
        → run_dir/{manifest.json, unit-NN.md}
명령 (LLM): 유닛별 증류 → index.md 로 기존 페이지 찾아 병합/신규 → log.md → commit_cursor.py
commit_cursor.py (결정적): 유닛 단위 cursor.json 갱신
```

증류 *규약*(페이지 타입·네이밍·dedup·세그멘테이션)은 코드가 아니라 출력 디렉토리
`CLAUDE.md`(schema)에 prose 로 정의되며, 쓰면서 공동 진화한다.

## 테스트

```bash
python3 tests/test_select.py -v
python3 tests/test_commit_cursor.py -v
```
````

- [ ] **Step 2: 검증**

Run:
```bash
python3 - <<'PY'
t = open("README.md", encoding="utf-8").read()
for kw in ["설치", "설정", "사용", "config.example.json", "Python 3.9",
           "select.py", "commit_cursor.py"]:
    assert kw in t, "누락: " + kw
print("OK")
PY
```
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add README.md
git commit -m "docs: README(설치·설정·사용·동작 개요) 작성"
```

---

## Task 15: end-to-end 수동 스모크 (LLM 증류 검증)

자동 단위테스트로 못 잡는 LLM 증류 흐름을 실제 세션으로 검증한다. (스펙 §8)

**Files:** 없음(수동 검증 + 결과 기록).

- [ ] **Step 1: 임시 위키 디렉토리 준비**

```bash
mkdir -p /tmp/lore-smoke
```

- [ ] **Step 2: 첫 실행 스캐폴딩 확인**

`/tmp/lore-smoke` 에서 `/lore-wiki` 실행. 출력 디렉토리를 `/tmp/lore-smoke` 로 지정.
- 기대: `~/.claude/lore-wiki/config.json` 생성, `/tmp/lore-smoke/{CLAUDE.md, index.md, log.md}` 생성.
- 확인:
  ```bash
  ls -la /tmp/lore-smoke
  cat ~/.claude/lore-wiki/config.json
  ```

- [ ] **Step 3: 1회 ingest 산출물 확인**

같은 위치에서 `/lore-wiki ingest` 실행.
- 기대: 하나 이상의 entity/decision/how-to 페이지 생성, `index.md` 갱신, `log.md` 항목 append, `cursor.json` 작성.
- 확인:
  ```bash
  ls /tmp/lore-smoke
  cat /tmp/lore-smoke/index.md
  cat /tmp/lore-smoke/log.md
  python3 -c "import json; c=json.load(open('$HOME/.claude/lore-wiki/cursor.json')); print('sessions:', len(c['sessions']), 'lastRun:', c['lastRun'])"
  ```
- 페이지 frontmatter 에 `sessions` provenance 가 들어갔는지 육안 확인.

- [ ] **Step 4: 재실행 skip/dedup 확인**

곧바로 `/lore-wiki ingest` 재실행.
- 기대: 대부분 세션 skip("위키 최신" 또는 소수 유닛만), 같은 지식의 **중복 페이지가 새로 생기지 않음**(기존 페이지 병합).
- 확인: `index.md` 페이지 수가 폭증하지 않는지, `git diff`(위키가 git 이면) 또는 파일 수 비교.

- [ ] **Step 5: 헬퍼 회귀 테스트 통과 재확인**

```bash
python3 tests/test_select.py && python3 tests/test_commit_cursor.py && echo ALL-OK
```
Expected: `ALL-OK`

- [ ] **Step 6: 스모크 결과를 커밋 메시지/노트로 기록**

이상 동작이 있으면 이슈로 적고, 정상이면 마무리. (코드 변경 없으면 커밋 불필요.)

---

## 완료 기준

- [ ] `python3 tests/test_select.py` 통과 (13 tests)
- [ ] `python3 tests/test_commit_cursor.py` 통과 (3 tests)
- [ ] 플러그인 구조 완비: `.claude-plugin/plugin.json`, `commands/lore-wiki.md`, `scripts/{select,commit_cursor}.py`, `templates/schema.CLAUDE.md`, `config.example.json`, `README.md`
- [ ] 수동 스모크(Task 15): 첫실행 스캐폴딩 → ingest 산출 → 재실행 dedup/skip 정상
