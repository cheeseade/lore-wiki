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
