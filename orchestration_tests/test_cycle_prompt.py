import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
RENDER = runpy.run_path(str(ROOT / "scripts/render-cycle-prompt"))["render"]
TEMPLATE = (ROOT / "templates/ORCHESTRATOR-PROMPT.template.md").read_text()
PROFILE = json.loads((ROOT / "templates/nestquest.profile.json").read_text())


class CyclePromptTests(unittest.TestCase):
    def test_project_profile_renders_without_specific_source_names(self):
        other = PROFILE.copy()
        other.update({
            "PROJECT_NAME": "ExampleQuest",
            "PROJECT_CONTEXT_LABEL": "EXAMPLEQUEST COORDINATION",
            "WORK_TRACKER": "TaskGrid",
            "CONTEXT_STORE": "ContextHub",
            "INTEGRATION_BRANCH": "integration",
            "RELEASE_BRANCH": "production",
            "CONTROL_HOME": "/opt/examplequest/controller",
            "SERVICE_NAME": "examplequest-controller.service",
            "PROJECT_ROOT": "/srv/examplequest",
            "TERMINAL_LAUNCHER": "eq-orchestrate",
            "FEATURE_BRANCH_EXAMPLE": "feature/EQ-17",
        })
        output = RENDER(TEMPLATE, other)
        self.assertIn("ExampleQuest Persistent Autonomous", output)
        self.assertIn("TaskGrid", output)
        self.assertIn("ContextHub", output)
        self.assertIn("feature/EQ-17", output)
        self.assertNotIn("NestQuest", output)
        self.assertNotIn("nestquest", output)
        self.assertNotIn("Maestro", output)
        self.assertNotIn("CTXD", output)
        self.assertNotIn("{{", output)

    def test_missing_value_fails_before_publication(self):
        other = PROFILE.copy()
        del other["PROJECT_NAME"]
        with self.assertRaisesRegex(ValueError, "PROJECT_NAME"):
            RENDER(TEMPLATE, other)

    def test_template_contains_only_terminal_runtime(self):
        output = RENDER(TEMPLATE, PROFILE)
        self.assertIn("# 27. FOREGROUND TERMINAL RUNTIME", output)
        self.assertIn("nq-orchestrate", output)
        self.assertNotIn("# 27. HOST CONTROLLER RUNTIME", output)
        self.assertNotIn("The persistent user service runs", output)
        self.assertNotIn("---\n\n---\n\n# 27", output)

    def test_task_complete_feature_triggers_one_guarded_promotion(self):
        output = RENDER(TEMPLATE, PROFILE)
        self.assertIn(
            "feature becomes task-complete and its reviewed merge into `dev` is verified",
            output,
        )
        self.assertIn("Every required feature task is `done`", output)
        self.assertIn("No task review, remediation, approval, or merge remains pending", output)
        self.assertIn("feature acceptance criteria and integrated checks pass", output)
        self.assertIn("Independent approval applies to the exact feature head", output)
        self.assertIn("approver's merge of that head into `dev` is verified", output)
        self.assertIn("reflects the completed feature and exact repository references", output)
        self.assertIn("Task completion inside an unmerged feature branch does not trigger", output)
        self.assertIn("Do not create a duplicate promotion", output)
        self.assertIn("Allow only one active promotion pull request to `main`", output)
        self.assertIn("if it was closed without merge, recalculate", output)
        self.assertIn("sole active orchestrator for the project", output)
        self.assertIn("including controller exclusivity, reconciliation", output)
        self.assertIn("RELEASE_PREPARATION_POLICY = EXCLUDED", output)
        self.assertIn("Active promotion branch and pull request", output)
        self.assertIn("An active promotion that has not reached `RELEASE_READY`", output)
        self.assertIn("RELEASE_PREPARATION_POLICY:\n", output)
        self.assertIn("A ready promotion is a local checkpoint", output)
        self.assertIn("continue that work while the ready promotion waits", output)
        self.assertLess(
            output.index("Begin an automatically triggered, requested, or scheduled release"),
            output.index("Advance to the next eligible feature"),
        )
        self.assertIn("Only Joshua may merge into `main`", output)


if __name__ == "__main__":
    unittest.main()
