"""Launch a bounded execution fork of the primary session.

The fork inherits the primary's full conversational context (so it understands
the proposal as discussed) via `--resume PRIMARY --fork-session --session-id FORK`
(custom fork id confirmed working in the save-fork skill). It runs with FULL
default tools EXCEPT git, which is denied via `--disallowedTools "Bash(git *)"`,
and in a credential-isolated env. Its single instruction: do ONLY the proposed
work, then stop. Drift is contained, not prevented — the tool commits whatever
the fork produced onto a throwaway session branch for the user to inspect.
"""
from . import claude_headless_runner
from .platform_env import credential_isolated_env

GIT_DENY_RULE = "Bash(git *)"

# A headless -p fork cannot answer permission prompts, so it needs an explicit
# posture to act autonomously. The posture is configurable per environment:
#   - "acceptEdits"      : file edits without prompts; NO arbitrary bash. Safer
#                          default; fine when the chunk is pure code edits.
#   - "skip-permissions" : full autonomy (edits + bash) via
#                          --dangerously-skip-permissions. Intended for a
#                          sandboxed VM; real unguarded write/exec on a dev host.
# In every posture git is denied as a courtesy speed bump; the real containment
# is credential/remote isolation (platform_env) + a local-only branch.
POSTURE_ACCEPT_EDITS = "acceptEdits"
POSTURE_SKIP_PERMISSIONS = "skip-permissions"
DEFAULT_EXECUTOR_PERMISSION = POSTURE_ACCEPT_EDITS
SUPPORTED_EXECUTOR_PERMISSIONS = (POSTURE_ACCEPT_EDITS, POSTURE_SKIP_PERMISSIONS)


def executor_permission_flags(posture):
    if posture == POSTURE_SKIP_PERMISSIONS:
        return ["--dangerously-skip-permissions", "--disallowedTools", GIT_DENY_RULE]
    if posture == POSTURE_ACCEPT_EDITS:
        return ["--permission-mode", "acceptEdits", "--disallowedTools", GIT_DENY_RULE]
    raise ValueError(
        "unsupported executor permission posture: %r (expected one of %r)"
        % (posture, list(SUPPORTED_EXECUTOR_PERMISSIONS))
    )


def run_forked_executor(
    project_path,
    primary_session_id,
    forked_session_id,
    proposed_work,
    on_text_delta=None,
    permission_posture=DEFAULT_EXECUTOR_PERMISSION,
):
    instruction = build_executor_instruction(proposed_work)
    args = [
        "claude", "-p", instruction,
        "--resume", primary_session_id,
        "--fork-session",
        "--session-id", forked_session_id,
        *executor_permission_flags(permission_posture),
        *claude_headless_runner._STREAMING_FLAGS,
    ]
    return _run_with_isolated_credentials(args, project_path, on_text_delta)


def resume_forked_executor(
    project_path,
    forked_session_id,
    tweak_message,
    on_text_delta=None,
    permission_posture=DEFAULT_EXECUTOR_PERMISSION,
):
    """Send a follow-up (tweak/question) to an already-running execution fork."""
    args = [
        "claude", "-p", tweak_message,
        "--resume", forked_session_id,
        *executor_permission_flags(permission_posture),
        *claude_headless_runner._STREAMING_FLAGS,
    ]
    return _run_with_isolated_credentials(args, project_path, on_text_delta)


def build_executor_instruction(proposed_work):
    import json
    proposal_json = json.dumps(proposed_work, indent=2)
    return (
        "You are an execution fork. DO ONLY THE FOLLOWING PROPOSED WORK, then "
        "STOP and return. Do not start adjacent improvements, refactors, or "
        "extra files beyond what is described. You may read, edit, and run the "
        "code, but you may NOT use git in any way.\n\n"
        "PROPOSED WORK:\n" + proposal_json
    )


def _run_with_isolated_credentials(args, project_path, on_text_delta):
    return claude_headless_runner.run_claude_streaming(
        args, project_path, on_text_delta, env=credential_isolated_env()
    )
