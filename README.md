# codex-guard

<!-- portfolio-status -->
**Status:** Production-used — I run this against my own live agent workflows. · **Layer:** Policy and guardrails · **[Portfolio map ›](https://github.com/kkrlstrm)**

> **Now part of [callusguard](https://github.com/kkrlstrm/callusguard).**
> codex-guard is the Codex half of the `guard` stage in a five-stage loop —
> `record → derive → guard → verify → prune`. callusguard adds rule derivation from your own
> telemetry, scope verification, and pruning of rules that have stopped firing, and ships all
> five stages for Claude Code as well as Codex, as one install. This repo stays up and works;
> callusguard is the maintained guardrail package; the wider learning loop, which also proposes skills, sub-agents and routes and measures each change against a control, continues in [runtune](https://github.com/kkrlstrm/runtune).

**Recoverability-first runtime controls for the OpenAI Codex CLI.**

codex-guard sits between Codex and the tools it's about to run. Every `Bash` command
and `apply_patch` edit passes through a `PreToolUse` hook first, where codex-guard can
do one of four things:

- **monitor** the call for audit only,
- **nudge** Codex with additional context and let the tool run,
- **deny** the call with a recoverable permission decision, or
- **block** the call with `exit 2` before it executes.

The goal isn't to sandbox Codex. It's to make agentic coding more recoverable — fail
open by default, block only irreversible damage, and keep a tamper-evident audit trail
of every verdict. It's the sibling of
[agent-guard](https://github.com/kkrlstrm/agent-guard) for Claude Code; the engine ports
unchanged.

## Why this exists

Codex now executes real commands, patches files, touches secrets, mutates databases, and
breaks local and dev environments. Static prompts aren't enough for that — you want
runtime controls that sit between the model and the tool call.

Most agent guardrails get written before you know what the agent will actually do.
codex-guard is meant to be *grown from real telemetry* instead: watch what Codex actually
tries, find the recurring failure patterns, start them as monitor-only rules, promote the
useful ones into nudges, and reserve hard blocks for irreversible operations. That's the
wedge — pair it with [codex-logger](https://github.com/kkrlstrm/codex-logger) and you have
the enforcement half of a Codex observability loop:

> codex-logger shows you what Codex actually does. codex-guard turns what you learn into
> runtime controls.

## How it works

A `~/.codex/hooks.json` `PreToolUse` command hook routes each tool call through
`pretooluse-guard.py`, which matches it against your rulesets and emits one of the four
actions above. In practice that means Codex can learn from the mistakes your sessions
actually make: bare `psql` calls that fail, risky `curl | sh` installs, force-pushes to
protected branches, edits to secret files, and SQL mutations from a read-only workflow.

Absolute invariant: **a guard bug must never wedge a session.** Any unexpected error falls
open (`exit 0`).

<details>
<summary><b>It works because Codex fires PreToolUse — verified, not assumed</b></summary>

On Codex `0.140.0-alpha.2` (VS Code extension), a `PreToolUse` command hook was measured to:

- fire for **`Bash`** (`tool_input.command` = the command) **and `apply_patch`**
  (`tool_input.command` = the patch) — not shell-only;
- **hard-block** a call when the hook returns **`exit 2`** (Codex shows the model
  *"Command blocked by PreToolUse hook: …"* and the tool never runs);
- **soft-deny** a call when the hook returns JSON
  `{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": …}}`;
- inject a non-blocking **`additionalContext`** nudge;

and the model **gracefully continued** after a block. Those are the exact mechanisms this
guard emits — the same contract agent-guard uses on Claude Code.
</details>

## The telemetry loop with codex-logger

[codex-logger](https://github.com/kkrlstrm/codex-logger) records every Codex tool call
(with exit codes) from the rollout files. `derive_rules.py` reads its DB, finds commands
that fail repeatedly, and proposes log-only `monitor` rules for you to review before you
promote any of them:

```bash
python3 bin/derive_rules.py --db ~/.codex-logger/codex.db --days 14 --min-count 3
```

Log real behavior → find repeated failures → derive candidate rules → review → promote the
useful ones into nudges or blocks. Rules earn their way up the ladder.

## Default safety posture

Two biases, one engine:

- **Main-session mode — fail-open nudges** (`rules/starter.rules.json`). Help Codex
  self-correct without interrupting flow. Rules that would fail anyway become non-blocking
  reminders (`curl | sh`, protected-branch force-pushes, inline secrets, bare `psql`,
  secret-file patches); a couple of irreversible patterns like `rm -rf /` hard-block.
- **Backstop mode — hard blocks** (`rules/readonly-db.rules.json`). A read-only-DB firewall
  that blocks detected SQL mutations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`,
  `CREATE`, `GRANT`, `REVOKE`, `COPY FROM`, `VACUUM`, stored-procedure calls) with `exit 2`.

The philosophy: **use nudges where the model can recover; use blocks where the action
violates the role.** The backstop is a backstop, not a true fail-closed boundary — the hook
itself falls open on any guard error, so the durable guarantee for a read-only workflow is a
`SELECT`-only DB role. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Install

```bash
python3 install.py                 # wire into ~/.codex/hooks.json (backed up, merge-aware)
python3 install.py --dry-run       # preview the hooks.json it would write
python3 install.py --uninstall     # remove just codex-guard's entry
```

Then **start a new Codex session** so the hook loads. Codex uses trust-on-first-use for
hooks (it records a `trusted_hash` in `config.toml`), so it may prompt you to trust
codex-guard once. Keep `pretooluse-guard.py` stable and put churn in the rules JSON (which
isn't hashed) to avoid re-prompts.

## Rules

A rule is JSON — a glob on `tool_name`, regexes on a `tool_input` field, an action, and a
message:

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
`block` (exit 2) · `monitor` (log-only). Point `$CODEX_GUARD_RULES` at your own file to
override the starter set.

Validate any ruleset (runs each rule's `examples` as a mini-spec):

```bash
python3 bin/check_rules.py rules/starter.rules.json rules/readonly-db.rules.json
```

## Audit log

Every verdict is appended to a hash-chained JSONL at `~/.codex-guard/audit.jsonl`
(override with `$CODEX_GUARD_AUDIT`). Secrets are never stored verbatim — a SHA-256 plus a
redacted preview.

```bash
python3 -m guard.audit tail       # last 20 verdicts
python3 -m guard.audit verify     # prove the chain wasn't altered
```

## Env toggles

| Var | Effect |
|---|---|
| `CODEX_GUARD_RULES` | main ruleset path (default `rules/starter.rules.json`) |
| `CODEX_GUARD_AUDIT` | audit-log path |
| `CODEX_GUARD_DRYRUN=1` | evaluate + audit, but never block/nudge (observe-only rollout) |
| `CODEX_GUARD_NUDGE_AS_BLOCK=1` | promote every nudge to a hard block |

## Threat model

codex-guard reduces *preventable* damage in Codex sessions; it doesn't secure them. It
catches obvious destructive `Bash` (`rm -rf /`, `curl | sh`, force-push, inline secrets,
bare `psql`), guards `apply_patch` writes to secret files, and hard-blocks DB mutations for
a read-only workflow. It does **not** stop obfuscated commands, prompt injection, a
determined agent, or a locally-compromised machine, and it falls open on its own errors by
design. It's a recoverability-first seatbelt, not a sandbox. Full model in
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

---

<!-- portfolio-footer -->
## Where this fits

Part of a portfolio of **governed, AI-native GTM systems** — reference implementations and reusable patterns extracted from a private production stack. In that system this is the recovery-first control surface for the Codex CLI.

**Full portfolio map → [github.com/kkrlstrm](https://github.com/kkrlstrm)**

Works with:
- [codex-logger](https://github.com/kkrlstrm/codex-logger) — supplies the telemetry
- [agent-guard](https://github.com/kkrlstrm/agent-guard) — the Claude Code sibling; the engine ports unchanged
