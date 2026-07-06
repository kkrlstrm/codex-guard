# codex-guard

A tiny, stdlib-only **PreToolUse guard for the OpenAI Codex CLI** — the sibling of
[agent-guard](https://github.com/kkrlstrm/agent-guard) for Claude Code. It screens
every tool call *before it runs* and can **nudge**, **deny**, or **hard-block** it,
with a hash-chained tamper-evident audit trail.

## It works because Codex fires PreToolUse — verified, not assumed

On Codex `0.140.0-alpha.2` (VS Code extension), a `~/.codex/hooks.json` `PreToolUse`
command hook was measured to:

- fire for **`Bash`** (`tool_input.command` = the command) **and `apply_patch`**
  (`tool_input.command` = the patch) — not shell-only;
- **hard-block** a call when the hook returns **`exit 2`** (Codex shows the model
  *"Command blocked by PreToolUse hook: …"* and the tool never runs);
- **soft-deny** a call when the hook returns JSON
  `{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": …}}`;
- inject a non-blocking **`additionalContext`** nudge;

and the model **gracefully continued** after a block. Those are the exact three
mechanisms this guard emits — the same contract agent-guard uses on Claude Code,
so the engine ports unchanged.

## Two biases, one engine

- **fail-OPEN nudges** (`rules/starter.rules.json`) — for the main session. Rules
  that would fail anyway become non-blocking reminders; only a couple of
  irreversible patterns (`rm -rf /`) hard-block.
- **hard-BLOCK backstop** (`rules/readonly-db.rules.json`) — a read-only-DB
  firewall that blocks detected SQL mutations with `exit 2`. A backstop, not a
  true fail-closed boundary: the hook itself falls open on any guard error, so the
  durable guarantee is a **SELECT-only DB role**. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

Absolute invariant: **a guard bug must never wedge a session** — any unexpected
error falls open (`exit 0`).

## Install

```bash
python3 install.py                 # wire into ~/.codex/hooks.json (backed up, merge-aware)
python3 install.py --dry-run       # preview the hooks.json it would write
python3 install.py --uninstall     # remove just codex-guard's entry
```

Then **start a new Codex session** so the hook loads. Codex uses **trust-on-first-use**
for hooks (it records a `trusted_hash` in `config.toml`), so it may prompt you to
trust codex-guard once. Keep `pretooluse-guard.py` stable and put churn in the rules
JSON (which isn't hashed) to avoid re-prompts.

## Rules

A rule is JSON — a glob on `tool_name`, regexes on a `tool_input` field, an action,
and a message:

```json
{
  "id": "git-force-push-protected",
  "tool": "Bash",
  "any": ["\\bgit\\s+push\\b.*(--force|-f\\b).*\\b(main|master|prod)\\b"],
  "action": "nudge",
  "message": "Force-pushing a protected branch rewrites shared history…",
  "examples": {"should_fire": ["git push -f origin main"], "should_not_fire": ["git push origin main"]}
}
```

Actions: `nudge` (additionalContext, tool runs) · `deny` (permissionDecision deny) ·
`block` (exit 2) · `monitor` (log-only). Point `$CODEX_GUARD_RULES` at your own file
to override the starter set.

Validate any ruleset (runs each rule's `examples` as a mini-spec):

```bash
python3 bin/check_rules.py rules/starter.rules.json rules/readonly-db.rules.json
```

## Audit log

Every verdict is appended to a hash-chained JSONL at `~/.codex-guard/audit.jsonl`
(override with `$CODEX_GUARD_AUDIT`). Secrets are never stored verbatim — a SHA-256
plus a redacted preview.

```bash
python3 -m guard.audit tail       # last 20 verdicts
python3 -m guard.audit verify     # prove the chain wasn't altered
```

## Grow rules from your own telemetry (with codex-logger)

[codex-logger](https://github.com/kkrlstrm/codex-logger) records every Codex tool
call (with exit codes) from the rollout files. `derive_rules.py` reads its DB, finds
commands that fail repeatedly, and proposes log-only `monitor` rules to review:

```bash
python3 bin/derive_rules.py --db ~/.codex-logger/codex.db --days 14 --min-count 3
```

## Env toggles

| Var | Effect |
|---|---|
| `CODEX_GUARD_RULES` | main ruleset path (default `rules/starter.rules.json`) |
| `CODEX_GUARD_AUDIT` | audit-log path |
| `CODEX_GUARD_DRYRUN=1` | evaluate + audit, but never block/nudge (observe-only rollout) |
| `CODEX_GUARD_NUDGE_AS_BLOCK=1` | promote every nudge to a hard block |

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## What it does and doesn't protect

It catches obvious destructive **Bash** (rm -rf /, curl|sh, force-push, inline
secrets, bare psql), guards **apply_patch** writes to secret files, and hard-blocks
**DB mutations** for a read-only sub-agent. It does **not** stop obfuscated commands,
prompt injection, or a locally-compromised machine. It's a recoverability-first
seatbelt, not a sandbox. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
