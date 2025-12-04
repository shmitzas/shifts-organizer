from __future__ import annotations

import csv
import datetime as dt
from typing import List, Dict, Tuple
from .models import (
    WEEKDAYS, DAY, NIGHT, OFF,
    ShiftConfig, RulesConfig, PersonState,
    DayPlan, WeekPlan
)


def compute_min_pattern_weeks(people_count: int, rules: RulesConfig) -> int:
    # Heuristic lower bound
    return 2


def target_daily_staff_count(shift: ShiftConfig, weekday_index: int) -> int:
    prefer_two = 2 if shift.prefer_two_or_more_in_shift else 1
    if weekday_index == 2 and shift.wednesday_day_overfill_count > 0:
        return max(prefer_two, shift.wednesday_day_overfill_count)
    return prefer_two


def allocate_week_pattern(shift: ShiftConfig, rules: RulesConfig, pattern_weeks: int) -> List[WeekPlan]:
    people = list(shift.people)
    person_states: Dict[str, PersonState] = {p: PersonState(name=p) for p in people}
    week_patterns: List[WeekPlan] = []

    for w in range(pattern_weeks):
        days: List[DayPlan] = []
        off_counter: Dict[str, int] = {p: 0 for p in people}

        for d in range(7):
            day_count = target_daily_staff_count(shift, d)
            night_count = target_daily_staff_count(shift, d)

            is_friday = (d == 4)
            priority_names = rules.friday_shift2_priority_names if shift.name.lower() == "shift 2" else []

            def rank_candidates(assign_type: str) -> List[str]:
                scored: List[Tuple[str, float]] = []
                for p in people:
                    st = person_states[p]
                    if not st.can_assign(assign_type, rules):
                        continue
                    penalty = st.streak_len if st.streak_type == assign_type else 0
                    bonus = -2 if (is_friday and p in priority_names) else 0
                    scored.append((p, penalty + (0 if st.last_assignment != assign_type else 0.5) - bonus))
                scored.sort(key=lambda x: (x[1], x[0]))
                return [p for p, _ in scored]

            day_members: List[str] = rank_candidates(DAY)[:day_count]
            for p in day_members:
                person_states[p].apply(DAY, rules)

            night_candidates = [p for p in people if p not in day_members]

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
                person_states[p].apply(NIGHT, rules)

            off_members = [p for p in people if p not in day_members and p not in night_members]
            # If a person was previously on NIGHT and now switches to OFF, start cooldown
            for p in off_members:
                st = person_states[p]
                # Detect transition from NIGHT to OFF at the start of OFF streak (streak_len will be set in apply)
                if st.last_assignment == NIGHT and st.night_cooldown_remaining == 0 and rules.min_days_off_after_night_streak > 0:
                    # Initialize cooldown; apply() will decrement per OFF day
                    st.night_cooldown_remaining = rules.min_days_off_after_night_streak
            for p in off_members:
                person_states[p].apply(OFF, rules)
                off_counter[p] += 1

            days.append(DayPlan(
                weekday_index=d,
                assignments={DAY: day_members, NIGHT: night_members, OFF: off_members}
            ))

        for p in people:
            off_days = off_counter[p]
            if off_days < rules.min_days_off or off_days > rules.max_days_off:
                raise ValueError(
                    f"Weekly OFF days for {p} in {shift.name} = {off_days} violates [{rules.min_days_off}, {rules.max_days_off}]"
                )

        week_patterns.append(WeekPlan(week_index=w, days=days))

    return week_patterns


def find_smallest_valid_pattern(shift: ShiftConfig, rules: RulesConfig, max_try_weeks: int = 12) -> List[WeekPlan]:
    start = compute_min_pattern_weeks(len(shift.people), rules)
    for w in range(start, max_try_weeks + 1):
        try:
            return allocate_week_pattern(shift, rules, w)
        except ValueError:
            continue
    raise RuntimeError(
        f"Could not find a valid repeating pattern within {max_try_weeks} weeks for shift '{shift.name}'"
    )


def write_csv(out_path: str, start_date: dt.date, total_weeks: int, shift_patterns: Dict[str, List[WeekPlan]]) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["week_index", "date", "weekday", "shift_name", "shift_type", "members"])

        for w in range(total_weeks):
            week_start = start_date + dt.timedelta(weeks=w)
            for shift_name, patterns in shift_patterns.items():
                pattern_week = patterns[w % len(patterns)]
                for day in pattern_week.days:
                    day_date = week_start + dt.timedelta(days=day.weekday_index)
                    writer.writerow([w, day_date.isoformat(), WEEKDAYS[day.weekday_index], shift_name, DAY, ";".join(day.assignments[DAY])])
                    writer.writerow([w, day_date.isoformat(), WEEKDAYS[day.weekday_index], shift_name, NIGHT, ";".join(day.assignments[NIGHT])])
