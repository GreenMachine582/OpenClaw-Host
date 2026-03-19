#!/usr/bin/env python3
# scripts/logs.py
# Log utilities — tail, filter by level/date, export, and prune old logs.
#
# Usage:
#   python scripts/logs.py tail [--lines N]
#   python scripts/logs.py filter --level ERROR [--since YYYY-MM-DD]
#   python scripts/logs.py export [--output FILE]
#   python scripts/logs.py prune [--days N]

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path("storage/logs")
LEVELS = {"DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL"}


def find_log_files() -> list[Path]:
    if not LOG_DIR.exists():
        print(f"Log directory not found: {LOG_DIR}", file=sys.stderr)
        sys.exit(1)
    files = sorted(LOG_DIR.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print("No log files found.")
        sys.exit(0)
    return files


def parse_line(line: str) -> dict | None:
    """Attempt to parse a JSON log line; fall back to raw."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line}


def format_line(entry: dict) -> str:
    if "raw" in entry:
        return entry["raw"]
    ts = entry.get("timestamp", entry.get("time", ""))
    level = entry.get("level", "").upper()
    msg = entry.get("message", entry.get("msg", ""))
    extra = {k: v for k, v in entry.items() if k not in ("timestamp", "time", "level", "message", "msg")}
    line = f"{ts} [{level}] {msg}"
    if extra:
        line += f"  {extra}"
    return line


def cmd_tail(args):
    files = find_log_files()
    lines = []
    for f in files:
        with open(f) as fh:
            lines.extend(fh.readlines())
    for line in lines[-args.lines:]:
        entry = parse_line(line)
        if entry:
            print(format_line(entry))


def cmd_filter(args):
    since = datetime.fromisoformat(args.since) if args.since else None
    level_filter = args.level.upper() if args.level else None

    for f in find_log_files():
        with open(f) as fh:
            for line in fh:
                entry = parse_line(line)
                if not entry:
                    continue
                if level_filter:
                    if entry.get("level", "").upper() != level_filter:
                        continue
                if since:
                    ts_str = entry.get("timestamp", entry.get("time", ""))
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ts < since:
                            continue
                    except (ValueError, TypeError):
                        pass
                print(format_line(entry))


def cmd_export(args):
    output = Path(args.output) if args.output else Path(f"logs-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
    count = 0
    with open(output, "w") as out:
        for f in find_log_files():
            with open(f) as fh:
                for line in fh:
                    out.write(line)
                    count += 1
    print(f"Exported {count} lines to {output}")


def cmd_prune(args):
    cutoff = datetime.now() - timedelta(days=args.days)
    pruned = 0
    for f in find_log_files():
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            print(f"Removing {f} (last modified {mtime.date()})")
            f.unlink()
            pruned += 1
    print(f"Pruned {pruned} file(s) older than {args.days} days.")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw log utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    p_tail = sub.add_parser("tail", help="Print the last N log lines")
    p_tail.add_argument("--lines", type=int, default=50)

    p_filter = sub.add_parser("filter", help="Filter logs by level and/or date")
    p_filter.add_argument("--level", choices=[l.lower() for l in LEVELS], help="Log level to filter by")
    p_filter.add_argument("--since", help="Show entries on or after this date (YYYY-MM-DD)")

    p_export = sub.add_parser("export", help="Export all logs to a single file")
    p_export.add_argument("--output", help="Output file path (default: timestamped filename)")

    p_prune = sub.add_parser("prune", help="Delete log files older than N days")
    p_prune.add_argument("--days", type=int, default=30)

    args = parser.parse_args()
    {"tail": cmd_tail, "filter": cmd_filter, "export": cmd_export, "prune": cmd_prune}[args.command](args)


if __name__ == "__main__":
    main()
