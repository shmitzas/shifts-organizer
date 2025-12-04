from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Dict, List

from .config import parse_config
from .models import WeekPlan
from .scheduling import find_smallest_valid_pattern, write_csv, write_pivot_csv, write_pivot_xlsx


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Organize shifts into repeatable weekly patterns and output CSV")
    ap.add_argument("--config", required=True, help="Path to configuration JSON")
    ap.add_argument("--start", required=True, help="Start period in YYYY-MM (e.g., 2025-01)")
    ap.add_argument("--weeks", type=int, required=False, help="Total number of weeks to emit; defaults to repeat cycle length")
    ap.add_argument("--out", required=True, help="Output file path (.csv or .xlsx)")
    ap.add_argument("--format", choices=["csv", "xlsx"], help="Output format; defaults by file extension")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = parse_config(args.config)

    try:
        # Parse YYYY-MM and set to first day of month
        year_str, month_str = args.start.split("-")
        start_date = dt.date(int(year_str), int(month_str), 1)
    except ValueError:
        print("Error: --start must be in YYYY-MM format, e.g., 2025-01", file=sys.stderr)
        return 1
    

    shift_patterns: Dict[str, List[WeekPlan]] = {}
    pattern_lengths: List[int] = []
    for s in cfg.shifts:
        patterns = find_smallest_valid_pattern(s, cfg.rules, max_try_weeks=52)
        shift_patterns[s.name] = patterns
        pattern_lengths.append(len(patterns))
        print(f"Shift '{s.name}': repeating every {len(patterns)} weeks with {len(s.people)} members")

    # Determine total weeks: default to LCM of pattern lengths so full schedule repeats
    import math
    def lcm(a: int, b: int) -> int:
        return abs(a*b) // math.gcd(a, b) if a and b else 0

    if args.weeks is None:
        if not pattern_lengths:
            print("Error: No shifts configured", file=sys.stderr)
            return 1
        total_weeks = pattern_lengths[0]
        for pl in pattern_lengths[1:]:
            total_weeks = lcm(total_weeks, pl)
        print(f"Total weeks not provided; using repeat cycle length = {total_weeks} (LCM of shift patterns)")
    else:
        total_weeks = args.weeks

    # Pivot output to match spreadsheet-like format
    # Choose writer by format or extension
    fmt = args.format
    if not fmt:
        fmt = "xlsx" if args.out.lower().endswith(".xlsx") else "csv"

    if fmt == "xlsx":
        write_pivot_xlsx(args.out, total_weeks, shift_patterns, cfg)
    else:
        write_pivot_csv(args.out, total_weeks, shift_patterns, cfg)
    print(f"Schedule written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
