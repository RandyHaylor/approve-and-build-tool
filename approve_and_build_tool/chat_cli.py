"""Layer B: a lightweight human chat REPL over the raw controller.

This is ONE consumer of the tool, not the tool. It maps slash verbs to controller
calls and streams agent text live. The prompt reflects state: a staged proposal
shows "(work proposed)"; WORK state shows "(work mode - /a to approve)".

    python -m approve_and_build_tool.chat_cli --project .

Commands:  /a or /approve   |   /r or /review   |   /q or /quit   |   anything else = chat
"""
import argparse
import sys

from .approve_build_controller import ApproveBuildController
from .forked_executor_launcher import (
    DEFAULT_EXECUTOR_PERMISSION,
    SUPPORTED_EXECUTOR_PERMISSIONS,
)
from . import session_store


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="approve-and-build-chat", description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument(
        "--executor-permission",
        choices=list(SUPPORTED_EXECUTOR_PERMISSIONS),
        default=DEFAULT_EXECUTOR_PERMISSION,
        help="permission posture for the execution fork (default: %(default)s)")
    args = parser.parse_args(argv)

    controller = ApproveBuildController()
    repl = ChatRepl(controller, args.project, args.executor_permission)
    return repl.run()


class ChatRepl:
    def __init__(self, controller, project_path, executor_permission=DEFAULT_EXECUTOR_PERMISSION):
        self._controller = controller
        self._project_path = project_path
        self._executor_permission = executor_permission
        self._session_id = None
        self._last_state = session_store.STATE_PRIMARY
        self._last_staged = None

    def run(self):
        print("approve-and-build chat. Type your first message to start (/q to quit).")
        first = self._read_line("you> ")
        if first is None or first.strip() in ("/q", "/quit"):
            return 0
        self._handle_result(self._controller.start(
            self._project_path, first, on_text_delta=_panel_for_primary(),
            executor_permission=self._executor_permission))

        while True:
            line = self._read_line(self._prompt())
            if line is None:
                return 0
            stripped = line.strip()
            if stripped in ("/q", "/quit"):
                return 0
            if stripped in ("/r", "/review"):
                self._show_staged()
                continue
            if stripped in ("/a", "/approve"):
                self._do_approve()
                continue
            self._handle_result(self._controller.chat(
                self._project_path, self._session_id, line, on_text_delta=self._active_panel()))

    # ----- actions ------------------------------------------------------
    def _do_approve(self):
        if self._last_state == session_store.STATE_PRIMARY and not self._last_staged:
            print("(no work staged — nothing to approve)")
            return
        result = self._controller.approve(
            self._project_path, self._session_id, on_text_delta=self._active_panel())
        if result.get("ok") is False and result.get("reason") == "no_work_staged":
            print("(no work staged — nothing to approve)")
            return
        if result.get("committed_sha"):
            print("\n[committed " + str(result["committed_sha"])[:10] + "]")
        self._handle_result(result)

    def _show_staged(self):
        result = self._controller.review(self._project_path, self._session_id)
        staged = result.get("staged_proposal")
        if not staged:
            print("(nothing staged)")
        else:
            import json
            print("staged proposal:\n" + json.dumps(staged, indent=2))

    # ----- state tracking + rendering -----------------------------------
    def _handle_result(self, result):
        self._session_id = result["session_id"]
        self._last_state = result["current_state"]
        self._last_staged = result.get("staged_proposal")
        sys.stdout.write("\n")

    def _prompt(self):
        if self._last_state == session_store.STATE_WORK:
            return "you (work mode - /a to approve)> "
        if self._last_staged:
            return "you (work proposed - /a to approve, /r to review)> "
        return "you> "

    def _active_panel(self):
        if self._last_state == session_store.STATE_WORK:
            return _panel_for_work()
        return _panel_for_primary()

    def _read_line(self, prompt):
        try:
            return input(prompt)
        except (EOFError, KeyboardInterrupt):
            print()
            return None


def _panel_for_primary():
    def emit(text_delta):
        sys.stdout.write(text_delta)
        sys.stdout.flush()
    return emit


def _panel_for_work():
    state = {"started": False}

    def emit(text_delta):
        if not state["started"]:
            sys.stdout.write("\n--- work fork ---\n")
            state["started"] = True
        sys.stdout.write(text_delta)
        sys.stdout.flush()
    return emit


if __name__ == "__main__":
    sys.exit(main())
