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
        max_shifts_in_row=int(rules_raw.get("max_shifts_in_row", 5)),
        max_days_off=int(rules_raw.get("max_days_off", 2)),
        min_days_off=int(rules_raw.get("min_days_off", 1)),
        no_day_after_night=bool(rules_raw.get("no_day_after_night", True)),
        friday_shift2_priority_names=list(rules_raw.get("friday_shift2_priority_names", [])),
        wednesday_day_overfill=bool(rules_raw.get("wednesday_day_overfill", True)),
        min_days_off_after_night_streak=int(rules_raw.get("min_days_off_after_night_streak", 0)),
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
    if r.max_shifts_in_row <= 0:
        raise ValueError("max_shifts_in_row must be positive")
    if r.min_days_off_after_night_streak < 0:
        raise ValueError("min_days_off_after_night_streak must be >= 0")


def _validate_time(t: str) -> None:
    try:
        dt.datetime.strptime(t, "%H:%M")
    except ValueError:
        raise ValueError(f"Invalid time format '{t}', expected HH:MM")
