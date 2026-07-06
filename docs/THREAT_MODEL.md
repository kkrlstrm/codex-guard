# Threat model

codex-guard is a **recoverability-first seatbelt**, not a sandbox. It screens
Codex tool calls at the `PreToolUse` hook and biases toward *not* wedging your
session. Be clear about what that does and doesn't buy you.

## What it protects against

- **Obvious destructive shell** — `rm -rf /`/`~`/`$HOME` (hard block), `curl|sh`,
  force-pushing a protected branch, inline secrets in a command, bare `psql` that
  will just fail. Nudges let the model self-correct; only irreversible deletes block.
- **apply_patch writes to secret files** — because Codex fires `PreToolUse` for
  `apply_patch` too, a patch that adds/updates `.env`, a private key, or
  `credentials.*` gets a nudge before it lands.
- **DB mutations from a read-only analyst sub-agent** — the `readonly-db` ruleset
  hard-blocks INSERT/UPDATE/DELETE/DDL/DCL with `exit 2`.

## What it does NOT protect against

- **Obfuscated intent** — base64-piped commands, `eval "$(…)"`, a mutation built by
  string concatenation, SQL hidden in a script file the command merely executes.
  Regexes see the command text, not its runtime effect.
- **Prompt injection / a determined agent** — the guard rules on the *command*, not
  on *why* the model wants to run it.
- **A locally compromised machine** — the audit log is tamper-*evident* (hash-chained)
  but not tamper-*proof*: anyone who can write the file can recompute the chain from
  genesis. There's no external anchor.
- **The guard failing open** — by design, any error in the hook (bad rules file,
  malformed payload, a bug) results in `exit 0` (allow). A guard that blocks on its
  own bugs is worse than no guard. This means enforcement is best-effort.

## The durable guarantees live elsewhere

- For **read-only DB access**, the real boundary is a **SELECT-only Postgres role**,
  not the regex backstop. Use the role; the ruleset is defense-in-depth.
- For **irreversible ops**, prefer reversible workflows (feature branch + PR over
  force-push; a scoped path over `rm -rf`).

## Codex-specific notes

- Hooks are discovered from **config layers** (`~/.codex/hooks.json` / `config.toml`),
  **not** from skill or agent manifests — so a hook applies to the whole session, you
  can't scope one to a single sub-agent via its manifest (unlike Claude Code's
  sub-agent frontmatter). Scope by rules, not by wiring.
- Codex uses **trust-on-first-use**: it records a `trusted_hash` per hook. Changing
  `pretooluse-guard.py` re-triggers a trust prompt; changing the rules JSON does not.
- `PreToolUse` is confirmed for `Bash` + `apply_patch` on 0.140. MCP-tool coverage
  is plausible (matchers accept `mcp__*`) but was not exercised in the probe — verify
  before relying on it.
