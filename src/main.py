from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Dict, List

from .config import parse_config
from .models import WeekPlan
from .scheduling import find_smallest_valid_pattern, write_csv


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Organize shifts into repeatable weekly patterns and output CSV")
    ap.add_argument("--config", required=True, help="Path to configuration JSON")
    ap.add_argument("--start", required=True, help="Start date (ISO, e.g., 2025-01-06 Monday)")
    ap.add_argument("--weeks", type=int, required=True, help="Total number of weeks to emit")
    ap.add_argument("--out", required=True, help="Output CSV path")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = parse_config(args.config)

    try:
        start_date = dt.date.fromisoformat(args.start)
    except ValueError:
        print("Error: --start must be an ISO date, e.g., 2025-01-06", file=sys.stderr)
        return 1
    if start_date.weekday() != 0:
        print("Warning: Start date is not Monday; weekly rows will begin mid-week.", file=sys.stderr)

    shift_patterns: Dict[str, List[WeekPlan]] = {}
    for s in cfg.shifts:
        patterns = find_smallest_valid_pattern(s, cfg.rules, max_try_weeks=24)
        shift_patterns[s.name] = patterns
        print(f"Shift '{s.name}': repeating every {len(patterns)} weeks with {len(s.people)} members")

    write_csv(args.out, start_date, args.weeks, shift_patterns)
    print(f"Schedule written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
