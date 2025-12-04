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

@dataclasses.dataclass
class PersonState:
    name: str
    streak_type: Optional[str] = None  # DAY/NIGHT/OFF
    streak_len: int = 0
    last_assignment: Optional[str] = None

    def can_assign(self, assign: str, rules: RulesConfig) -> bool:
        if assign == DAY:
            if self.streak_type == DAY and self.streak_len >= rules.max_day_in_row:
                return False
            if rules.no_day_after_night and self.last_assignment == NIGHT:
                return False
        if assign == NIGHT:
            if self.streak_type == NIGHT and self.streak_len >= rules.max_night_in_row:
                return False
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
