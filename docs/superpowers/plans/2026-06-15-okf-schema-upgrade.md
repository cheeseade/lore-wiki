# OKF v0.1 스키마 격상 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** lore-wiki 내부 스키마를 OKF v0.1 스펙에 맞춰 격상한다 — frontmatter 에 `title`·`description`·`timestamp` 추가, 스키마·명령 문서 갱신, 기존 269개 페이지 결정적 백필.

**Architecture:** 페이지 frontmatter 백필은 신규 stdlib 스크립트 `scripts/migrate_okf_frontmatter.py`(결정적·idempotent)가 담당한다 — `title`은 본문 H1, `description`은 `index.md` 의 한 줄 요약, `timestamp`는 기존 `updated` 값에서 결정적으로 도출. 스키마 규약은 시드(`templates/schema.CLAUDE.md`)와 실제 위키 `CLAUDE.md` 두 곳의 prose 문서를 OKF 계보 명시로 갱신. `select.py`·`commit_cursor.py`는 페이지 frontmatter 를 쓰지 않으므로 무변경.

**Tech Stack:** Python 3.9+ stdlib only (argparse·json·os·re·sys), `unittest`, `tests/loader.py` 모듈 로더. 마크다운 + YAML frontmatter.

**Spec:** `docs/superpowers/specs/2026-06-15-okf-schema-upgrade-design.md`

---

## 커밋 규약

- 커밋 메시지는 **한글**. 각 커밋 끝에 다음 트레일러를 붙인다(빈 줄 뒤):
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- 아래 Step 의 `git commit -m "..."` 는 요지만 표기 — 실제 커밋 시 위 트레일러 포함.

## frontmatter 필드 (격상 후)

```yaml
---
type: entity        # OKF 표준(필수) — lore-wiki 어휘 enum
title: "..."        # OKF 표준 — 사람용 이름 (본문 H1)
description: "..."  # OKF 표준 — 한 줄 요약 (index.md 정본)
tags: [...]         # OKF 표준
created: 2026-06-01 # lore-wiki 확장 (최초 생성일)
updated: 2026-06-01 # lore-wiki 확장 (최종 수정일, 사람용)
timestamp: 2026-06-01  # OKF 표준 — updated 값 미러링(최종 수정)
sessions:           # lore-wiki 확장 — 세션 provenance
  - { sessionId: "...", timestamp: "..." }
---
```

마이그레이션은 누락된 `title`·`description`·`timestamp` 만 삽입한다. `title`·`description` 은 `type` 라인 아래에(자유 텍스트 → 큰따옴표 인용), `timestamp` 는 `updated` 라인 아래에(날짜 스칼라 → 인용 없음, 값은 `updated` 미러링).

## File Structure

- **Create** `scripts/migrate_okf_frontmatter.py` — 기존 페이지 frontmatter 에 `title`·`description`·`timestamp` 백필하는 결정적 일회성 마이그레이션. 순수 함수(파싱·추출·주입) + `main`(config 읽기·디렉토리 순회·dry-run·기록).
- **Create** `tests/test_migrate_okf.py` — 위 스크립트의 순수 함수 + `main` 테스트.
- **Modify** `templates/schema.CLAUDE.md` — frontmatter 섹션 교체 + "OKF 계보" 단락 추가.
- **Modify** `commands/lore-wiki.md` — 증류 2단계에 `title`/`description`/`timestamp`·index DRY 반영.
- **Modify** `README.md` — 스키마가 OKF v0.1 기반임을 한 줄 명시.
- **Modify (repo 밖)** `/Users/gglee/workspace/obsidian/지식위키/CLAUDE.md` — frontmatter 섹션 교체 + "OKF 계보" 추가, "나무위키식 구조" 진화분 보존.
- **Execute** dry-run → 검토 → 실제 위키 269개 백필.

---

## Task 1: 스크립트 스캐폴딩 + frontmatter 분해·키·값 추출

**Files:**
- Create: `scripts/migrate_okf_frontmatter.py`
- Test: `tests/test_migrate_okf.py`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate_okf.py`:

```python
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from loader import load

mig = load("lore_migrate_okf", "migrate_okf_frontmatter.py")

PAGE = (
    "---\n"
    "type: entity\n"
    "tags: [a, b]\n"
    "created: 2026-06-01\n"
    "updated: 2026-06-02\n"
    "sessions:\n"
    '  - { sessionId: "S1", timestamp: "T1" }\n'
    "---\n"
    "# My Page Title\n"
    "## 1. 개요\n"
    "본문.\n"
)


