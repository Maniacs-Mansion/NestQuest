import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
RENDER = runpy.run_path(str(ROOT / "scripts/render-cycle-prompt"))["render"]
SELECT_RUNTIME = runpy.run_path(str(ROOT / "scripts/render-cycle-prompt"))["select_runtime"]
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
            "START_COMMAND": "/start-examplequest-development",
            "STOP_COMMAND": "/stop-examplequest-development",
            "STATUS_COMMAND": "/examplequest-development-status",
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

    def test_terminal_runtime_replaces_service_controller(self):
        selected = SELECT_RUNTIME(TEMPLATE, "terminal")
        output = RENDER(selected, PROFILE)
        self.assertIn("# 27. FOREGROUND TERMINAL RUNTIME", output)
        self.assertIn("nq-orchestrate", output)
        self.assertNotIn("# 27. HOST CONTROLLER RUNTIME", output)
        self.assertNotIn("The persistent user service runs", output)
        self.assertNotIn("---\n\n---\n\n# 27", output)


if __name__ == "__main__":
    unittest.main()
