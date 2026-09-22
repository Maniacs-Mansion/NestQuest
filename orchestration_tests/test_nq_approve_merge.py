from pathlib import Path
import contextlib
import io
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch


APPROVE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/nq-approve-merge"))
HEAD = "a" * 40


class MergeGateTests(unittest.TestCase):
    def test_main_rejects_moved_head_unmergeable_and_pending_checks(self):
        root = Path("/tmp/opencode")
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            review_file = Path(directory) / "review.txt"
            review_file.write_text(f"REVIEWED_HEAD: {HEAD}\nREVIEW_VERDICT: APPROVED\n")
            for problem in ("moved", "unmergeable", "pending", "none"):
                with self.subTest(problem=problem):
                    merged = False
                    calls = []
                    def fake_request(path, token, payload=None):
                        nonlocal merged
                        calls.append((path, payload))
                        if path.endswith("/reviews"):
                            return [{"id": 1, "state": "APPROVED", "commit_id": HEAD,
                                     "user": {"login": "review_agent"}}]
                        if path.endswith("/status"):
                            return {"total_count": 1, "state": "pending" if problem == "pending" else "success"}
                        if path.endswith("/merge"):
                            merged = True
                            return {}
                        if path.endswith("/pulls/149"):
                            return {"number": 149, "base": {"ref": "dev"},
                                    "head": {"sha": "b" * 40 if problem == "moved" else HEAD},
                                    "state": "open", "merged": merged,
                                    "mergeable": problem != "unmergeable"}
                        raise AssertionError(path)
                    globals_ = APPROVE["main"].__globals__
                    with patch.dict(globals_, {"request": fake_request,
                                               "token_from_file": lambda: "test"}), \
                         patch.object(sys, "argv", ["nq-approve-merge", "merge", "149", HEAD,
                                                    str(review_file)]), \
                         contextlib.redirect_stdout(io.StringIO()):
                        if problem == "none":
                            self.assertEqual(APPROVE["main"](), 0)
                        else:
                            with self.assertRaises(RuntimeError):
                                APPROVE["main"]()
                    self.assertEqual(merged, problem == "none")

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
