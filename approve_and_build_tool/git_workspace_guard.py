"""All git operations for a session. The TOOL is the sole committer.

The forked executor agent is denied git (and credential-isolated), so the only
path from "files changed in the working tree" to "a commit on the session branch"
is through this module. Because nothing else writes to the session branch, every
commit here is a fast-forward — there is no merge-conflict path by construction.
"""
import os
import subprocess

from .session_store import SESSIONS_DIRNAME


class GitCommandError(RuntimeError):
    pass


def exclude_session_state_from_git(project_path):
    """Keep the tool's own session-state dir out of the user's commits.

    Written to .git/info/exclude (local, never committed) so we neither pollute
    the user's tracked tree with our bookkeeping nor touch their .gitignore.
    Must be called BEFORE the session dir is created so it is never staged.
    """
    exclude_path = os.path.join(project_path, ".git", "info", "exclude")
    pattern = SESSIONS_DIRNAME.replace(os.sep, "/") + "/"
    existing = ""
    if os.path.exists(exclude_path):
        with open(exclude_path, "r") as f:
            existing = f.read()
    if pattern in existing.splitlines():
        return
    os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
    with open(exclude_path, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(pattern + "\n")


def _run_git(project_path, args):
    completed = subprocess.run(
        ["git", *args],
        cwd=project_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise GitCommandError(
            "git " + " ".join(args) + " failed:\n" + completed.stderr.strip()
        )
    return completed.stdout


def is_git_repo(project_path):
    git_dir = os.path.join(project_path, ".git")
    return os.path.isdir(git_dir)


def ensure_repo_with_initial_commit(project_path):
    """Initialise a repo if absent and guarantee at least one commit exists."""
    if not is_git_repo(project_path):
        _run_git(project_path, ["init", "-q"])
        _run_git(project_path, ["checkout", "-q", "-b", "main"])
    if not _has_any_commit(project_path):
        # An empty repo has no HEAD to branch from; lay down a root commit.
        keep_path = os.path.join(project_path, ".gitkeep")
        if not os.path.exists(keep_path):
            with open(keep_path, "w"):
                pass
        _run_git(project_path, ["add", "-A"])
        _commit(project_path, "Initial commit (approve-and-build session root)")


def _has_any_commit(project_path):
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=project_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def create_session_branch(project_path, branch_name):
    _run_git(project_path, ["checkout", "-q", "-b", branch_name])


def get_staged_diff(project_path):
    """Stage everything in the working tree and return the diff to be committed."""
    _run_git(project_path, ["add", "-A"])
    return _run_git(project_path, ["diff", "--cached"])


def commit_all(project_path, message):
    """Stage all changes and commit; returns the new commit sha (or None if nothing)."""
    _run_git(project_path, ["add", "-A"])
    if not _has_staged_changes(project_path):
        return None
    return _commit(project_path, message)


def _has_staged_changes(project_path):
    completed = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=project_path,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    # exit 1 == there ARE staged changes; exit 0 == none.
    return completed.returncode == 1


def _commit(project_path, message):
    # Identity is forced here so the tool's commits never depend on global config
    # (which the fork's isolated env nulls out anyway).
    _run_git(project_path, [
        "-c", "user.name=approve-and-build-tool",
        "-c", "user.email=approve-and-build@localhost",
        "commit", "-q", "-m", message,
    ])
    return _run_git(project_path, ["rev-parse", "HEAD"]).strip()
