from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Dict, List

from .config import parse_config
from .models import WeekPlan
from .scheduling import find_smallest_valid_pattern, write_csv, write_pivot_csv, write_pivot_xlsx, allocate_week_pattern, _pattern_meets_mins


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Organize shifts into repeatable weekly patterns and output CSV")
    ap.add_argument("--config", required=True, help="Path to configuration JSON")
    ap.add_argument("--start", required=True, help="Start period in YYYY-MM (e.g., 2025-01)")
    ap.add_argument("--weeks", type=int, required=False, help="Total number of weeks to emit; defaults to repeat cycle length")
    ap.add_argument("--max-weeks", type=int, required=False, default=10, help="Maximum weeks to search for a valid repeating pattern (default 10)")
    ap.add_argument("--out", required=True, help="Output file path (extension will be determined by --format)")
    ap.add_argument("--format", required=True, choices=["csv", "xlsx"], help="Output format")
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
    
    # Global tracking for equal hours across ALL shifts
    global_pattern_hours: Dict[str, float] = {}
    global_weekend_counts: Dict[str, int] = {}
    
    # If require_equal_hours is enabled, we need to coordinate across all shifts
    if hasattr(cfg.rules, 'require_equal_hours') and cfg.rules.require_equal_hours:
        # Initialize global tracking with all people from all shifts
        for s in cfg.shifts:
            for p in s.people:
                global_pattern_hours[p] = 0.0
                global_weekend_counts[p] = 0
        
        # Find the maximum pattern length needed across all shifts
        max_pattern_weeks = args.max_weeks
        for trial_weeks in range(2, max_pattern_weeks + 1):
            shift_patterns = {}
            pattern_lengths = []
            # Reset global tracking for this trial
            for p in global_pattern_hours:
                global_pattern_hours[p] = 0.0
                global_weekend_counts[p] = 0
            
            success = True
            for s in cfg.shifts:
                try:
                    patterns = allocate_week_pattern(s, cfg.rules, trial_weeks, global_pattern_hours, global_weekend_counts)
                    if not _pattern_meets_mins(patterns, s):
                        success = False
                        break
                    shift_patterns[s.name] = patterns
                    pattern_lengths.append(len(patterns))
                except ValueError:
                    success = False
                    break
            
            if success:
                # Check if all people have equal hours across ALL shifts
                if global_pattern_hours:
                    hours_values = list(global_pattern_hours.values())
                    # Calculate average hours per week
                    avg_hours = {p: h / trial_weeks for p, h in global_pattern_hours.items()}
                    min_avg = min(avg_hours.values())
                    max_avg = max(avg_hours.values())
                    
                    if max_avg - min_avg <= 0.5:
                        # Success! All people have equal hours
                        for s in cfg.shifts:
                            print(f"Shift '{s.name}': repeating every {len(shift_patterns[s.name])} weeks with {len(s.people)} members")
                        print(f"All people work equal hours: {min_avg:.1f}h/week average")
                        break
                    else:
                        print(f"Pattern {trial_weeks} weeks: hours not equal (min={min_avg:.1f}, max={max_avg:.1f}), trying longer...")
        else:
            print("Warning: Could not find pattern with equal hours across all shifts within max weeks")
    else:
        # Original behavior: each shift independently
        for s in cfg.shifts:
            patterns = find_smallest_valid_pattern(s, cfg.rules, max_try_weeks=args.max_weeks)
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

    # Add extension based on format if not present
    import os
    out_path = args.out
    base, ext = os.path.splitext(out_path)
    
    # Remove extension if present and add the correct one based on format
    if ext.lower() in ['.csv', '.xlsx']:
        out_path = base
    
    out_path = f"{out_path}.{args.format}"

    # Pivot output to match spreadsheet-like format
    if args.format == "xlsx":
        write_pivot_xlsx(out_path, total_weeks, shift_patterns, cfg)
    else:
        write_pivot_csv(out_path, total_weeks, shift_patterns, cfg)
    print(f"Schedule written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
