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
    # Staffing bounds
    min_day_staff: int
    max_day_staff: int
    min_night_staff: int
    max_night_staff: int

@dataclasses.dataclass
class RulesConfig:
    max_shifts_in_row: int
    max_days_off: int
    min_days_off: int
    no_day_after_night: bool
    friday_shift2_priority_names: List[str]
    wednesday_day_overfill: bool
    min_days_off_after_night_streak: int
    # New configurable targets/behaviors
    target_weekly_hours_min: int = 40
    target_weekly_hours_max: int = 48
    enable_auto_adjust: bool = True

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
    previous_assignment: Optional[str] = None  # Track previous state for transition detection

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
        # Store previous before updating
        self.previous_assignment = self.last_assignment
        
        # Update streak tracking
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
        
        # Cooldown management with proper transition detection
        if rules is not None:
            # Detect NIGHT → OFF transition
            if assign == OFF and self.previous_assignment == NIGHT and self.night_cooldown_remaining == 0:
                self.night_cooldown_remaining = rules.min_days_off_after_night_streak
            
            # Decrement cooldown on OFF days
            if assign == OFF and self.night_cooldown_remaining > 0:
                self.night_cooldown_remaining -= 1

@dataclasses.dataclass
class DayPlan:
    weekday_index: int  # 0..6
    assignments: Dict[str, List[str]]  # {DAY: [names], NIGHT: [names], OFF: [names]}

@dataclasses.dataclass
class WeekPlan:
    week_index: int  # pattern index
    days: List[DayPlan]  # length 7
