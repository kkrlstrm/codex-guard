"""codex-guard — a tiny, stdlib-only policy engine for OpenAI Codex CLI PreToolUse hooks.

The Codex sibling of agent-guard. Codex fires a `PreToolUse` hook before every
Bash and apply_patch tool call (verified on 0.140.0-alpha.2), passing the tool
name + input on stdin, and honors two block mechanisms the same way Claude Code
does: `exit 2` (hard block, reason via stderr) and a JSON
`{"hookSpecificOutput": {"permissionDecision": "deny", ...}}` (soft deny). It
also injects `additionalContext` for non-blocking nudges. codex-guard reuses
agent-guard's engine unchanged and speaks that contract.

Two enforcement biases, one engine:
  - fail-OPEN nudges: telemetry-driven reminders injected as additionalContext;
  - hard-BLOCK backstop: a read-only-DB firewall (blocks detected DB mutations
    with exit 2). A backstop, not a true fail-closed boundary — the hook itself
    falls open on any guard error, so the durable guarantee is a SELECT-only DB
    role. See docs/THREAT_MODEL.md.

Rules live in JSON (see ../rules/*.rules.json); each verdict is appended to a
hash-chained, tamper-evident audit log (see audit.py). Absolute invariant: a
guard bug must never wedge a session — any unexpected error falls open (exit 0).
"""

__version__ = "0.1.0"
