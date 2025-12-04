"""
Shift Organizer

Generates repeatable weekly shift patterns based on configuration described in README.md
and outputs a CSV schedule. The number of week variations is automatically determined
to satisfy constraints; the schedule then repeats every N weeks.
"""

from __future__ import annotations

"""
Deprecated: Use the modular CLI in src/main.py

Convenience wrapper to maintain backward compatibility.
"""

import argparse
import datetime as dt
import sys
from typing import Dict, List

from src.config import parse_config
from src.models import WeekPlan
from src.scheduling import find_smallest_valid_pattern, write_pivot_csv, write_pivot_xlsx


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Organize shifts into repeatable weekly patterns and output CSV")
    ap.add_argument("--config", required=True, help="Path to configuration JSON")
    ap.add_argument("--start", required=True, help="Start date (ISO, e.g., 2025-01-06 Monday)")
    ap.add_argument("--weeks", type=int, required=False, help="Total number of weeks to emit; defaults to repeat cycle length")
    ap.add_argument("--max-weeks", type=int, required=False, default=10, help="Maximum weeks to search for a valid repeating pattern (default 10)")
    ap.add_argument("--out", required=True, help="Output file path (.csv or .xlsx)")
    ap.add_argument("--format", choices=["csv", "xlsx"], help="Output format; defaults by file extension")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = parse_config(args.config)

    try:
        year_str, month_str = args.start.split("-")
        start_date = dt.date(int(year_str), int(month_str), 1)
    except Exception:
        print("Error: --start must be in YYYY-MM format, e.g., 2025-01", file=sys.stderr)
        return 1

    shift_patterns: Dict[str, List[WeekPlan]] = {}
    pattern_lengths: List[int] = []
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
"""
Shift Organizer

Generates repeatable weekly shift patterns based on configuration described in README.md
and outputs a CSV schedule. The number of week variations is automatically determined
to satisfy constraints; the schedule then repeats every N weeks.

Usage:
    python scheduler.py --config config.json --start 2025-01-06 --weeks 12 --out schedule.csv

Config format (JSON):
{
  "shifts": [
    {
      "name": "Shift 1",
      "people": ["Alice", "Bob", "Charlie"],
      "timezone": "EET",
      "day_shift": {"start": "09:00", "end": "18:00"},
      "night_shift": {"start": "17:00", "end": "02:00"},
      "wednesday_day_overfill_count": 2,
      "prefer_two_or_more_in_shift": true
    },
    {
      "name": "Shift 2",
      "people": ["Dina", "Evan"],
      "timezone": "GMT+7",
      "day_shift": {"start": "09:00", "end": "18:00"},
      "night_shift": {"start": "17:00", "end": "02:00"},
      "wednesday_day_overfill_count": 2,
      "prefer_two_or_more_in_shift": true
    }
  ],
  "rules": {
    "max_day_in_row": 5,
    "max_night_in_row": 5,
    "max_days_off": 2,
    "min_days_off": 1,
    "no_day_after_night": true,
    "friday_shift2_priority_names": ["Dina"],
    "wednesday_day_overfill": true
  }
}

Notes:
- Output columns: week_index, date, weekday, shift_name, shift_type, members
- The algorithm tries to balance day/night/off per person while respecting constraints.
- The script computes the smallest pattern length N that satisfies constraints for all shifts.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import json
import math
import sys
from typing import List, Dict, Optional, Tuple

# ------------------------------
# Data models
# ------------------------------

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

@dataclasses.dataclass(frozen=True)
class TimeRange:
    start: str  # "HH:MM"
    end: str    # "HH:MM"

@dataclasses.dataclass
class ShiftConfig:
    name: str
    people: List[str]
    timezone: str
    day_shift: TimeRange
    night_shift: TimeRange
    wednesday_day_overfill_count: int
    prefer_two_or_more_in_shift: bool

@dataclasses.dataclass
class RulesConfig:
    max_day_in_row: int
    max_night_in_row: int
    max_days_off: int
    min_days_off: int
    no_day_after_night: bool
    friday_shift2_priority_names: List[str]
    wednesday_day_overfill: bool

@dataclasses.dataclass
class Config:
    shifts: List[ShiftConfig]
    rules: RulesConfig

# ------------------------------
# Parsing and validation
# ------------------------------

def parse_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    shifts: List[ShiftConfig] = []
    for s in raw.get("shifts", []):
        shifts.append(ShiftConfig(
            name=s["name"],
            people=list(s["people"]),
            timezone=s["timezone"],
            day_shift=TimeRange(**s["day_shift"]),
            night_shift=TimeRange(**s["night_shift"]),
            wednesday_day_overfill_count=int(s.get("wednesday_day_overfill_count", 0)),
            prefer_two_or_more_in_shift=bool(s.get("prefer_two_or_more_in_shift", False))
        ))
    rules_raw = raw.get("rules", {})
    rules = RulesConfig(
        max_day_in_row=int(rules_raw.get("max_day_in_row", 5)),
        max_night_in_row=int(rules_raw.get("max_night_in_row", 5)),
        max_days_off=int(rules_raw.get("max_days_off", 2)),
        min_days_off=int(rules_raw.get("min_days_off", 1)),
        no_day_after_night=bool(rules_raw.get("no_day_after_night", True)),
        friday_shift2_priority_names=list(rules_raw.get("friday_shift2_priority_names", [])),
        wednesday_day_overfill=bool(rules_raw.get("wednesday_day_overfill", True)),
    )

    cfg = Config(shifts=shifts, rules=rules)
    validate_config(cfg)
    return cfg

def validate_config(cfg: Config) -> None:
    if not cfg.shifts:
        raise ValueError("Config must contain at least one shift")

    for s in cfg.shifts:
        if not s.people:
            raise ValueError(f"Shift '{s.name}' must have at least one person")
        if s.wednesday_day_overfill_count < 0:
            raise ValueError(f"Shift '{s.name}' wednesday_day_overfill_count must be >= 0")
        _validate_time(s.day_shift.start)
        _validate_time(s.day_shift.end)
        _validate_time(s.night_shift.start)
        _validate_time(s.night_shift.end)

    r = cfg.rules
    if r.min_days_off < 0 or r.max_days_off < 0:
        raise ValueError("Days off must be non-negative")
    if r.min_days_off > r.max_days_off:
        raise ValueError("min_days_off cannot exceed max_days_off")
    if r.max_day_in_row <= 0 or r.max_night_in_row <= 0:
        raise ValueError("max_day_in_row and max_night_in_row must be positive")

def _validate_time(t: str) -> None:
    try:
        dt.datetime.strptime(t, "%H:%M")
    except ValueError:
        raise ValueError(f"Invalid time format '{t}', expected HH:MM")

# ------------------------------
# Scheduling
# ------------------------------

# Assignment enums
DAY = "DAY"
NIGHT = "NIGHT"
OFF = "OFF"

@dataclasses.dataclass
class PersonState:
    name: str
    streak_type: Optional[str] = None  # DAY/NIGHT/OFF
    streak_len: int = 0
    last_assignment: Optional[str] = None

    def can_assign(self, assign: str, rules: RulesConfig) -> bool:
        # Respect streak limits
        if assign == DAY:
            if self.streak_type == DAY and self.streak_len >= rules.max_day_in_row:
                return False
            if rules.no_day_after_night and self.last_assignment == NIGHT:
                return False
        if assign == NIGHT:
            if self.streak_type == NIGHT and self.streak_len >= rules.max_night_in_row:
                return False
        if assign == OFF:
            # OFF limits are weekly-checked; allow OFF here and validate aggregate later
            pass
        return True

    def apply(self, assign: str) -> None:
        if self.streak_type == assign:
            self.streak_len += 1
        else:
            self.streak_type = assign
            self.streak_len = 1
        self.last_assignment = assign

@dataclasses.dataclass
class DayPlan:
    weekday_index: int  # 0..6
    assignments: Dict[str, List[str]]  # {DAY: [names], NIGHT: [names], OFF: [names]}

@dataclasses.dataclass
class WeekPlan:
    week_index: int  # pattern index
    days: List[DayPlan]  # length 7

def compute_min_pattern_weeks(people_count: int, rules: RulesConfig) -> int:
    """
    Heuristic lower bound: Need enough weeks so min/max OFF and day/night streaks
    can be satisfied. Start from 2 and grow until feasible.
    """
    # Base bound: ensure room for min days off while also covering day/night slots.
    base = 2
    # Increase if off constraints tight compared to prefer_two_or_more requirement
    # Not strictly provable; we will attempt patterns and increase until valid.
    return base

def target_daily_staff_count(shift: ShiftConfig, weekday_index: int) -> int:
    """
    Preferred number of staffed persons per DAY/NIGHT shift for each weekday.
    """
    prefer_two = 2 if shift.prefer_two_or_more_in_shift else 1
    # Overfill Wednesday for DAY shift only
    if weekday_index == 2 and shift.wednesday_day_overfill_count > 0:
        return max(prefer_two, shift.wednesday_day_overfill_count)
    return prefer_two

def allocate_week_pattern(shift: ShiftConfig, rules: RulesConfig, pattern_weeks: int) -> List[WeekPlan]:
    """
    Build a pattern of 'pattern_weeks' distinct weekly schedules that satisfy constraints.
    The pattern is then repeatable.
    """
    people = list(shift.people)
    person_states: Dict[str, PersonState] = {p: PersonState(name=p) for p in people}

    week_patterns: List[WeekPlan] = []

    # Determine daily staffing targets for both DAY and NIGHT
    # We use same count for NIGHT as DAY unless Friday priority applies.
    for w in range(pattern_weeks):
        days: List[DayPlan] = []
        # Reset per-week OFF counters for validation
        off_counter: Dict[str, int] = {p: 0 for p in people}

        for d in range(7):
            day_count = target_daily_staff_count(shift, d)
            night_count = target_daily_staff_count(shift, d)

            # Friday priority for Shift 2 (by name match)
            is_friday = (d == 4)
            priority_names = rules.friday_shift2_priority_names if shift.name.lower() == "shift 2" else []

            # Rank candidates for DAY/NIGHT considering constraints and fairness
            def rank_candidates(assign_type: str) -> List[str]:
                # Score: lower streak_len preferred unless same assign_type; also rotate fairly by name order
                scored: List[Tuple[str, float]] = []
                for p in people:
                    st = person_states[p]
                    if not st.can_assign(assign_type, rules):
                        continue
                    # penalize long streaks of same type
                    penalty = st.streak_len if st.streak_type == assign_type else 0
                    # prefer priority names on Friday for night/day respectively if provided
                    bonus = 0
                    if is_friday and p in priority_names:
                        bonus = -2
                    scored.append((p, penalty + (0 if st.last_assignment != assign_type else 0.5) - bonus))
                scored.sort(key=lambda x: (x[1], x[0]))
                return [p for p, _ in scored]

            day_members: List[str] = rank_candidates(DAY)[:day_count]
            # Mark DAY assignments
            for p in day_members:
                person_states[p].apply(DAY)

            # Exclude from night if already assigned day
            night_candidates = [p for p in people if p not in day_members]
            # Temporarily compute ranking for night using a snapshot
            def rank_night(cands: List[str]) -> List[str]:
                scored: List[Tuple[str, float]] = []
                for p in cands:
                    st = person_states[p]
                    if not st.can_assign(NIGHT, rules):
                        continue
                    penalty = st.streak_len if st.streak_type == NIGHT else 0
                    scored.append((p, penalty + (0 if st.last_assignment != NIGHT else 0.5)))
                scored.sort(key=lambda x: (x[1], x[0]))
                return [p for p, _ in scored]

            night_members = rank_night(night_candidates)[:night_count]
            for p in night_members:
                person_states[p].apply(NIGHT)

            # Remaining are OFF
            off_members = [p for p in people if p not in day_members and p not in night_members]
            for p in off_members:
                person_states[p].apply(OFF)
                off_counter[p] += 1

            days.append(DayPlan(
                weekday_index=d,
                assignments={DAY: day_members, NIGHT: night_members, OFF: off_members}
            ))

        # Validate weekly OFF bounds
        for p in people:
            off_days = off_counter[p]
            if off_days < rules.min_days_off or off_days > rules.max_days_off:
                # If invalid, we will fail and the outer search will increase pattern_weeks
                raise ValueError(f"Weekly OFF days for {p} in {shift.name} = {off_days} violates [{rules.min_days_off}, {rules.max_days_off}]")

        week_patterns.append(WeekPlan(week_index=w, days=days))

    return week_patterns

def find_smallest_valid_pattern(shift: ShiftConfig, rules: RulesConfig, max_try_weeks: int = 12) -> List[WeekPlan]:
    """
    Attempts increasing pattern length until constraints are satisfied.
    """
    start = compute_min_pattern_weeks(len(shift.people), rules)
    for w in range(start, max_try_weeks + 1):
        try:
            return allocate_week_pattern(shift, rules, w)
        except ValueError:
            continue
    raise RuntimeError(f"Could not find a valid repeating pattern within {max_try_weeks} weeks for shift '{shift.name}'")

# ------------------------------
# CSV Output
# ------------------------------

def write_csv(out_path: str, start_date: dt.date, total_weeks: int, shift_patterns: Dict[str, List[WeekPlan]]) -> None:
    """
    Writes a schedule that repeats each shift's pattern cyclically until total_weeks are covered.
    """
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["week_index", "date", "weekday", "shift_name", "shift_type", "members"])

        for w in range(total_weeks):
            week_start = start_date + dt.timedelta(weeks=w)
            for shift_name, patterns in shift_patterns.items():
                # pick pattern week in cycle
                pattern_week = patterns[w % len(patterns)]
                for day in pattern_week.days:
                    day_date = week_start + dt.timedelta(days=day.weekday_index)
                    # write DAY
                    writer.writerow([w, day_date.isoformat(), WEEKDAYS[day.weekday_index], shift_name, DAY, ";".join(day.assignments[DAY])])
                    # write NIGHT
                    writer.writerow([w, day_date.isoformat(), WEEKDAYS[day.weekday_index], shift_name, NIGHT, ";".join(day.assignments[NIGHT])])

# ------------------------------
# CLI
# ------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Organize shifts into repeatable weekly patterns and output CSV")
    ap.add_argument("--config", required=True, help="Path to configuration JSON")
    ap.add_argument("--start", required=True, help="Start date (ISO, e.g., 2025-01-06 Monday)")
    ap.add_argument("--weeks", type=int, required=True, help="Total number of weeks to emit")
    ap.add_argument("--out", required=True, help="Output CSV path")
    return ap.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    cfg = parse_config(args.config)

    try:
        start_date = dt.date.fromisoformat(args.start)
    except ValueError:
        print("Error: --start must be an ISO date, e.g., 2025-01-06", file=sys.stderr)
        return 1
    if start_date.weekday() != 0:
        print("Warning: Start date is not Monday; weekly rows will begin mid-week.", file=sys.stderr)

    # Build patterns per shift
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
