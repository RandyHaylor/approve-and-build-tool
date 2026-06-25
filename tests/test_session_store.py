import os
import tempfile
import unittest

from approve_and_build_tool import session_store


class SessionStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_create_then_load_roundtrip(self):
        created = session_store.create_session(self.project, "approve-build/abc12345")
        loaded = session_store.load_session(self.project, created["session_id"])
        self.assertEqual(loaded["branch_name"], "approve-build/abc12345")
        self.assertEqual(loaded["current_state"], session_store.STATE_PRIMARY)
        self.assertIsNone(loaded["staged_proposal"])
        self.assertTrue(loaded["primary_session_id"])

    def test_save_persists_changes(self):
        state = session_store.create_session(self.project, "b")
        state["current_state"] = session_store.STATE_WORK
        state["staged_proposal"] = {"summary": "do thing"}
        session_store.save_session(state)
        reloaded = session_store.load_session(self.project, state["session_id"])
        self.assertEqual(reloaded["current_state"], session_store.STATE_WORK)
        self.assertEqual(reloaded["staged_proposal"]["summary"], "do thing")

    def test_fixed_session_id_honored_and_dirs_made(self):
        state = session_store.create_session(self.project, "b", session_id="fixed-id-123")
        self.assertEqual(state["session_id"], "fixed-id-123")
        self.assertTrue(os.path.isdir(
            session_store.fork_scratch_home_dir(self.project, "fixed-id-123")))


if __name__ == "__main__":
    unittest.main()
