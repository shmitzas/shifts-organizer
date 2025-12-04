from __future__ import annotations

import dataclasses
from typing import List, Dict, Optional

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DAY = "DAY"
NIGHT = "NIGHT"
OFF = "OFF"

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
    max_shifts_in_row: int
    max_days_off: int
    min_days_off: int
    no_day_after_night: bool
    friday_shift2_priority_names: List[str]
    wednesday_day_overfill: bool
    min_days_off_after_night_streak: int

@dataclasses.dataclass
class Config:
    shifts: List[ShiftConfig]
    rules: RulesConfig

@dataclasses.dataclass
class PersonState:
    name: str
    streak_type: Optional[str] = None  # DAY/NIGHT/OFF
    streak_len: int = 0
    last_assignment: Optional[str] = None
    night_cooldown_remaining: int = 0
    working_streak_len: int = 0  # consecutive DAYS or NIGHTS regardless of type

    def can_assign(self, assign: str, rules: RulesConfig) -> bool:
        # If in mandatory cooldown after NIGHT streak, only OFF is allowed
        if self.night_cooldown_remaining > 0 and assign != OFF:
            return False
        # Unified max consecutive working shifts (DAY or NIGHT)
        if assign in (DAY, NIGHT):
            if self.working_streak_len >= rules.max_shifts_in_row:
                return False
        # Cross-type immediate constraints
        if assign == DAY and rules.no_day_after_night and self.last_assignment == NIGHT:
            return False
        return True

    def apply(self, assign: str, rules: Optional[RulesConfig] = None) -> None:
        if self.streak_type == assign:
            self.streak_len += 1
        else:
            self.streak_type = assign
            self.streak_len = 1
        self.last_assignment = assign
        # Maintain unified working streak length across DAY/NIGHT
        if assign in (DAY, NIGHT):
            self.working_streak_len += 1
        else:
            self.working_streak_len = 0
        # Manage cooldown: when transitioning from NIGHT to OFF, start cooldown
        if rules is not None:
            if self.last_assignment == OFF:
                # If previous streak was NIGHT and we just started OFF, initialize cooldown if not already
                if self.night_cooldown_remaining == 0 and self.streak_len == 1 and self.streak_type == OFF and self.last_assignment:
                    # Check previous assignment type via last_assignment before overwrite; we already set last_assignment=OFF
                    pass
            # Decrement cooldown when OFF
            if assign == OFF and self.night_cooldown_remaining > 0:
                self.night_cooldown_remaining -= 1
            # If assigning NIGHT, reset cooldown
            if assign == NIGHT:
                # Night assignment continues/starts a streak; cooldown will be set when OFF begins below
                pass
            # If we transitioned from NIGHT to OFF (detect using previous assignment), start cooldown
            # We can't read previous assignment now; callers should set cooldown when starting OFF after NIGHT.

@dataclasses.dataclass
class DayPlan:
    weekday_index: int  # 0..6
    assignments: Dict[str, List[str]]  # {DAY: [names], NIGHT: [names], OFF: [names]}

@dataclasses.dataclass
class WeekPlan:
    week_index: int  # pattern index
    days: List[DayPlan]  # length 7
