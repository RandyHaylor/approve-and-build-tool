import unittest

from approve_and_build_tool import forked_executor_launcher as launcher


class ExecutorPermissionFlagsTests(unittest.TestCase):
    def test_accept_edits_posture(self):
        flags = launcher.executor_permission_flags(launcher.POSTURE_ACCEPT_EDITS)
        self.assertIn("--permission-mode", flags)
        self.assertIn("acceptEdits", flags)
        self.assertIn(launcher.GIT_DENY_RULE, flags)
        self.assertNotIn("--dangerously-skip-permissions", flags)

    def test_skip_permissions_posture(self):
        flags = launcher.executor_permission_flags(launcher.POSTURE_SKIP_PERMISSIONS)
        self.assertIn("--dangerously-skip-permissions", flags)
        self.assertIn(launcher.GIT_DENY_RULE, flags)

    def test_default_is_accept_edits(self):
        self.assertEqual(launcher.DEFAULT_EXECUTOR_PERMISSION, launcher.POSTURE_ACCEPT_EDITS)

    def test_unknown_posture_raises(self):
        with self.assertRaises(ValueError):
            launcher.executor_permission_flags("wide-open")

    def test_executor_instruction_contains_only_and_no_git(self):
        instruction = launcher.build_executor_instruction({"summary": "s", "details": "d"})
        self.assertIn("DO ONLY", instruction)
        self.assertIn("NOT use git", instruction)


if __name__ == "__main__":
    unittest.main()