class TestFrontmatter(unittest.TestCase):
    def test_split_frontmatter(self):
        fm_lines, body = mig.split_frontmatter(PAGE)
        self.assertEqual(fm_lines[0], "type: entity")
        self.assertTrue(body.startswith("# My Page Title"))

    def test_split_no_frontmatter(self):
        fm_lines, body = mig.split_frontmatter("# 그냥 본문\n")
        self.assertIsNone(fm_lines)
        self.assertEqual(body, "# 그냥 본문\n")

    def test_frontmatter_keys(self):
        fm_lines, _ = mig.split_frontmatter(PAGE)
        keys = mig.frontmatter_keys(fm_lines)
        self.assertEqual(
            keys, {"type", "tags", "created", "updated", "sessions"})
        self.assertNotIn("sessionId", keys)  # 들여쓴 '- { ... }' 는 키 아님

    def test_frontmatter_value(self):
        fm_lines, _ = mig.split_frontmatter(PAGE)
        self.assertEqual(mig.frontmatter_value(fm_lines, "updated"),
                         "2026-06-02")
        self.assertIsNone(mig.frontmatter_value(fm_lines, "nope"))
        self.assertIsNone(mig.frontmatter_value(fm_lines, "sessions"))  # 값 없음


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: FAIL — `migrate_okf_frontmatter.py` 없음 (import 에러).

- [ ] **Step 3: Write minimal implementation**

`scripts/migrate_okf_frontmatter.py`:

```python
"""Lore Wiki — OKF v0.1 격상 마이그레이션: 기존 페이지 frontmatter 에 title·description·timestamp 백필.

결정적·idempotent. stdlib only.
- title       ← 본문 첫 H1
- description ← index.md 의 해당 페이지 한 줄 요약
- timestamp   ← 기존 updated 값 미러링 (OKF 표준 필드)
"""
import argparse
import json
import os
import re
import sys

SKIP_FILES = {"index.md", "log.md", "CLAUDE.md"}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def split_frontmatter(text):
    """(frontmatter_lines, body) 반환. frontmatter 없으면 (None, text)."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text
    fm = text[4:end]
    body = text[end + len("\n---\n"):]
    return fm.split("\n"), body


def frontmatter_keys(fm_lines):
    """frontmatter 의 최상위 키 집합(들여쓴 줄·리스트 항목 제외)."""
    keys = set()
    for line in fm_lines:
        m = re.match(r"^([A-Za-z][\w-]*):", line)
        if m:
            keys.add(m.group(1))
    return keys


def frontmatter_value(fm_lines, key):
    """frontmatter 최상위 key 의 스칼라 값(없거나 빈 값이면 None)."""
    pat = re.compile(r"^%s:\s*(.*?)\s*$" % re.escape(key))
    for line in fm_lines:
        m = pat.match(line)
        if m:
            return m.group(1) or None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_okf_frontmatter.py tests/test_migrate_okf.py
git commit -m "migrate_okf: frontmatter 분해·키·값 추출 + 테스트"
```

---

## Task 2: title 추출 + 파일명 휴머나이즈

**Files:**
- Modify: `scripts/migrate_okf_frontmatter.py`
- Test: `tests/test_migrate_okf.py`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate_okf.py` 에 클래스 추가:

```python
class TestTitle(unittest.TestCase):
    def test_extract_title(self):
        self.assertEqual(mig.extract_title("# My Page Title\n본문"),
                         "My Page Title")

    def test_extract_title_with_backticks(self):
        body = "# Anthropic `401 invalid x-api-key` 진단 (키 없음 vs 거부됨)\n"
        self.assertEqual(
            mig.extract_title(body),
            "Anthropic `401 invalid x-api-key` 진단 (키 없음 vs 거부됨)")

    def test_extract_title_none(self):
        self.assertIsNone(mig.extract_title("## 소제목만\n본문"))

    def test_humanize_filename(self):
        self.assertEqual(mig.humanize_filename("cart-fifo-차감.md"),
                         "cart fifo 차감")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: FAIL — `has no attribute 'extract_title'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/migrate_okf_frontmatter.py` 의 `frontmatter_value` 아래에 추가:

