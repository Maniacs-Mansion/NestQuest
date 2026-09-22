from pathlib import Path
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/nq-review"


class ReviewLauncherTests(unittest.TestCase):
    def test_pins_head_and_model_in_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
            (repo / "README").write_text("initial\n")
            subprocess.run(["git", "-C", str(repo), "add", "README"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
            head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            prompt = root / "review.txt"
            prompt.write_text("Review this change.")
            stub = root / "claude"
            stub.write_text("#!/bin/sh\nprintf '%s\\n' \"$PWD\" \"$@\"\n")
            stub.chmod(0o700)
            env = os.environ.copy()
            env["CLAUDE_BIN"] = str(stub)
            result = subprocess.run([str(SCRIPT), str(repo), head, head, str(prompt)], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(repo), result.stdout)
            self.assertIn("--model\nclaude-sonnet-5", result.stdout)
            self.assertIn("--effort\nhigh", result.stdout)
            self.assertIn(head, result.stdout)

            result = subprocess.run([str(SCRIPT), str(repo), head, "HEAD~1", str(prompt)], env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
