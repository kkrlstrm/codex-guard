#!/usr/bin/env python3
"""Install codex-guard into ~/.codex/hooks.json (or a chosen CODEX_HOME).

Wires the PreToolUse hook to pretooluse-guard.py so every Bash / apply_patch tool
call is screened. Merge-aware (won't clobber other hooks), idempotent (re-running
updates in place), and it backs up any existing hooks.json first.

  python3 install.py                 # install / update
  python3 install.py --dry-run       # print what would be written, change nothing
  python3 install.py --uninstall     # remove only codex-guard's hook entry
  python3 install.py --codex-home /path/to/.codex   # non-default location

Note on Codex trust-on-first-use: Codex records a `trusted_hash` for each hook in
config.toml and may prompt you to trust codex-guard the first time a session
starts. Keep pretooluse-guard.py stable (put churn in the rules JSON, which isn't
hashed) so you're not re-prompted on every rules edit.
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD_CMD = f'{sys.executable} "{os.path.join(HERE, "pretooluse-guard.py")}"'
MARKER = "pretooluse-guard.py"  # how we recognize our own entry


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"! existing {path} is not valid JSON ({e}); refusing to overwrite. "
              "Fix or move it, then re-run.", file=sys.stderr)
        sys.exit(1)


def _our_entry():
    return {
        "matcher": ".*",
        "hooks": [{
            "type": "command",
            "command": GUARD_CMD,
            "statusMessage": "codex-guard screening tool call",
            "timeout": 15,
        }],
    }


def _strip_ours(pretool_list):
    """Drop any existing codex-guard entries (by marker) so we can re-add cleanly."""
    kept = []
    for group in pretool_list:
        hooks = [h for h in group.get("hooks", []) if MARKER not in (h.get("command") or "")]
        if hooks:
            group = dict(group)
            group["hooks"] = hooks
            kept.append(group)
        elif not group.get("hooks"):
            kept.append(group)  # preserve a (weird) empty group untouched
    return kept


def main(argv=None):
    ap = argparse.ArgumentParser(description="Install codex-guard's PreToolUse hook")
    ap.add_argument("--codex-home", default=os.path.expanduser("~/.codex"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args(argv)

    hooks_path = os.path.join(a.codex_home, "hooks.json")
    doc = _load(hooks_path)
    hooks = doc.setdefault("hooks", {}) if isinstance(doc, dict) else {}
    pre = hooks.get("PreToolUse", [])
    if not isinstance(pre, list):
        pre = []

    pre = _strip_ours(pre)                       # remove any prior codex-guard entry
    if not a.uninstall:
        pre.append(_our_entry())                 # add the current one
    if pre:
        hooks["PreToolUse"] = pre
    elif "PreToolUse" in hooks:
        del hooks["PreToolUse"]
    doc["hooks"] = hooks

    rendered = json.dumps(doc, indent=2) + "\n"
    action = "uninstall" if a.uninstall else "install"
    if a.dry_run:
        print(f"# --dry-run ({action}) — would write {hooks_path}:\n")
        print(rendered)
        return

    os.makedirs(a.codex_home, exist_ok=True)
    if os.path.exists(hooks_path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = f"{hooks_path}.bak-{stamp}"
        shutil.copy2(hooks_path, backup)
        print(f"backed up existing hooks.json -> {backup}")

    with open(hooks_path, "w") as f:
        f.write(rendered)

    if a.uninstall:
        print(f"codex-guard removed from {hooks_path}")
    else:
        print(f"codex-guard installed -> {hooks_path}")
        print("  guarded: PreToolUse (Bash + apply_patch + MCP), rules/starter.rules.json")
        print("  audit log: ~/.codex-guard/audit.jsonl  (python3 -m guard.audit tail)")
        print("  NOTE: start a NEW Codex session to load the hook; Codex may prompt once")
        print("        to trust codex-guard (trust-on-first-use).")


if __name__ == "__main__":
    main()
