import os
import tempfile
import unittest

from approve_and_build_tool import git_workspace_guard as guard


class GitWorkspaceGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_ensure_repo_creates_repo_and_initial_commit(self):
        self.assertFalse(guard.is_git_repo(self.project))
        guard.ensure_repo_with_initial_commit(self.project)
        self.assertTrue(guard.is_git_repo(self.project))
        # A second call is idempotent and must not raise.
        guard.ensure_repo_with_initial_commit(self.project)

    def test_branch_diff_and_commit_cycle(self):
        guard.ensure_repo_with_initial_commit(self.project)
        guard.create_session_branch(self.project, "approve-build/test1")

        new_file = os.path.join(self.project, "feature.py")
        with open(new_file, "w") as f:
            f.write("print('hello')\n")

        diff = guard.get_staged_diff(self.project)
        self.assertIn("feature.py", diff)

        sha = guard.commit_all(self.project, "approve-and-build: add feature")
        self.assertTrue(sha)

        # Nothing new to commit -> None.
        self.assertIsNone(guard.commit_all(self.project, "noop"))

    def test_session_state_dir_excluded_from_staging(self):
        guard.ensure_repo_with_initial_commit(self.project)
        guard.exclude_session_state_from_git(self.project)
        # Create a file under the tool's session-state dir.
        sessions_dir = os.path.join(self.project, ".claude", "approve-and-build-sessions", "s1")
        os.makedirs(sessions_dir)
        with open(os.path.join(sessions_dir, "state.json"), "w") as f:
            f.write("{}")
        diff = guard.get_staged_diff(self.project)
        self.assertNotIn("approve-and-build-sessions", diff)
        # Idempotent second call must not raise.
        guard.exclude_session_state_from_git(self.project)


if __name__ == "__main__":
    unittest.main()
