"""The PRIMARY <-> WORK state machine and the tool's core operations.

Dependencies (headless runner, forked executor, git guard, session store) are
injected so the orchestration can be unit-tested with fakes; they default to the
real modules. Every public method returns a plain dict result so the raw CLI can
emit it as JSON for a higher scaffold to consume.
"""
import uuid

from . import claude_headless_runner as _default_headless_runner
from . import forked_executor_launcher as _default_forked_executor
from . import git_workspace_guard as _default_git_guard
from . import session_store as _default_store
from .primary_preamble import build_first_primary_message
from .proposed_work_parser import parse_latest_proposed_work


class ApproveBuildController:
    def __init__(
        self,
        headless_runner=_default_headless_runner,
        forked_executor=_default_forked_executor,
        git_guard=_default_git_guard,
        store=_default_store,
    ):
        self._headless_runner = headless_runner
        self._forked_executor = forked_executor
        self._git_guard = git_guard
        self._store = store

    # ----- start a new session -----------------------------------------
    def start(self, project_path, user_first_message, session_id=None, on_text_delta=None,
              executor_permission=None):
        session_id = session_id or str(uuid.uuid4())
        branch_name = "approve-build/" + session_id[:8]
        executor_permission = executor_permission or self._forked_executor.DEFAULT_EXECUTOR_PERMISSION
        self._git_guard.ensure_repo_with_initial_commit(project_path)
        self._git_guard.exclude_session_state_from_git(project_path)
        self._git_guard.create_session_branch(project_path, branch_name)
        state = self._store.create_session(
            project_path, branch_name, session_id=session_id,
            executor_permission=executor_permission)

        first_message = build_first_primary_message(user_first_message)
        reply = self._headless_runner.start_primary(
            project_path, state["primary_session_id"], first_message, on_text_delta
        )
        self._stage_if_proposed(state, reply)
        self._store.save_session(state)
        return self._result(state, primary_reply=reply)

    # ----- converse -----------------------------------------------------
    def chat(self, project_path, session_id, message, on_text_delta=None):
        state = self._store.load_session(project_path, session_id)
        if state["current_state"] == self._store.STATE_WORK:
            reply = self._forked_executor.resume_forked_executor(
                project_path, state["forked_session_id"], message, on_text_delta,
                permission_posture=self._executor_permission_for(state),
            )
            self._store.save_session(state)
            return self._result(state, work_reply=reply)
        reply = self._headless_runner.resume_primary(
            project_path, state["primary_session_id"], message, on_text_delta
        )
        self._stage_if_proposed(state, reply)
        self._store.save_session(state)
        return self._result(state, primary_reply=reply)

    # ----- inspect staged work -----------------------------------------
    def review(self, project_path, session_id):
        state = self._store.load_session(project_path, session_id)
        return self._result(state)

    # ----- the rigid approve path --------------------------------------
    def approve(self, project_path, session_id, on_text_delta=None):
        state = self._store.load_session(project_path, session_id)
        if state["current_state"] == self._store.STATE_PRIMARY:
            return self._approve_from_primary(project_path, state, on_text_delta)
        return self._approve_from_work(project_path, state, on_text_delta)

    def status(self, project_path, session_id):
        state = self._store.load_session(project_path, session_id)
        return self._result(state)

    # ----- internals ----------------------------------------------------
    def _approve_from_primary(self, project_path, state, on_text_delta):
        if not state.get("staged_proposal"):
            # No agent is engaged when there is nothing staged — pure code path.
            return self._result(state, ok=False, reason="no_work_staged")
        forked_session_id = str(uuid.uuid4())
        state["forked_session_id"] = forked_session_id
        state.setdefault("fork_session_id_log", []).append(forked_session_id)
        state["current_state"] = self._store.STATE_WORK
        self._store.save_session(state)  # persist before the long-running fork
        reply = self._forked_executor.run_forked_executor(
            project_path,
            state["primary_session_id"],
            forked_session_id,
            state["staged_proposal"],
            on_text_delta,
            permission_posture=self._executor_permission_for(state),
        )
        return self._result(state, ok=True, entered="WORK", work_reply=reply)

    def _approve_from_work(self, project_path, state, on_text_delta):
        applied_proposal = state.get("staged_proposal")
        diff_text = self._git_guard.get_staged_diff(project_path)
        commit_message = _commit_message_for(applied_proposal)
        commit_sha = self._git_guard.commit_all(project_path, commit_message)

        state["current_state"] = self._store.STATE_PRIMARY
        state["staged_proposal"] = None
        state["forked_session_id"] = None
        self._store.save_session(state)

        wake_message = _build_primary_review_prompt(applied_proposal, commit_sha, diff_text)
        reply = self._headless_runner.resume_primary(
            project_path, state["primary_session_id"], wake_message, on_text_delta
        )
        self._stage_if_proposed(state, reply)
        self._store.save_session(state)
        return self._result(state, ok=True, committed_sha=commit_sha, primary_reply=reply)

    def _executor_permission_for(self, state):
        return state.get("executor_permission") or self._forked_executor.DEFAULT_EXECUTOR_PERMISSION

    def _stage_if_proposed(self, state, agent_reply_text):
        proposal = parse_latest_proposed_work(agent_reply_text)
        if proposal is not None:
            state["staged_proposal"] = proposal

    def _result(self, state, **extra):
        result = {
            "session_id": state["session_id"],
            "current_state": state["current_state"],
            "staged_proposal": state.get("staged_proposal"),
            "branch_name": state["branch_name"],
        }
        result.update(extra)
        return result


def _commit_message_for(proposal):
    summary = (proposal or {}).get("summary") if isinstance(proposal, dict) else None
    return "approve-and-build: " + (summary or "approved work chunk")


def _build_primary_review_prompt(applied_proposal, commit_sha, diff_text):
    summary = ""
    if isinstance(applied_proposal, dict):
        summary = applied_proposal.get("summary", "")
    return (
        "The proposed work was applied by the execution fork and committed as "
        + str(commit_sha) + ".\n"
        "Proposed summary was: " + summary + "\n\n"
        "Here is the committed diff:\n\n" + diff_text + "\n\n"
        "Review what was actually built against what you proposed, tell the user "
        "briefly what landed, then propose the next chunk (or ask the user what's "
        "next). Re-emit a PROPOSE_WORK block only when you have a concrete next chunk."
    )