```python
def extract_title(body):
    """본문 첫 H1('# ...') 텍스트. 없으면 None."""
    for line in body.split("\n"):
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1)
    return None


def humanize_filename(basename):
    """'a-b-c.md' → 'a b c' (H1 부재 시 title 폴백용)."""
    stem = basename[:-3] if basename.endswith(".md") else basename
    return stem.replace("-", " ")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_okf_frontmatter.py tests/test_migrate_okf.py
git commit -m "migrate_okf: H1 title 추출·파일명 폴백 + 테스트"
```

---

## Task 3: index.md 파싱 (description 소스)

**Files:**
- Modify: `scripts/migrate_okf_frontmatter.py`
- Test: `tests/test_migrate_okf.py`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate_okf.py` 에 추가:

```python
class TestParseIndex(unittest.TestCase):
    def test_wikilink(self):
        idx = (
            "# Index\n\n## Entities\n\n"
            "- [[2026-screenpop-api]] — 삼성 ScreenPOP 백엔드, Transaction Script\n"
            "- [[wafl-rise2]] — WAFL 차세대 RAG 엔진\n"
        )
        out = mig.parse_index(idx, wikilink=True)
        self.assertEqual(out["2026-screenpop-api"],
                         "삼성 ScreenPOP 백엔드, Transaction Script")
        self.assertEqual(out["wafl-rise2"], "WAFL 차세대 RAG 엔진")

    def test_non_wikilink(self):
        idx = "- [삼성 ScreenPOP 백엔드](2026-screenpop-api.md)\n"
        out = mig.parse_index(idx, wikilink=False)
        self.assertEqual(out["2026-screenpop-api"], "삼성 ScreenPOP 백엔드")

    def test_no_match_line_ignored(self):
        out = mig.parse_index("## Entities\n일반 문장\n", wikilink=True)
        self.assertEqual(out, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: FAIL — `has no attribute 'parse_index'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/migrate_okf_frontmatter.py` 에 추가:

```python
def parse_index(index_text, wikilink):
    """index.md → {page_key: description}. page_key = basename(.md 제외)."""
    out = {}
    if wikilink:
        pat = re.compile(r"\[\[([^\]]+?)\]\]\s*—\s*(.+?)\s*$")
        for line in index_text.split("\n"):
            m = pat.search(line)
            if m:
                key = m.group(1).split("/")[-1]
                if key.endswith(".md"):
                    key = key[:-3]
                out[key] = m.group(2)
    else:
        pat = re.compile(r"\[([^\]]+?)\]\(([^)]+?\.md)\)")
        for line in index_text.split("\n"):
            m = pat.search(line)
            if m:
                key = os.path.basename(m.group(2))[:-3]
                out[key] = m.group(1)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_okf_frontmatter.py tests/test_migrate_okf.py
git commit -m "migrate_okf: index.md 요약 파싱(wikilink on/off) + 테스트"
```

---

## Task 4: YAML 인용 + 필드 주입 (title·description·timestamp)

**Files:**
- Modify: `scripts/migrate_okf_frontmatter.py`
- Test: `tests/test_migrate_okf.py`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate_okf.py` 에 추가:

```python
class TestInject(unittest.TestCase):
    def test_yaml_dquote_plain(self):
        self.assertEqual(mig.yaml_dquote("간단 요약"), '"간단 요약"')

    def test_yaml_dquote_escapes(self):
        self.assertEqual(mig.yaml_dquote('경로 C:\\x "인용"'),
                         '"경로 C:\\\\x \\"인용\\""')

    def test_inject_title_description_after_type(self):
        fm = ["type: entity", "tags: [a]"]
        out, changed = mig.inject_fields(fm, "제목", "요약", None)
        self.assertTrue(changed)
        self.assertEqual(out, [
            "type: entity", 'title: "제목"', 'description: "요약"', "tags: [a]"])

    def test_inject_timestamp_after_updated(self):
        fm = ["type: entity", "updated: 2026-06-01", "sessions:"]
        out, changed = mig.inject_fields(fm, None, None, "2026-06-01")
        self.assertTrue(changed)
        self.assertEqual(out, [
            "type: entity", "updated: 2026-06-01",
            "timestamp: 2026-06-01", "sessions:"])

    def test_inject_all_three(self):
        fm = ["type: entity", "updated: 2026-06-02"]
        out, changed = mig.inject_fields(fm, "T", "D", "2026-06-02")
        self.assertTrue(changed)
        self.assertEqual(out, [
            "type: entity", 'title: "T"', 'description: "D"',
            "updated: 2026-06-02", "timestamp: 2026-06-02"])

    def test_inject_idempotent_when_all_present(self):
        fm = ["type: entity", 'title: "T"', 'description: "D"',
              "updated: 2026-06-01", "timestamp: 2026-06-01"]
        out, changed = mig.inject_fields(fm, "새", "새요약", "2026-06-01")
        self.assertFalse(changed)
        self.assertEqual(out, fm)

    def test_inject_skips_none_values(self):
        fm = ["type: entity"]
        out, changed = mig.inject_fields(fm, "제목", None, None)
        self.assertTrue(changed)
        self.assertEqual(out, ["type: entity", 'title: "제목"'])

    def test_rebuild_roundtrip(self):
        fm_lines, body = mig.split_frontmatter(PAGE)
        self.assertEqual(mig.rebuild(fm_lines, body), PAGE)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: FAIL — `has no attribute 'yaml_dquote'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/migrate_okf_frontmatter.py` 에 추가:

```python
def yaml_dquote(value):
    """double-quoted YAML 스칼라로 인용(역슬래시·따옴표 이스케이프)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped


def _insert_after(lines, anchor_key, new_lines):
    """anchor_key 최상위 라인 바로 뒤에 new_lines 삽입. anchor 없으면 맨 앞."""
    idx = None
    for i, line in enumerate(lines):
        if re.match(r"^%s:" % re.escape(anchor_key), line):
            idx = i
            break
    insert_at = (idx + 1) if idx is not None else 0
    return lines[:insert_at] + list(new_lines) + lines[insert_at:]


def inject_fields(fm_lines, title, description, timestamp):
    """누락된 OKF 필드 삽입.

    - title·description: `type` 라인 아래 (자유 텍스트 → 큰따옴표 인용)
    - timestamp: `updated` 라인 아래 (날짜 스칼라 → 인용 없음)
    이미 있는 필드는 건드리지 않는다. 반환: (new_fm_lines, changed).
    """
    keys = frontmatter_keys(fm_lines)
    lines = list(fm_lines)
    changed = False
    head = []
    if "title" not in keys and title is not None:
        head.append("title: %s" % yaml_dquote(title))
    if "description" not in keys and description is not None:
        head.append("description: %s" % yaml_dquote(description))
    if head:
        lines = _insert_after(lines, "type", head)
        changed = True
    if "timestamp" not in keys and timestamp is not None:
        lines = _insert_after(lines, "updated", ["timestamp: %s" % timestamp])
        changed = True
    return lines, changed


def rebuild(fm_lines, body):
    """frontmatter 라인 + 본문 → 원본 텍스트 형태로 합성."""
    return "---\n" + "\n".join(fm_lines) + "\n---\n" + body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: PASS (19 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_okf_frontmatter.py tests/test_migrate_okf.py
git commit -m "migrate_okf: YAML 인용·필드 주입(title·description·timestamp)·rebuild + 테스트"
```

---

## Task 5: 페이지 처리(process_page) — 합성·idempotent·상태

**Files:**
- Modify: `scripts/migrate_okf_frontmatter.py`
- Test: `tests/test_migrate_okf.py`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate_okf.py` 에 추가:

```python
class TestProcessPage(unittest.TestCase):
    DESCS = {"my-page": "인덱스가 준 요약"}

    def test_updated(self):
        new, status = mig.process_page(PAGE, "my-page.md", self.DESCS)
        self.assertEqual(status, "updated")
        self.assertIn('title: "My Page Title"', new)
        self.assertIn('description: "인덱스가 준 요약"', new)
        self.assertIn("timestamp: 2026-06-02", new)   # updated 값 미러링
        self.assertIn("## 1. 개요", new)               # 본문 보존
        self.assertIn("type: entity", new)             # 기존 필드 보존

    def test_skipped_when_all_present(self):
        already = PAGE.replace(
            "type: entity\n",
            'type: entity\ntitle: "T"\ndescription: "D"\n').replace(
            "updated: 2026-06-02\n",
            "updated: 2026-06-02\ntimestamp: 2026-06-02\n")
        new, status = mig.process_page(already, "my-page.md", self.DESCS)
        self.assertEqual(status, "skipped")
        self.assertEqual(new, already)

    def test_flagged_when_no_index_desc(self):
        new, status = mig.process_page(PAGE, "unknown-page.md", {})
        self.assertEqual(status, "flagged")
        self.assertIn('title: "My Page Title"', new)  # title·timestamp 는 채워짐
        self.assertIn("timestamp: 2026-06-02", new)
        self.assertNotIn("description:", new)          # description 은 비움

    def test_no_frontmatter(self):
        new, status = mig.process_page("# H1만 있음\n본문\n", "x.md", {})
        self.assertEqual(status, "no-frontmatter")
        self.assertEqual(new, "# H1만 있음\n본문\n")

    def test_idempotent_rerun_on_updated(self):
        once, _ = mig.process_page(PAGE, "my-page.md", self.DESCS)
        twice, status = mig.process_page(once, "my-page.md", self.DESCS)
        self.assertEqual(status, "skipped")
        self.assertEqual(twice, once)

    def test_idempotent_rerun_on_flagged(self):
        once, _ = mig.process_page(PAGE, "unknown-page.md", {})
        twice, status = mig.process_page(once, "unknown-page.md", {})
        self.assertEqual(status, "flagged")
        self.assertEqual(twice, once)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: FAIL — `has no attribute 'process_page'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/migrate_okf_frontmatter.py` 에 추가:

```python
def process_page(text, basename, descriptions):
    """페이지 텍스트 → (new_text, status).

    status ∈ updated | skipped | flagged | no-frontmatter.
    flagged = title/timestamp 는 채웠으나 index 요약이 없어 description 미확정.
    """
    fm_lines, body = split_frontmatter(text)
    if fm_lines is None:
        return text, "no-frontmatter"
    keys = frontmatter_keys(fm_lines)
    has_title = "title" in keys
    has_desc = "description" in keys
    has_ts = "timestamp" in keys
    if has_title and has_desc and has_ts:
        return text, "skipped"
    key = basename[:-3] if basename.endswith(".md") else basename
    title = extract_title(body) or humanize_filename(basename)
    description = descriptions.get(key)
    timestamp = frontmatter_value(fm_lines, "updated")
    new_fm, changed = inject_fields(fm_lines, title, description, timestamp)
    new_text = rebuild(new_fm, body) if changed else text
    final_has_desc = has_desc or (description is not None)
    if not final_has_desc:
        return new_text, "flagged"
    return new_text, ("updated" if changed else "skipped")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: PASS (25 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_okf_frontmatter.py tests/test_migrate_okf.py
git commit -m "migrate_okf: process_page 합성·idempotent·상태 분류 + 테스트"
```

---

## Task 6: main() — config 읽기·디렉토리 순회·dry-run·기록

**Files:**
- Modify: `scripts/migrate_okf_frontmatter.py`
- Test: `tests/test_migrate_okf.py`

- [ ] **Step 1: Write the failing test**

`tests/test_migrate_okf.py` 에 추가:

```python
class TestMain(unittest.TestCase):
    def _setup(self, d, wikilink=True):
        out = os.path.join(d, "wiki")
        os.makedirs(out)
        cfg = os.path.join(d, "config.json")
        import json as _j
        with open(cfg, "w", encoding="utf-8") as f:
            _j.dump({"output_dir": out, "wikilink": wikilink}, f)
        with open(os.path.join(out, "index.md"), "w", encoding="utf-8") as f:
            f.write("- [[my-page]] — 인덱스 요약\n")
        with open(os.path.join(out, "my-page.md"), "w", encoding="utf-8") as f:
            f.write(PAGE)
        for skip in ("log.md", "CLAUDE.md"):  # 건드리면 안 되는 파일
            with open(os.path.join(out, skip), "w", encoding="utf-8") as f:
                f.write("# %s\nyo\n" % skip)
        return cfg, out

    def test_main_writes_fields(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, out = self._setup(d)
            rc = mig.main(["--config", cfg])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "my-page.md"), encoding="utf-8") as f:
                txt = f.read()
            self.assertIn('title: "My Page Title"', txt)
            self.assertIn('description: "인덱스 요약"', txt)
            self.assertIn("timestamp: 2026-06-02", txt)
            with open(os.path.join(out, "CLAUDE.md"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "# CLAUDE.md\nyo\n")  # 불변

    def test_main_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, out = self._setup(d)
            rc = mig.main(["--config", cfg, "--dry-run"])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "my-page.md"), encoding="utf-8") as f:
                self.assertEqual(f.read(), PAGE)  # 변경 없음

    def test_main_missing_output_dir_errors(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("{}")
            with self.assertRaises(SystemExit):
                mig.main(["--config", cfg])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: FAIL — `has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

`scripts/migrate_okf_frontmatter.py` 끝에 추가:

```python
def main(argv=None):
    p = argparse.ArgumentParser(description="Lore Wiki OKF frontmatter 백필")
    p.add_argument("--config", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    cfg = load_json(os.path.expanduser(args.config), {})
    output_dir = cfg.get("output_dir")
    if not output_dir:
        raise SystemExit("config 에 output_dir 없음")
    output_dir = os.path.expanduser(output_dir)
    if not os.path.isdir(output_dir):
        raise SystemExit("output_dir 디렉토리 없음: %s" % output_dir)
    wikilink = bool(cfg.get("wikilink", False))

    index_text = ""
    index_path = os.path.join(output_dir, "index.md")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index_text = f.read()
    descriptions = parse_index(index_text, wikilink)

    counts = {"updated": 0, "skipped": 0, "flagged": 0, "no-frontmatter": 0}
    flagged = []
    for name in sorted(os.listdir(output_dir)):
        if not name.endswith(".md") or name in SKIP_FILES:
            continue
        path = os.path.join(output_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        new_text, status = process_page(text, name, descriptions)
        counts[status] = counts.get(status, 0) + 1
        if status in ("flagged", "no-frontmatter"):
            flagged.append("%s (%s)" % (name, status))
        if not args.dry_run and new_text != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)

    mode = "[dry-run] " if args.dry_run else ""
    print("%s백필 완료: updated=%d skipped=%d flagged=%d no-fm=%d" % (
        mode, counts["updated"], counts["skipped"], counts["flagged"],
        counts["no-frontmatter"]))
    for item in flagged:
        print("FLAG: %s" % item, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/test_migrate_okf.py -v`
Expected: PASS (28 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_okf_frontmatter.py tests/test_migrate_okf.py
git commit -m "migrate_okf: main(config·순회·dry-run·기록·플래그) + 테스트"
```

---

## Task 7: 시드 스키마 문서 격상 (`templates/schema.CLAUDE.md`)

**Files:**
- Modify: `templates/schema.CLAUDE.md`

- [ ] **Step 1: frontmatter 섹션 교체**

`templates/schema.CLAUDE.md` 에서 아래 블록(현재 `## frontmatter (필수 필드)` ~ 닫는 ```` ``` ````)을:

```markdown
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
```

다음으로 교체:

```markdown
## frontmatter (필수 필드)

```yaml
---
type: entity        # entity | decision | how-to  (lore-wiki 어휘 — OKF "type 필수" 원칙)
title: ...          # 사람용 이름 (페이지 H1 과 일치)
description: ...    # 한 줄 요약 — index.md 항목의 정본 (단일 출처)
tags: []
created: YYYY-MM-DD    # 최초 생성일 (lore-wiki 확장)
updated: YYYY-MM-DD    # 최종 수정일 (사람용, lore-wiki 확장)
timestamp: YYYY-MM-DD  # OKF 표준 — updated 값 미러링(최종 수정)
sessions:             # provenance — 이 지식이 나온 세션 (lore-wiki 확장)
  - { sessionId: "...", timestamp: "..." }
---
```
```

- [ ] **Step 2: "OKF 계보" 단락 삽입**

위 frontmatter 섹션 바로 뒤(`## index.md` 섹션 앞)에 삽입:

```markdown
## OKF 계보

이 스키마는 [Open Knowledge Format (OKF) v0.1](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/) 기반이다.
OKF 의 구조 원칙 — 마크다운+YAML frontmatter, 파일 경로 = 개념 정체성, `index.md`(카탈로그)·`log.md`(이력),
페이지 간 링크 = 지식 그래프 — 을 그대로 따른다. frontmatter 필드는 두 갈래:

| 필드 | 구분 |
|---|---|
| `type` · `title` · `description` · `tags` · `timestamp` | OKF 표준 |
| `created` · `updated` · `sessions` | lore-wiki 확장 (`updated` 는 `timestamp` 와 값 동일) |

`type` 은 OKF 에선 자유 문자열이나 lore-wiki 는 `entity|decision|how-to` enum 으로 좁혀 쓴다.
`timestamp`(OKF 표준 최종수정 필드)는 `updated` 와 값이 같고, OKF 도구 호환을 위해 별도로 둔다.
```

- [ ] **Step 3: 검증**

Run: `sed -n '/## frontmatter/,/^## index.md/p' templates/schema.CLAUDE.md`
Expected: frontmatter 에 `title`·`description`·`timestamp` 포함, 뒤에 "## OKF 계보" 표 존재.

- [ ] **Step 4: Commit**

```bash
git add templates/schema.CLAUDE.md
git commit -m "template schema: frontmatter title·description·timestamp 추가 + OKF 계보 명시"
```

---

## Task 8: 증류 명령 문서 갱신 (`commands/lore-wiki.md`)

**Files:**
- Modify: `commands/lore-wiki.md`

- [ ] **Step 1: 2단계 증류 지침 교체**

`commands/lore-wiki.md` 의 `### 2. 유닛 루프` → 2번 항목에서 아래 두 줄을:

```markdown
   - 새 페이지 생성 시 `<output_dir>/index.md` 갱신(카테고리별 링크 + 한 줄 요약).
   - frontmatter 의 provenance 에 `unit.sessions[*]` 의 `sessionId`·`lastTimestamp` 를 기록.
```

다음으로 교체:

```markdown
   - frontmatter 필수 필드를 채운다: `type`·`title`(본문 H1 과 일치)·`description`(한 줄 요약)·`tags`·`created`·`updated`·`timestamp`(OKF 표준, `updated` 값 미러링). provenance 는 `sessions` 에 `unit.sessions[*]` 의 `sessionId`·`lastTimestamp` 를 기록.
   - 새/갱신 페이지를 `<output_dir>/index.md` 에 반영하되, **index 항목의 한 줄 요약은 그 페이지 frontmatter 의 `description` 과 동일하게** 한다(단일 출처).
```

- [ ] **Step 2: 검증**

Run: `grep -n "description\|timestamp" commands/lore-wiki.md`
Expected: 2단계에 `description`·`timestamp`·"단일 출처" 언급이 보인다.

- [ ] **Step 3: Commit**

```bash
git add commands/lore-wiki.md
git commit -m "command: 증류 2단계에 title·description·timestamp·index DRY 반영"
```

---

## Task 9: 실제 위키 스키마 + README 갱신

**Files:**
- Modify (repo 밖): `/Users/gglee/workspace/obsidian/지식위키/CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: 실제 위키 frontmatter 섹션 교체**

`/Users/gglee/workspace/obsidian/지식위키/CLAUDE.md` 의 frontmatter 섹션은 시드와 **동일한 텍스트**(현재 `## frontmatter (필수 필드)` ~ 닫는 ```` ``` ````)이다. Task 7 Step 1 과 **같은 old→new 교체**를 적용한다.

- [ ] **Step 2: "OKF 계보" 단락 삽입 (진화분 보존)**

`## index.md` 섹션 앞에 Task 7 Step 2 의 "## OKF 계보" 단락을 동일하게 삽입한다. **이 파일의 "## 문서 스타일 (나무위키식 구조형)"·"### 타입별 권장 구조"·"## 증류 지침" 섹션은 그대로 둔다(삭제·수정 금지).**

- [ ] **Step 3: 실제 위키 검증**

Run: `grep -n "OKF\|title\|description\|timestamp" "/Users/gglee/workspace/obsidian/지식위키/CLAUDE.md" && grep -c "나무위키식 구조형" "/Users/gglee/workspace/obsidian/지식위키/CLAUDE.md"`
Expected: frontmatter 에 `title`·`description`·`timestamp`, "## OKF 계보" 존재. 마지막 줄 출력 `1`(나무위키 섹션 보존됨).

- [ ] **Step 4: README 한 줄 갱신**

`README.md` 의 다음 줄을:

```markdown
- **Schema**: 출력 디렉토리의 `CLAUDE.md` (규약 — 쓰면서 공동 진화)
```

다음으로 교체:

```markdown
- **Schema**: 출력 디렉토리의 `CLAUDE.md` (규약 — [OKF v0.1](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/) 기반, 쓰면서 공동 진화)
```

- [ ] **Step 5: Commit (README 만 — 실제 위키는 별도 vault)**

```bash
git add README.md
git commit -m "docs: README 스키마 설명에 OKF v0.1 기반 명시"
```

실제 위키 `CLAUDE.md` 는 obsidian vault(별도 git)에 속하므로 이 repo 커밋에 포함하지 않는다. vault 쪽에서 별도 커밋하거나 사용자 판단에 맡긴다.

---

## Task 10: 실제 위키 269개 백필 (dry-run → 검토 → 실행)

**Files:**
- Execute only (코드 변경 없음). 대상: `/Users/gglee/workspace/obsidian/지식위키`.

- [ ] **Step 1: 전체 테스트 재확인**

Run: `python3 tests/test_migrate_okf.py -v && python3 tests/test_select.py -v && python3 tests/test_commit_cursor.py -v`
Expected: 전부 PASS (기존 테스트 회귀 없음).

- [ ] **Step 2: dry-run**

Run: `python3 scripts/migrate_okf_frontmatter.py --config ~/.claude/lore-wiki/config.json --dry-run`
Expected: `[dry-run] 백필 완료: updated=269 skipped=0 flagged=0 no-fm=0` 근처. `FLAG:` 행이 있으면 해당 페이지를 확인(없는 게 정상 — 모든 페이지가 index 에 있고 H1 보유).

- [ ] **Step 3: flagged 가 있으면 원인 확인**

flagged 페이지가 보고되면 `grep "페이지명" "/Users/gglee/workspace/obsidian/지식위키/index.md"` 로 index 항목 존재를 확인. 누락이면 index 에 항목을 먼저 보강하거나, description 을 사후 수동 보완(스크립트는 title·timestamp 만 채우고 description 은 비워둠). 0건이면 이 Step 스킵.

- [ ] **Step 4: 실제 백필 실행**

Run: `python3 scripts/migrate_okf_frontmatter.py --config ~/.claude/lore-wiki/config.json`
Expected: `백필 완료: updated=269 ...`.

- [ ] **Step 5: diff 검토 (vault git)**

Run: `cd "/Users/gglee/workspace/obsidian/지식위키" && git diff --stat | tail -5 && git diff -- 2026-screenpop-api.md`
Expected: 페이지마다 `title:`·`description:` 가 `type:` 아래, `timestamp:` 가 `updated:` 아래에 삽입됨. 본문·기존 필드 불변. (vault 가 git 이 아니면 대표 페이지 몇 개를 직접 열어 확인.)

- [ ] **Step 6: idempotent 재실행 확인**

Run: `python3 scripts/migrate_okf_frontmatter.py --config ~/.claude/lore-wiki/config.json`
Expected: `백필 완료: updated=0 skipped=269 ...` (재실행 시 변경 0).

---

## Self-Review (계획 작성자 체크 완료)

- **Spec coverage**: §3 필드(title/description + 신규 timestamp = updated 미러링) → Task 1·4·5·7. §4 스키마 문서(두 갈래 OKF 계보) → Task 7·9. §5 DRY → Task 8. §6 마이그레이션(파싱·title/description/timestamp 도출·삽입 위치·폴백·검증) → Task 1~6·10. §7 변경/무변경 → Task 7·8·9 + select/commit_cursor 무변경 명시. §8 테스트(timestamp 미러링·인용·idempotent·dry-run·wikilink on/off·폴백) → Task 1~6. 누락 없음.
- **Placeholder scan**: 모든 코드 Step 에 완전한 코드·정확한 명령·기대 출력 포함. "TODO/TBD/적절히" 없음. flagged 페이지는 stderr `FLAG:` 행으로 보고(스펙의 추상 표현을 구체 구현으로 확정).
- **Type consistency**: 함수 시그니처 일관 — `split_frontmatter→(fm_lines, body)`, `frontmatter_keys(fm_lines)→set`, `frontmatter_value(fm_lines, key)→str|None`, `inject_fields(fm_lines, title, description, timestamp)→(lines, changed)`, `_insert_after(lines, anchor_key, new_lines)→lines`, `process_page(text, basename, descriptions)→(text, status)`, `parse_index(text, wikilink)→dict`. Task 간 호출 인자·반환 형태 일치. 특히 `inject_fields` 4-인자(timestamp 포함)·`process_page` 가 `frontmatter_value(.., "updated")` 로 timestamp 도출하는 흐름 일관.
