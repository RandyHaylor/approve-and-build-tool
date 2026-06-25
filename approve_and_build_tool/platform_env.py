"""Environment construction for the forked executor.

Goal: the fork can WRITE code and run builds/tests, but cannot use your git
identity or credentials to push anywhere. We deliberately do NOT change HOME,
because the Claude CLI needs its own auth (config/keyring) to run at all — nuking
HOME would break the fork. Instead we neutralise git's view of credentials:

  - GIT_CONFIG_GLOBAL/SYSTEM -> /dev/null : no user identity, no credential.helper
  - GIT_TERMINAL_PROMPT=0                 : never block prompting for a password
  - GIT_SSH_COMMAND with IdentitiesOnly + no key/agent : ssh push cannot use ~/.ssh
  - SSH_AUTH_SOCK unset                   : no agent-forwarded keys

This is defence-in-depth on top of two stronger guarantees the caller provides:
the session branch has NO remote (nowhere to push), and the fork is denied the
git command via Bash(git *). Full isolation (scratch HOME + CLAUDE_CONFIG_DIR, or
a sandboxed VM) is the future hardening path; this is the working v1.
"""
import os

_NULL_DEVICE = "/dev/null"


def credential_isolated_env():
    env = dict(os.environ)
    env["GIT_CONFIG_GLOBAL"] = _NULL_DEVICE
    env["GIT_CONFIG_SYSTEM"] = _NULL_DEVICE
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_SSH_COMMAND"] = (
        "ssh -o IdentitiesOnly=yes -o IdentityFile=/dev/null "
        "-o IdentityAgent=none -o BatchMode=yes"
    )
    env.pop("SSH_AUTH_SOCK", None)
    return env
