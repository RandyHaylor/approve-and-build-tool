"""Controller orchestration tests with a fake Claude (no real `claude -p` calls).

Real session_store and real git_workspace_guard run against a temp repo; only the
two Claude-invoking collaborators are faked. The fake executor actually writes a
file into the project so the git commit path is exercised for real.
"""
import os
import tempfile
import unittest

from approve_and_build_tool import git_workspace_guard, session_store
from approve_and_build_tool.approve_build_controller import ApproveBuildController
from approve_and_build_tool.proposed_work_parser import SENTINEL_OPEN, SENTINEL_CLOSE


def _proposal_block(summary):
    return (SENTINEL_OPEN + '\n{"summary": "' + summary + '", "details": "d"}\n'
            + SENTINEL_CLOSE)


class FakeHeadlessRunner:
    def __init__(self, scripted_replies):
        self._scripted_replies = list(scripted_replies)
        self.start_calls = 0
        self.resume_calls = 0

    def start_primary(self, project_path, primary_session_id, first_message, on_text_delta=None):
        self.start_calls += 1
        return self._next()

    def resume_primary(self, project_path, primary_session_id, message, on_text_delta=None):
        self.resume_calls += 1
        return self._next()

    def _next(self):
        return self._scripted_replies.pop(0) if self._scripted_replies else "ok"


class FakeForkedExecutor:
    """Simulates an executor that writes one file when it runs."""
    DEFAULT_EXECUTOR_PERMISSION = "acceptEdits"

    def __init__(self):
        self.run_calls = 0
        self.resume_calls = 0
        self.last_posture = None

    def run_forked_executor(self, project_path, primary_session_id, forked_session_id,
                            proposed_work, on_text_delta=None,
                            permission_posture=DEFAULT_EXECUTOR_PERMISSION):
        self.run_calls += 1
        self.last_posture = permission_posture
        written = os.path.join(project_path, "applied_by_fork.txt")
        with open(written, "w") as f:
            f.write("work: " + str(proposed_work.get("summary")) + "\n")
        return "done applying"

    def resume_forked_executor(self, project_path, forked_session_id, tweak_message,
                               on_text_delta=None,
                               permission_posture=DEFAULT_EXECUTOR_PERMISSION):
        self.resume_calls += 1
        self.last_posture = permission_posture
        return "tweaked"


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _make(self, scripted_replies):
        self.runner = FakeHeadlessRunner(scripted_replies)
        self.executor = FakeForkedExecutor()
        return ApproveBuildController(
            headless_runner=self.runner,
            forked_executor=self.executor,
            git_guard=git_workspace_guard,
            store=session_store,
        )

    def test_start_stages_proposal_and_makes_branch(self):
        controller = self._make(["Here is the plan.\n" + _proposal_block("first chunk")])
        result = controller.start(self.project, "build me a thing")
        self.assertEqual(result["current_state"], session_store.STATE_PRIMARY)
        self.assertEqual(result["staged_proposal"]["summary"], "first chunk")
        self.assertTrue(result["branch_name"].startswith("approve-build/"))
        self.assertTrue(git_workspace_guard.is_git_repo(self.project))

    def test_approve_with_nothing_staged_does_not_engage_agent(self):
        controller = self._make(["no proposal in this reply"])
        result = controller.start(self.project, "hi")
        self.assertIsNone(result["staged_proposal"])
        approve_result = controller.approve(self.project, result["session_id"])
        self.assertFalse(approve_result["ok"])
        self.assertEqual(approve_result["reason"], "no_work_staged")
        self.assertEqual(self.executor.run_calls, 0)

    def test_full_loop_primary_to_work_to_commit_to_next_proposal(self):
        controller = self._make([
            "plan\n" + _proposal_block("chunk one"),          # start -> staged
            "reviewed, next:\n" + _proposal_block("chunk two"),  # post-commit wake -> next
        ])
        started = controller.start(self.project, "go")
        sid = started["session_id"]

        # Approve #1: enter WORK, fork writes a file.
        work_result = controller.approve(self.project, sid)
        self.assertTrue(work_result["ok"])
        self.assertEqual(work_result["entered"], "WORK")
        self.assertEqual(self.executor.run_calls, 1)
        self.assertTrue(os.path.exists(os.path.join(self.project, "applied_by_fork.txt")))

        # Approve #2: commit, return to PRIMARY, primary proposes the next chunk.
        commit_result = controller.approve(self.project, sid)
        self.assertTrue(commit_result["ok"])
        self.assertTrue(commit_result["committed_sha"])
        self.assertEqual(commit_result["current_state"], session_store.STATE_PRIMARY)
        self.assertEqual(commit_result["staged_proposal"]["summary"], "chunk two")

        # The committed file is really in git history now.
        log = git_workspace_guard._run_git(self.project, ["log", "--oneline"])
        self.assertIn("approve-and-build: chunk one", log)

    def test_chat_in_work_mode_talks_to_fork(self):
        controller = self._make(["plan\n" + _proposal_block("c1")])
        started = controller.start(self.project, "go")
        sid = started["session_id"]
        controller.approve(self.project, sid)  # now in WORK
        result = controller.chat(self.project, sid, "tweak: rename it")
        self.assertEqual(result["work_reply"], "tweaked")
        self.assertEqual(self.executor.resume_calls, 1)


if __name__ == "__main__":
    unittest.main()
