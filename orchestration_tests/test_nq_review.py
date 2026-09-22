from pathlib import Path
import runpy
import unittest

REVIEW = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/nq-review"))
HEAD = "a" * 40

class ReviewLauncherTests(unittest.TestCase):
    def test_exact_head_verdict(self):
        self.assertEqual(REVIEW["verdict"](f"REVIEWED_HEAD: {HEAD}\nREVIEW_VERDICT: APPROVED\n", HEAD), "APPROVED")
        with self.assertRaisesRegex(RuntimeError, "one verdict"):
            REVIEW["verdict"](f"REVIEWED_HEAD: {'b' * 40}\nREVIEW_VERDICT: APPROVED\n", HEAD)
        with self.assertRaisesRegex(RuntimeError, "one verdict"):
            REVIEW["verdict"](f"REVIEWED_HEAD: {HEAD}\nREVIEW_VERDICT: APPROVED\nREVIEW_VERDICT: CHANGES_REQUIRED\n", HEAD)

if __name__ == "__main__":
    unittest.main()
