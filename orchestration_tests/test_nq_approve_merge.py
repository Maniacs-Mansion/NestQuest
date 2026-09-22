from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


APPROVE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/nq-approve-merge"))
HEAD = "a" * 40


class MergeGateTests(unittest.TestCase):
    def test_review_evidence_must_match_exact_head_and_approval(self):
        root = Path("/tmp/opencode")
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            review = Path(directory) / "review.txt"
            review.write_text(f"Findings: none\nREVIEWED_HEAD: {HEAD}\nREVIEW_VERDICT: APPROVED\n")
            APPROVE["validate_review"](review, HEAD)
            with self.assertRaisesRegex(RuntimeError, "exact head"):
                APPROVE["validate_review"](review, "b" * 40)
            review.write_text(f"REVIEWED_HEAD: {HEAD}\nREVIEW_VERDICT: CHANGES_REQUIRED\n")
            with self.assertRaisesRegex(RuntimeError, "exact head"):
                APPROVE["validate_review"](review, HEAD)

    def test_requires_distinct_gitea_reviewer_on_exact_commit(self):
        records = [{"state": "APPROVED", "commit_id": HEAD, "user": {"login": "review_agent"}}]
        with patch.dict(APPROVE["has_platform_review"].__globals__, {"request": lambda *_: records}):
            self.assertTrue(APPROVE["has_platform_review"](149, HEAD, "unused"))
            self.assertFalse(APPROVE["has_platform_review"](149, "b" * 40, "unused"))
            records[0]["user"]["login"] = "orchestrator-agent"
            self.assertFalse(APPROVE["has_platform_review"](149, HEAD, "unused"))
            records[:] = [
                {"id": 1, "state": "APPROVED", "commit_id": HEAD, "user": {"login": "review_agent"}},
                {"id": 2, "state": "REQUEST_CHANGES", "commit_id": HEAD, "user": {"login": "review_agent"}},
            ]
            self.assertFalse(APPROVE["has_platform_review"](149, HEAD, "unused"))


if __name__ == "__main__":
    unittest.main()
