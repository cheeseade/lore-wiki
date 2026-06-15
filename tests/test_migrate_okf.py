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
