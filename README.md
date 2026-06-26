# approve-and-build-tool

A small, platform-independent Python tool that runs a **propose → approve →
bounded-fork-applies → commit** loop on top of the headless Claude Code CLI.

The point: a conversational agent that *cannot touch your repo*, paired with a
disposable executor that applies only what you approved.

## The loop

1. A **primary** Claude session (`claude -p`) talks with you. It is restricted to
   **Read + WebSearch + WebFetch** — it has no ability to edit files or run
   commands. When you agree on a chunk of work, it emits a `PROPOSE_WORK` block,
   which this tool parses and stages.
2. You **approve** (`/a`). The tool forks the primary session (`--fork-session`,
   full context) into an **executor** that has write tools but **no git** and a
   **credential-isolated environment**, instructed to do *only* the proposed work.
   You can chat with the executor to tweak it.
3. On the next **approve**, the **tool** (never the agent) commits the result on a
   local session branch — always a fast-forward, no merge-conflict path — then
   wakes the primary with the committed diff to review and propose the next chunk.

Enforcement rests on the primary having **no write capability** and the executor
having **no credentials and no remote** — not on out-guessing the model. Drift is
contained (throwaway branch, visible diff), not assumed away.

### Executor permission posture

A headless fork can't answer permission prompts, so its autonomy is set by
`--executor-permission` (stored per session):

- `acceptEdits` *(default)* — file edits without prompts, **no arbitrary bash**.
  Safer; right for a normal dev host.
- `skip-permissions` — full autonomy (edits + bash) via
  `--dangerously-skip-permissions`. Intended for a **sandboxed VM**; on a dev host
  this is real unguarded write/exec.

git is denied in every posture; the real containment is credential/remote isolation.

## Layers

- **Core engine** — `approve_and_build_tool/` with a raw, machine-drivable CLI
  (`raw_cli.py`, JSON in/out) intended for a higher scaffold (e.g. Unharness) to
  drive headlessly.
- **Chat REPL** — `chat_cli.py`, a thin human front-end over that API.

This tool ships **no methodology of its own** — the caller supplies whatever plan
or context it wants; the tool only enforces the rigid approve path.

## Usage

```bash
# Human REPL
python3 -m approve_and_build_tool.chat_cli --project /path/to/your/project

# Raw API (for integration)
python3 -m approve_and_build_tool.raw_cli start   --project . --message "..."
python3 -m approve_and_build_tool.raw_cli chat    --project . --session <uuid> --message "..."
python3 -m approve_and_build_tool.raw_cli review  --project . --session <uuid>
python3 -m approve_and_build_tool.raw_cli approve --project . --session <uuid>
python3 -m approve_and_build_tool.raw_cli status  --project . --session <uuid>
```

Requires the `claude` CLI on PATH and Python 3 (standard library only).

## Raw CLI / integration (driving it without the chat REPL)

`raw_cli` is the machine surface. Each subcommand prints a **JSON result object to
stdout**; live agent text is streamed to **stderr** (so it never pollutes the JSON).
Put `--no-stream` *before* the subcommand to silence the stderr stream.

### Result object (stdout)

Always present:

| field | meaning |
|---|---|
| `session_id` | the session UUID (capture this from `start`) |
| `current_state` | `PRIMARY` (conversing) or `WORK` (a fork is applying work) |
| `staged_proposal` | the parsed proposal dict, or `null` if nothing is staged |
| `branch_name` | the local session branch the tool commits to |

Added depending on the call:

| field | when |
|---|---|
| `primary_reply` | `start`, `chat` (in PRIMARY), and `approve` that commits — the primary's text |
| `work_reply` | `approve` that enters WORK, and `chat` while in WORK — the fork's text |
| `ok` + `entered: "WORK"` | `approve` that launched a fork |
| `ok: false` + `reason: "no_work_staged"` | `approve` in PRIMARY with nothing staged (no agent is called) |
| `committed_sha` | `approve` that committed the fork's work |

### Flags

- `start --session-id <uuid>` — supply your own session UUID (else one is generated).
- `start --executor-permission {acceptEdits|skip-permissions}` — fork posture (default `acceptEdits`).
- `--no-stream` (global, before the subcommand) — do not stream agent text to stderr.

### Driving one chunk (the approve-twice rhythm)

```bash
# 1) Start: primary proposes; capture session_id and check staged_proposal != null
python3 -m approve_and_build_tool.raw_cli start --project . --message "<plan + first ask>"

# 2) (optional) converse until a proposal is staged
python3 -m approve_and_build_tool.raw_cli chat --project . --session <uuid> --message "..."

# 3) Approve #1 -> enters WORK; the fork applies the staged proposal
python3 -m approve_and_build_tool.raw_cli approve --project . --session <uuid>

# 3a) (optional) talk to the fork to tweak before accepting
python3 -m approve_and_build_tool.raw_cli chat --project . --session <uuid> --message "rename X to Y"

# 4) Approve #2 -> commits on the session branch, returns to PRIMARY, primary reviews + proposes next
python3 -m approve_and_build_tool.raw_cli approve --project . --session <uuid>
```

So **two `approve` calls bracket a chunk**: the first runs the fork, the second
commits it and wakes the primary. Abandoned fork session ids are recorded in
`fork_session_id_log` in the session's `state.json` for later inspection.

## Tests

```bash
python3 -m unittest discover -s tests
```
