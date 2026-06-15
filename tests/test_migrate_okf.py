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


if __name__ == "__main__":
    unittest.main()
