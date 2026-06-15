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
