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


class TestMatchCwd(unittest.TestCase):
    def test_include_exclude(self):
        self.assertTrue(sel.match_cwd("/work/app", ["/work/*"], []))
        self.assertFalse(sel.match_cwd("/home/x", ["/work/*"], []))
        self.assertFalse(sel.match_cwd("/work/sandbox", ["/work/*"], ["*/sandbox"]))
        self.assertTrue(sel.match_cwd("/anything", ["*"], []))       # 기본 전체
        self.assertTrue(sel.match_cwd(None, ["*"], []))              # cwd 없음 허용


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

    def test_append_uuid_only_in_body_falls_back(self):
        # lastUuid 문자열이 '본문'에만 있고 uuid 키 값은 아니면 → 오탐 없이 fallback
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "S.jsonl")
            line0 = json.dumps({"type": "user", "uuid": "u1", "parentUuid": None,
                                "timestamp": "T1", "sessionId": "S",
                                "message": {"role": "user",
                                            "content": "GHOST 관련 질문"}})
            with open(p, "w") as f:
                f.write(line0 + "\n")
            off = os.stat(p).st_size
            entry = {"byteOffset": off, "lastUuid": "GHOST",
                     "size": off, "mtime": os.stat(p).st_mtime}
            with open(p, "a") as f:
                f.write(json.dumps({"type": "assistant", "uuid": "a1",
                                    "parentUuid": "u1", "timestamp": "T2",
                                    "message": {"role": "assistant",
                                                "content": [{"type": "text",
                                                             "text": "A1"}]}}) + "\n")
            seg = sel.build_segment(p, "append", entry)
            self.assertTrue(seg["fell_back"])

    def test_append_non_boundary_offset_falls_back(self):
        # offset 이 라인 경계(\n 직후)가 아니면 → fallback
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "S.jsonl")
            with open(p, "w") as f:
                f.write(self._session_lines()[0] + "\n")
            full = os.stat(p).st_size
            entry = {"byteOffset": full - 3, "lastUuid": "u1",
                     "size": full - 3, "mtime": 0}
            with open(p, "a") as f:
                f.write(self._session_lines()[1] + "\n")
            seg = sel.build_segment(p, "append", entry)
            self.assertTrue(seg["fell_back"])

    def test_rescan_reads_all_no_fallback(self):
        # rescan 은 처음부터 전체 재읽기(fell_back=False)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "S.jsonl")
            with open(p, "w") as f:
                f.write("\n".join(self._session_lines()) + "\n")
            entry = {"byteOffset": 5, "lastUuid": "u1", "size": 9999, "mtime": 0}
            seg = sel.build_segment(p, "rescan", entry)
            self.assertFalse(seg["fell_back"])
            self.assertIn("Q1", seg["text"])
            self.assertIn("A1", seg["text"])


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


if __name__ == "__main__":
    unittest.main()
