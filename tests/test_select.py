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
