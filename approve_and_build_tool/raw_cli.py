"""Layer A: the raw, machine-drivable CLI API.

JSON result to stdout; live agent text streamed to stderr (so a parent process or
a higher scaffold like Unharness can watch progress without it polluting the JSON
result). Every subcommand maps 1:1 to an ApproveBuildController method.

    python -m approve_and_build_tool.raw_cli start   --project . --message "..." [--session-id UUID]
    python -m approve_and_build_tool.raw_cli chat    --project . --session UUID --message "..."
    python -m approve_and_build_tool.raw_cli review   --project . --session UUID
    python -m approve_and_build_tool.raw_cli approve  --project . --session UUID
    python -m approve_and_build_tool.raw_cli status   --project . --session UUID
"""
import argparse
import json
import sys

from .approve_build_controller import ApproveBuildController
from .forked_executor_launcher import (
    DEFAULT_EXECUTOR_PERMISSION,
    SUPPORTED_EXECUTOR_PERMISSIONS,
)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    stream_to_stderr = None if args.no_stream else _stderr_streamer
    controller = ApproveBuildController()

    if args.command == "start":
        result = controller.start(args.project, args.message, args.session_id, stream_to_stderr,
                                  executor_permission=args.executor_permission)
    elif args.command == "chat":
        result = controller.chat(args.project, args.session, args.message, stream_to_stderr)
    elif args.command == "review":
        result = controller.review(args.project, args.session)
    elif args.command == "approve":
        result = controller.approve(args.project, args.session, stream_to_stderr)
    elif args.command == "status":
        result = controller.status(args.project, args.session)
    else:  # pragma: no cover - argparse enforces choices
        parser.error("unknown command")

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _stderr_streamer(text_delta):
    sys.stderr.write(text_delta)
    sys.stderr.flush()


def _build_arg_parser():
    parser = argparse.ArgumentParser(prog="approve-and-build", description=__doc__)
    parser.add_argument("--no-stream", action="store_true",
                        help="do not stream agent text to stderr")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="start a new session")
    start_parser.add_argument("--project", default=".")
    start_parser.add_argument("--message", required=True, help="user's first message")
    start_parser.add_argument("--session-id", default=None, help="optional fixed session UUID")
    start_parser.add_argument(
        "--executor-permission",
        choices=list(SUPPORTED_EXECUTOR_PERMISSIONS),
        default=DEFAULT_EXECUTOR_PERMISSION,
        help="permission posture for the execution fork (default: %(default)s)")

    for name, help_text in (("chat", "send a message"),
                            ("review", "show staged proposal"),
                            ("approve", "approve the rigid path"),
                            ("status", "show session state")):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--project", default=".")
        sub.add_argument("--session", required=True, help="session UUID")
        if name in ("chat",):
            sub.add_argument("--message", required=True)

    return parser


if __name__ == "__main__":
    sys.exit(main())
