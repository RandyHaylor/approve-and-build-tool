"""approve-and-build-tool: a propose -> approve -> bounded-fork-applies -> commit loop.

A read-and-web-only "primary" Claude session converses with the user and emits
structured PROPOSE_WORK blocks. Nothing it says can touch the repo. On approval,
a context-fork of that session runs with write tools but no git access, applies
ONLY the proposed work, and the tool (never the agent) commits the result on a
local session branch. See README.md for the loop.
"""
