import json
from pathlib import Path
import runpy
import sqlite3
import sys
import tempfile
import unittest


CONTROL = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/nq-controller"))


class ControllerProtocolTests(unittest.TestCase):
    def test_installed_opencode_text_event(self):
        event = {"type": "text", "sessionID": "ses_test", "part": {"type": "text", "text": "Next task queued.\nORCHESTRATOR_STATE: CONTINUE\n"}}
        self.assertEqual(CONTROL["parse_event"](json.dumps(event)), (event["part"]["text"], None))
        self.assertEqual(CONTROL["STATE_RE"].findall(event["part"]["text"]), ["CONTINUE"])

    def test_error_event_does_not_publish_provider_message(self):
        event = {"type": "error", "error": {"name": "APIError", "data": {"message": "secret provider response"}}}
        self.assertEqual(CONTROL["parse_event"](json.dumps(event)), (None, "APIError"))
        self.assertEqual(CONTROL["parse_event"]("null"), (None, None))
        self.assertEqual(CONTROL["parse_event"]("[]"), (None, None))

    def test_tick_uses_final_text(self):
        event = json.dumps({"type": "text", "part": {"type": "text", "text": "ORCHESTRATOR_STATE: QUIESCENT\n"}})
        command = [sys.executable, "-c", f"import json,sys; sys.stdin.read(); print({event!r})"]
        status, answer, error = CONTROL["run_tick"](command, {}, "tick", 10)
        self.assertEqual((status, error), (0, None))
        self.assertEqual(CONTROL["STATE_RE"].findall(answer), ["QUIESCENT"])

    def test_timeout_kills_child_group_and_marks_tick_failed(self):
        command = [sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(10)"]
        status, answer, error = CONTROL["run_tick"](command, {}, "tick", 1)
        self.assertEqual(status, 124)
        self.assertEqual(answer, "")
        self.assertIn("timeout", error)

    def test_interactive_session_detects_dir_and_resumed_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            proc = root / "proc"
            entry = proc / "123"
            entry.mkdir(parents=True)
            (entry / "cwd").symlink_to(root)
            database = root / "opencode.db"
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE session (id TEXT, directory TEXT)")
                db.execute("INSERT INTO session VALUES (?, ?)", ("ses_test", str(project)))
            (entry / "cmdline").write_bytes(b"opencode\0--dir\0" + str(project).encode() + b"\0")
            self.assertTrue(CONTROL["interactive_nestquest_session"](project, proc, database))
            (entry / "cmdline").write_bytes(b"opencode\0-s\0ses_test\0")
            self.assertTrue(CONTROL["interactive_nestquest_session"](project, proc, database))
            (entry / "cmdline").write_bytes(b"opencode\0--dir\0" + str(root).encode() + b"\0")
            self.assertFalse(CONTROL["interactive_nestquest_session"](project, proc, database))
            with sqlite3.connect(database) as db:
                db.execute("DROP TABLE session")
            (entry / "cmdline").write_bytes(b"opencode\0-s\0ses_test\0")
            with self.assertRaisesRegex(RuntimeError, "lookup failed"):
                CONTROL["interactive_nestquest_session"](project, proc, database)


if __name__ == "__main__":
    unittest.main()
