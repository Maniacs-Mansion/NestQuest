from pathlib import Path
import fcntl
import os
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/nq-orchestrate"


class ForegroundLauncherTests(unittest.TestCase):
    def test_launches_terminal_agent_with_rendered_and_user_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "control"
            scripts = control / "scripts"
            agents = control / ".opencode/agents"
            templates = control / "templates"
            project = root / "project"
            for path in (scripts, agents, templates, project):
                path.mkdir(parents=True, exist_ok=True)
            (templates / "nestquest.profile.json").write_text("{}")
            (agents / "terminal-orchestrator.md").write_text("agent")
            renderer = scripts / "render-cycle-prompt"
            renderer.write_text("#!/bin/sh\nprintf 'BASE TERMINAL PROMPT'")
            controller = scripts / "nq-controller"
            controller_args = root / "controller-args"
            open_marker = root / "open-session"
            controller.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {controller_args}\n"
                f"if test -f {open_marker}; then printf 'interactive NestQuest session open\\n'; "
                "else printf 'no interactive NestQuest session\\n'; fi\n"
            )
            opencode = root / "opencode"
            output = root / "args"
            opencode.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {output}\n")
            systemctl = root / "systemctl"
            stopped = root / "stopped"
            systemctl.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {stopped}\n")
            for executable in (renderer, controller, opencode, systemctl):
                executable.chmod(0o700)
            mission = root / "mission.md"
            mission.write_text("Complete feature EQ-17.")
            env = os.environ.copy()
            env.update({
                "NQ_CONTROL_HOME": str(control),
                "NQ_PROJECT_ROOT": str(project),
                "OPENCODE_BIN": str(opencode),
                "SYSTEMCTL_BIN": str(systemctl),
                "NQ_STATE_DIR": str(root / "state"),
            })
            printed = subprocess.run([str(SCRIPT), "--print-prompt"], env=env,
                                     text=True, capture_output=True)
            self.assertEqual(printed.returncode, 0, printed.stderr)
            self.assertEqual(printed.stdout, "BASE TERMINAL PROMPT\n")
            self.assertFalse(stopped.exists())
            result = subprocess.run([str(SCRIPT), str(mission)], env=env, text=True,
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            args = output.read_text()
            self.assertIn("--agent\nterminal-orchestrator", args)
            self.assertIn("BASE TERMINAL PROMPT", args)
            self.assertIn("# USER MISSION", args)
            self.assertIn("Complete feature EQ-17.", args)
            self.assertEqual(stopped.read_text().splitlines(),
                             ["--user", "stop", "nestquest-controller.service"])
            self.assertEqual(controller_args.read_text().splitlines(),
                             ["--check-interactive", "--project", str(project)])

            output.unlink()
            lock_path = root / "state/controller.lock"
            with lock_path.open("w") as held_lock:
                fcntl.flock(held_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = subprocess.run([str(SCRIPT)], env=env, text=True,
                                        capture_output=True)
                self.assertEqual(locked.returncode, 75)
                self.assertIn("Another NestQuest orchestrator or controller",
                              locked.stderr)
                self.assertFalse(output.exists())

            open_marker.touch()
            refused = subprocess.run([str(SCRIPT)], env=env, text=True,
                                     capture_output=True)
            self.assertEqual(refused.returncode, 75)
            self.assertIn("Another interactive NestQuest", refused.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
