"""Extract the staged work proposal from a primary-agent reply.

The primary agent is instructed (see primary_preamble.py) to emit at most one
fenced block of the form:

    <<<PROPOSE_WORK>>>
    { "summary": "...", "details": "...", "files": [...] }
    <<<END_PROPOSE_WORK>>>

This is an IN-HOUSE convention parsed by our own code — it is not a Claude tool.
If the agent emits several over a conversation, the LATEST one wins (it overwrites
any previously staged proposal). Parsing is tolerant: prose around the block is
ignored, and a block whose body is not valid JSON yields no staged proposal
rather than raising.
"""
import json
import re

SENTINEL_OPEN = "<<<PROPOSE_WORK>>>"
SENTINEL_CLOSE = "<<<END_PROPOSE_WORK>>>"

_BLOCK_PATTERN = re.compile(
    re.escape(SENTINEL_OPEN) + r"(.*?)" + re.escape(SENTINEL_CLOSE),
    re.DOTALL,
)


def parse_latest_proposed_work(agent_reply_text):
    """Return the last well-formed proposal dict in the reply, or None.

    None means "no parseable proposal present" — callers should leave any
    currently staged proposal untouched only if they choose to; the controller
    treats a successful parse as an overwrite and a None as "nothing new staged".
    """
    if not agent_reply_text:
        return None
    matches = _BLOCK_PATTERN.findall(agent_reply_text)
    for raw_block in reversed(matches):
        candidate = _try_load_json_object(raw_block)
        if candidate is not None:
            return candidate
    return None


def _try_load_json_object(raw_block):
    text = raw_block.strip()
    try:
        loaded = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(loaded, dict):
        return loaded
    return None
