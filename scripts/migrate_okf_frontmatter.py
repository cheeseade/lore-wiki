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
