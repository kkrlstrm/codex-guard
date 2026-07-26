#!/usr/bin/env python3
"""Mine recurring Bash failures from codex-logger and emit candidate `monitor` rules.

This is the telemetry loop that ties codex-guard to codex-logger: the logger
records every tool call from Codex's rollout files (including exit codes), and
this reads the failures, finds commands that fail repeatedly, and proposes
log-only `monitor` rules. You review, tighten the regex + message, and graduate
the good ones to `nudge`/`block`. Nothing is ever auto-armed.

  python3 bin/derive_rules.py --db ~/.codex-logger/codex.db --days 14 --min-count 3
  python3 bin/derive_rules.py --db ~/.codex-logger/codex.db --out candidates.rules.json

Pure stdlib (sqlite3). Reads only; never writes to the logger DB.
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter


def _signature(command):
    """Collapse a command to a coarse signature: first 1-2 significant tokens."""
    toks = re.findall(r"[A-Za-z0-9_./-]+", command or "")
    toks = [t for t in toks if not re.fullmatch(r"[A-Z_]+=\S*", t)]  # drop VAR=val
    sig = " ".join(toks[:2]) if toks else ""
    return sig


def main(argv=None):
    ap = argparse.ArgumentParser(description="Derive candidate monitor rules from codex-logger failures")
    ap.add_argument("--db", default=os.path.expanduser("~/.codex-logger/codex.db"))
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--out", help="write candidates here (default: stdout)")
    a = ap.parse_args(argv)

    if not os.path.exists(a.db):
        print(f"! no codex-logger DB at {a.db}. Run `python3 -m codex_logger ingest` first.",
              file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(a.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        # Command-shaped tools ONLY, deliberately. codex-logger captures every tool
        # (apply_patch, update_plan, MCP, …) because it tails rollout files rather than
        # hooks, but this deriver produces command-PATTERN rules — it clusters on the
        # command string, which the others don't have.
        #
        # Do not broaden this to all tools without adding an exclusion set first. Read-
        # only/context tools fail constantly as ordinary behaviour (a missing file is the
        # agent checking whether it exists), clear any threshold, and would put the same
        # junk candidate in front of the reviewer every run. agent-guard hit exactly that
        # and now excludes them by default — see its docs/TELEMETRY.md.
        """SELECT arguments FROM tool_calls
           WHERE status='failure' AND tool_name IN ('exec_command','Bash')
             AND ts >= datetime('now', ?)""",
        (f"-{a.days} days",),
    ).fetchall()

    counts = Counter()
    for r in rows:
        try:
            args = json.loads(r["arguments"]) if r["arguments"] else {}
        except Exception:
            args = {}
        cmd = args.get("cmd") or args.get("command") or ""
        sig = _signature(cmd)
        if sig:
            counts[sig] += 1

    candidates = []
    for sig, n in counts.most_common():
        if n < a.min_count:
            break
        pattern = r"\b" + r"\s+".join(re.escape(t) for t in sig.split()) + r"\b"
        candidates.append({
            "id": "derived-" + re.sub(r"[^a-z0-9]+", "-", sig.lower()).strip("-"),
            "tool": "Bash",
            "any": [pattern],
            "severity": 30,
            "action": "monitor",
            "message": f"'{sig}' failed {n}x in the last {a.days}d — candidate guard. "
                       "Tighten this regex + message and graduate to nudge if it's a real footgun.",
            "meta": {"why": "telemetry-derived from codex-logger failures; monitor-only until reviewed.",
                     "count": n, "days": a.days},
        })

    out = {"ruleset": "derived-candidates", "bias": "monitor-only", "rules": candidates}
    text = json.dumps(out, indent=2) + "\n"
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
        print(f"wrote {len(candidates)} candidate rule(s) -> {a.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
