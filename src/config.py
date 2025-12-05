from __future__ import annotations

import json
import datetime as dt
from typing import List
from .models import Config, ShiftConfig, RulesConfig, TimeRange


def parse_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    shifts: List[ShiftConfig] = []
    for s in raw.get("shifts", []):
        # Backward-compat: infer min staff from prefer_two_or_more_in_shift if present
        prefer_two = bool(s.get("prefer_two_or_more_in_shift", False))
        inferred_min = 2 if prefer_two else 1
        people_list = list(s["people"]) if isinstance(s.get("people"), list) else []
        people_count = len(people_list)
        shifts.append(ShiftConfig(
            name=s["name"],
            people=people_list,
            timezone=s["timezone"],
            day_shift=TimeRange(**s["day_shift"]),
            night_shift=TimeRange(**s["night_shift"]),
            min_day_staff=int(s.get("min_day_staff", inferred_min)),
            max_day_staff=int(s.get("max_day_staff", max(inferred_min, people_count))),
            min_night_staff=int(s.get("min_night_staff", inferred_min)),
            max_night_staff=int(s.get("max_night_staff", max(inferred_min, people_count))),
            # Weekend-specific staffing
            min_day_staff_weekend=int(s["min_day_staff_weekend"]) if "min_day_staff_weekend" in s else None,
            max_day_staff_weekend=int(s["max_day_staff_weekend"]) if "max_day_staff_weekend" in s else None,
            min_night_staff_weekend=int(s["min_night_staff_weekend"]) if "min_night_staff_weekend" in s else None,
            max_night_staff_weekend=int(s["max_night_staff_weekend"]) if "max_night_staff_weekend" in s else None,
            # Wednesday-specific staffing
            min_day_staff_wednesday=int(s["min_day_staff_wednesday"]) if "min_day_staff_wednesday" in s else None,
            max_day_staff_wednesday=int(s["max_day_staff_wednesday"]) if "max_day_staff_wednesday" in s else None,
            min_night_staff_wednesday=int(s["min_night_staff_wednesday"]) if "min_night_staff_wednesday" in s else None,
            max_night_staff_wednesday=int(s["max_night_staff_wednesday"]) if "max_night_staff_wednesday" in s else None,
        ))
    rules_raw = raw.get("rules", {})
    rules = RulesConfig(
        max_shifts_in_row=int(rules_raw.get("max_shifts_in_row", 5)),
        max_days_off=int(rules_raw.get("max_days_off", 2)),
        min_days_off=int(rules_raw.get("min_days_off", 1)),
        no_day_after_night=bool(rules_raw.get("no_day_after_night", True)),
        friday_shift2_priority_names=list(rules_raw.get("friday_shift2_priority_names", [])),
        min_days_off_after_night_streak=int(rules_raw.get("min_days_off_after_night_streak", 0)),
        target_weekly_hours_min=int(rules_raw.get("target_weekly_hours_min", 40)),
        target_weekly_hours_max=int(rules_raw.get("target_weekly_hours_max", 48)),
        enable_auto_adjust=bool(rules_raw.get("enable_auto_adjust", True)),
        require_equal_hours=bool(rules_raw.get("require_equal_hours", False)),
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
        _validate_time(s.day_shift.start)
        _validate_time(s.day_shift.end)
        _validate_time(s.night_shift.start)
        _validate_time(s.night_shift.end)

        # Staffing bounds validation
        if s.min_day_staff < 0 or s.min_night_staff < 0:
            raise ValueError(f"Shift '{s.name}' min_*_staff must be >= 0")
        if s.max_day_staff < s.min_day_staff:
            raise ValueError(f"Shift '{s.name}' max_day_staff must be >= min_day_staff")
        if s.max_night_staff < s.min_night_staff:
            raise ValueError(f"Shift '{s.name}' max_night_staff must be >= min_night_staff")
        if s.max_day_staff > len(s.people) or s.max_night_staff > len(s.people):
            raise ValueError(f"Shift '{s.name}' max_*_staff cannot exceed number of people")

    r = cfg.rules
    if r.min_days_off < 0 or r.max_days_off < 0:
        raise ValueError("Days off must be non-negative")
    if r.min_days_off > r.max_days_off:
        raise ValueError("min_days_off cannot exceed max_days_off")
    if r.max_shifts_in_row <= 0:
        raise ValueError("max_shifts_in_row must be positive")
    if r.min_days_off_after_night_streak < 0:
        raise ValueError("min_days_off_after_night_streak must be >= 0")
    if r.target_weekly_hours_min < 0:
        raise ValueError("target_weekly_hours_min must be >= 0")
    if getattr(r, "target_weekly_hours_max", 0) < 0:
        raise ValueError("target_weekly_hours_max must be >= 0")
    if hasattr(r, "target_weekly_hours_max") and r.target_weekly_hours_min > r.target_weekly_hours_max:
        raise ValueError("target_weekly_hours_min cannot exceed target_weekly_hours_max")


def _validate_time(t: str) -> None:
    try:
        dt.datetime.strptime(t, "%H:%M")
    except ValueError:
        raise ValueError(f"Invalid time format '{t}', expected HH:MM")
