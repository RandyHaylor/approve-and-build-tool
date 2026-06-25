"""Thin wrapper over the headless Claude CLI (`claude -p`) with live streaming.

Exposes only what the controller needs:
  - start_primary  : launch the read+web-only conversation agent at a known id
  - resume_primary : send another user turn to that same session
  - run_claude_streaming : the shared NDJSON-streaming subprocess driver

All Claude flags used here were verified against the Claude Code docs
(v2.1.x): --session-id, --resume, --fork-session, --allowedTools,
--permission-mode, --output-format stream-json, --verbose,
--include-partial-messages, --disallowedTools "Bash(git *)".
"""
import json
import subprocess

# The primary agent may only read and search — it has no hands on the repo.
PRIMARY_ALLOWED_TOOLS = "Read,WebSearch,WebFetch"


def start_primary(project_path, primary_session_id, first_message, on_text_delta=None):
    args = [
        "claude", "-p", first_message,
        "--session-id", primary_session_id,
        "--allowedTools", PRIMARY_ALLOWED_TOOLS,
        "--permission-mode", "dontAsk",
        *_STREAMING_FLAGS,
    ]
    return run_claude_streaming(args, project_path, on_text_delta)


def resume_primary(project_path, primary_session_id, message, on_text_delta=None):
    args = [
        "claude", "-p", message,
        "--resume", primary_session_id,
        "--allowedTools", PRIMARY_ALLOWED_TOOLS,
        "--permission-mode", "dontAsk",
        *_STREAMING_FLAGS,
    ]
    return run_claude_streaming(args, project_path, on_text_delta)


_STREAMING_FLAGS = [
    "--output-format", "stream-json",
    "--verbose",
    "--include-partial-messages",
]


def run_claude_streaming(args, cwd, on_text_delta=None, env=None):
    """Run a `claude -p ... --output-format stream-json` subprocess.

    Streams text deltas to ``on_text_delta`` as they arrive and returns the
    assembled final assistant text. Prefers the terminal ``result`` event's
    text; falls back to concatenated deltas if no result text is present.
    ``env`` overrides the child environment (the forked executor passes a
    credential-isolated env here).
    """
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    collected_deltas = []
    final_result_text = None
    for line in proc.stdout:
        event = _try_load_json_line(line)
        if event is None:
            continue
        delta_text = _extract_text_delta(event)
        if delta_text:
            collected_deltas.append(delta_text)
            if on_text_delta is not None:
                on_text_delta(delta_text)
        result_text = _extract_result_text(event)
        if result_text is not None:
            final_result_text = result_text
    stderr_text = proc.stderr.read()
    return_code = proc.wait()
    if return_code != 0:
        raise ClaudeHeadlessError(
            "claude exited with code %d:\n%s" % (return_code, stderr_text.strip())
        )
    if final_result_text is not None:
        return final_result_text
    return "".join(collected_deltas)


class ClaudeHeadlessError(RuntimeError):
    pass


def _try_load_json_line(line):
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except ValueError:
        return None


def _extract_text_delta(event):
    if event.get("type") != "stream_event":
        return None
    inner = event.get("event", {})
    delta = inner.get("delta", {})
    if delta.get("type") == "text_delta":
        return delta.get("text", "")
    return None


def _extract_result_text(event):
    if event.get("type") == "result" and isinstance(event.get("result"), str):
        return event["result"]
    return None
