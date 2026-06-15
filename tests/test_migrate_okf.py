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
