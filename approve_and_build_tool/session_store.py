"""On-disk session state for an approve-and-build session.

State lives at <project>/.claude/approve-and-build-sessions/<uuid>/state.json so a
higher scaffold (e.g. Unharness) and the local chat REPL both read the same truth.
The state is a plain dict, deliberately small and JSON-only.
"""
import json
import os
import uuid

SESSIONS_DIRNAME = os.path.join(".claude", "approve-and-build-sessions")
STATE_FILENAME = "state.json"

STATE_PRIMARY = "PRIMARY"  # conversing with the read-only primary agent
STATE_WORK = "WORK"        # a fork is applying approved work; awaiting accept


def sessions_root_for_project(project_path):
    return os.path.join(project_path, SESSIONS_DIRNAME)


def session_dir(project_path, session_id):
    return os.path.join(sessions_root_for_project(project_path), session_id)


def state_path(project_path, session_id):
    return os.path.join(session_dir(project_path, session_id), STATE_FILENAME)


def fork_scratch_home_dir(project_path, session_id):
    """A throwaway HOME-ish dir for the fork's git-credential isolation."""
    return os.path.join(session_dir(project_path, session_id), "fork_scratch_home")


def create_session(project_path, branch_name, primary_session_id=None, session_id=None,
                   executor_permission=None):
    """Create and persist a fresh session state; returns the state dict."""
    session_id = session_id or str(uuid.uuid4())
    primary_session_id = primary_session_id or str(uuid.uuid4())
    state = {
        "session_id": session_id,
        "project_path": os.path.abspath(project_path),
        "primary_session_id": primary_session_id,
        "branch_name": branch_name,
        "current_state": STATE_PRIMARY,
        "staged_proposal": None,
        "forked_session_id": None,
        "executor_permission": executor_permission,
    }
    os.makedirs(session_dir(project_path, session_id), exist_ok=True)
    os.makedirs(fork_scratch_home_dir(project_path, session_id), exist_ok=True)
    save_session(state)
    return state


def load_session(project_path, session_id):
    with open(state_path(project_path, session_id), "r") as f:
        return json.load(f)


def save_session(state):
    path = state_path(state["project_path"], state["session_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp_path, path)
