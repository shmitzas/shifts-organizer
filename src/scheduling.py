from __future__ import annotations

import csv
import datetime as dt
from typing import List, Dict, Tuple
from .models import (
    WEEKDAYS, DAY, NIGHT, OFF,
    ShiftConfig, RulesConfig, PersonState,
    DayPlan, WeekPlan, Config
)


def compute_min_pattern_weeks(people_count: int, rules: RulesConfig) -> int:
    # Heuristic lower bound
    return 2


def _total_daily_staff(people_count: int, rules: RulesConfig) -> int:
    """
    Choose total staffed headcount (DAY+NIGHT) per day so that average OFF days
    per person stays within [min_days_off, max_days_off].

    Heuristic: target the midpoint OFF per week, then convert to staff.
    total_staff_per_day = people_count - target_off_avg
    Bound to [1, people_count].
    """
    target_off_avg = max(rules.min_days_off, min(rules.max_days_off, (rules.min_days_off + rules.max_days_off) // 2))
    total_staff = max(1, min(people_count, people_count - target_off_avg))
    return total_staff


def target_daily_staff_counts(shift: ShiftConfig, rules: RulesConfig, weekday_index: int) -> Tuple[int, int]:
    """
    Decide DAY and NIGHT staffing counts for the given weekday.
    - Keep both >= prefer_min (1 or 2)
    - Apply Wednesday day overfill by moving capacity from NIGHT to DAY
    - Keep total equal to computed daily staff
    """
    people_count = len(shift.people)
    total_staff = _total_daily_staff(people_count, rules)

    prefer_min = 2 if shift.prefer_two_or_more_in_shift else 1
    # Start with equal split
    day_count = max(prefer_min, total_staff // 2)
    night_count = max(prefer_min, total_staff - day_count)

    # If totals exceed, adjust
    while day_count + night_count > total_staff:
        if night_count > day_count:
            night_count -= 1
        else:
            day_count -= 1

    # Wednesday day overfill: shift headcount from night to day when possible
    if weekday_index == 2 and shift.wednesday_day_overfill_count > 0:
        desired_day = max(day_count, shift.wednesday_day_overfill_count)
        move = max(0, min(desired_day - day_count, night_count - prefer_min))
        day_count += move
        night_count -= move

    # Ensure we don't request more people than available
    total = day_count + night_count
    if total > people_count:
        overflow = total - people_count
        # Trim night first, then day
        trim_night = min(overflow, max(0, night_count - prefer_min))
        night_count -= trim_night
        overflow -= trim_night
        if overflow:
            day_count = max(prefer_min, day_count - overflow)

    return day_count, night_count


def allocate_week_pattern(shift: ShiftConfig, rules: RulesConfig, pattern_weeks: int) -> List[WeekPlan]:
    people = list(shift.people)
    person_states: Dict[str, PersonState] = {p: PersonState(name=p) for p in people}
    week_patterns: List[WeekPlan] = []

    # Helper to compute hours for a single assignment type for this shift
    def _hours_for(assign_type: str) -> float:
        def parse_hhmm(s: str) -> Tuple[int, int]:
            h, m = s.split(":")
            return int(h), int(m)
        if assign_type == DAY:
            sh = shift.day_shift
        else:
            sh = shift.night_shift
        h1, m1 = parse_hhmm(sh.start)
        h2, m2 = parse_hhmm(sh.end)
        t1 = dt.timedelta(hours=h1, minutes=m1)
        t2 = dt.timedelta(hours=h2, minutes=m2)
        dur = t2 - t1
        if dur.total_seconds() <= 0:
            # Overnight wrap
            dur = (dt.timedelta(days=1) - t1) + t2
        return dur.total_seconds() / 3600.0

    day_hours = _hours_for(DAY)
    night_hours = _hours_for(NIGHT)

    for w in range(pattern_weeks):
        days: List[DayPlan] = []
        off_counter: Dict[str, int] = {p: 0 for p in people}

        for d in range(7):
            day_count, night_count = target_daily_staff_counts(shift, rules, d)

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
            # Allow small deviations and let multi-week pattern absorb variance
            if off_days < rules.min_days_off - 1 or off_days > rules.max_days_off + 1:
                raise ValueError(
                    f"Weekly OFF days for {p} in {shift.name} = {off_days} violates relaxed bounds [{rules.min_days_off - 1}, {rules.max_days_off + 1}]"
                )

        week_patterns.append(WeekPlan(week_index=w, days=days))

    return week_patterns


def find_smallest_valid_pattern(shift: ShiftConfig, rules: RulesConfig, max_try_weeks: int = 52) -> List[WeekPlan]:
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


def write_pivot_csv(out_path: str, total_weeks: int, shift_patterns: Dict[str, List[WeekPlan]], cfg: Config) -> None:
    """
    Writes a pivot-style CSV matching the spreadsheet-like view:
    - Weeks laid out horizontally with day columns (M..Su) per week.
    - One row per shift+type, labeled with times and timezone.
    - Cells contain the semicolon-separated member list for that day.

    Note: CSV cannot merge cells for week headers; we emit a header row per week.
    """
    # Build header: for each week, 7 day columns
    week_headers: List[str] = []
    day_headers: List[str] = []
    for w in range(total_weeks):
        week_headers.extend([f"Week {w+1}"] + ["" for _ in range(6)])
        day_headers.extend(["M", "T", "W", "Th", "F", "S", "Su"])

    rows: List[List[str]] = []

    # For deterministic ordering: list the first team (first shift), then the second, etc.
    for shift in cfg.shifts:
        patterns = shift_patterns[shift.name]

        def base_label(assign_type: str) -> str:
            if assign_type == DAY:
                return f"{shift.name} {assign_type}: {shift.day_shift.start}-{shift.day_shift.end} {shift.timezone}"
            else:
                return f"{shift.name} {assign_type}: {shift.night_shift.start}-{shift.night_shift.end} {shift.timezone}"

        # Emit one row per person per assignment type, showing only that person's presence for each day
        for assign_type in (DAY, NIGHT):
            for person in shift.people:
                row: List[str] = []
                for w in range(total_weeks):
                    week = patterns[w % len(patterns)]
                    for d in range(7):
                        members = week.days[d].assignments[assign_type]
                        cell = person if person in members else ""
                        row.append(cell)
                row.insert(0, f"{base_label(assign_type)} | {person}")
                rows.append(row)

    # Write CSV
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # First column label for shift row names
        writer.writerow(["Shift"] + week_headers)
        writer.writerow([""] + day_headers * total_weeks)
        for r in rows:
            writer.writerow(r)


def write_pivot_xlsx(out_path: str, total_weeks: int, shift_patterns: Dict[str, List[WeekPlan]], cfg: Config) -> None:
    """
    Write a styled XLSX workbook with pivot layout and colors per team/shift type.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    except Exception as e:
        raise RuntimeError("XLSX output requires 'openpyxl'. Please install it.") from e

    wb = Workbook()
    ws = wb.active
    ws.title = "Schedule"

    # Header rows
    week_headers: List[str] = []
    day_headers: List[str] = []
    for w in range(total_weeks):
        week_headers.extend([f"Week {w+1}"] + ["" for _ in range(6)])
        day_headers.extend(["M", "T", "W", "Th", "F", "S", "Su"])

    # Write headers
    ws.cell(row=1, column=1, value="Shift")
    for i, h in enumerate(week_headers, start=2):
        ws.cell(row=1, column=i, value=h)
    for i, h in enumerate(day_headers * total_weeks, start=2):
        ws.cell(row=2, column=i, value=h)

    # Build data rows like CSV pivot (one row per person per assign type)
    rows: List[Tuple[str, List[str]]] = []
    for shift in cfg.shifts:
        patterns = shift_patterns[shift.name]
        def base_label(assign_type: str) -> str:
            if assign_type == DAY:
                return f"{shift.name} {assign_type}: {shift.day_shift.start}-{shift.day_shift.end} {shift.timezone}"
            else:
                return f"{shift.name} {assign_type}: {shift.night_shift.start}-{shift.night_shift.end} {shift.timezone}"
        for assign_type in (DAY, NIGHT):
            for person in shift.people:
                cells: List[str] = []
                for w in range(total_weeks):
                    week = patterns[w % len(patterns)]
                    for d in range(7):
                        members = week.days[d].assignments[assign_type]
                        cells.append(person if person in members else "")
                rows.append((f"{base_label(assign_type)} | {person}", cells))

    # Styling
    header_fill = PatternFill("solid", fgColor="DDDDDD")
    bold = Font(bold=True)
    center = Alignment(horizontal="center", vertical="center")
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Apply header style
    for r in (1, 2):
        for c in range(1, 1 + 1 + len(week_headers)):
            cell = ws.cell(row=r, column=c)
            cell.fill = header_fill
            cell.font = bold
            cell.alignment = center
            cell.border = border

    # Color map per team/type
    def team_colors(idx: int):
        # idx is shift index in cfg.shifts
        # Palette pairs: DAY, NIGHT
        palettes = [
            ("D9EAD3", "CFE2F3"),  # first team: green, teal
            ("FCE5CD", "EAD1DC"),  # second team: orange, purple
            ("FFF2CC", "D9D2E9"),  # third team: yellow, violet
        ]
        return palettes[idx % len(palettes)]

    # Write data rows with coloring per team/type
    row_idx = 3
    for shift_index, shift in enumerate(cfg.shifts):
        day_color, night_color = team_colors(shift_index)
        # For each type, for each person
        for assign_type in (DAY, NIGHT):
            color = day_color if assign_type == DAY else night_color
            fill = PatternFill("solid", fgColor=color)
            for person in shift.people:
                # Retrieve corresponding data row
                label = f"{shift.name} {assign_type}: {shift.day_shift.start}-{shift.day_shift.end} {shift.timezone}" if assign_type == DAY else f"{shift.name} {assign_type}: {shift.night_shift.start}-{shift.night_shift.end} {shift.timezone}"
                # Find the tuple in rows (inefficient linear search but fine for small sizes)
                # Alternatively we could generate inline, but keep simple
                # We'll just write now instead of searching rows list
                ws.cell(row=row_idx, column=1, value=f"{label} | {person}")
                # fill cells
                col = 2
                for w in range(total_weeks):
                    week = shift_patterns[shift.name][w % len(shift_patterns[shift.name])]
                    for d in range(7):
                        members = week.days[d].assignments[assign_type]
                        val = person if person in members else ""
                        cell = ws.cell(row=row_idx, column=col, value=val)
                        cell.border = border
                        cell.alignment = center
                        col += 1
                # color full row
                for c in range(1, 1 + 1 + len(week_headers)):
                    ws.cell(row=row_idx, column=c).fill = fill
                row_idx += 1

    # Freeze top two rows
    ws.freeze_panes = ws["A3"]

    # Set column widths roughly
    ws.column_dimensions["A"].width = 40
    # Data columns (B..): narrow but readable
    for c in range(2, 2 + len(week_headers)):
        ws.column_dimensions[chr(64 + c)].width = 10 if c <= 26 else 10  # simplistic; wide sheets may exceed Z

    wb.save(out_path)
