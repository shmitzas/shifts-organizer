# Shifts Organizer
Organize repeatable weekly shift patterns from a declarative configuration and export to CSV.

## Features
- Repeatable weekly patterns: schedule repeats every N weeks per shift.
- Constraints-aware: max streaks, off-day bounds, and "no day after night".
- Per-shift preferences: Wednesday day overfill and Friday priorities.
- Simple CSV output for downstream tools.

## Quick Start
1) Create a `config.json` in the project root (see schema below).
2) Run the CLI to generate a schedule:

```pwsh
python -m src.main --config config.json --start 2025-01-06 --weeks 12 --out schedule.csv
```

Alternatively, the legacy entry point is still available:

```pwsh
python scheduler.py --config config.json --start 2025-01-06 --weeks 12 --out schedule.csv
```

## Configuration Schema (JSON)

### Shifts
| Field | Type | Example | Notes |
|------|------|---------|-------|
| `name` | string | `"Shift 1"` | Unique shift identifier. |
| `people` | array(string) | `["Alice","Bob","Charlie"]` | Members of this shift. |
| `timezone` | string | `"EET"` | Informational only. |
| `day_shift.start` | string `HH:MM` | `"09:00"` | Start time. |
| `day_shift.end` | string `HH:MM` | `"18:00"` | End time. |
| `night_shift.start` | string `HH:MM` | `"17:00"` | Start time. |
| `night_shift.end` | string `HH:MM` | `"02:00"` | End time. |
| `wednesday_day_overfill_count` | integer | `2` | Extra DAY staff on Wednesday. |
| `prefer_two_or_more_in_shift` | boolean | `true` | Target at least two people per shift. |

### Rules
| Field | Type | Default | Description |
|------|------|---------|-------------|
| `max_day_in_row` | integer | `5` | Upper bound for consecutive DAY assignments. |
| `max_night_in_row` | integer | `5` | Upper bound for consecutive NIGHT assignments. |
| `max_days_off` | integer | `2` | Max OFF days per person per week. |
| `min_days_off` | integer | `1` | Min OFF days per person per week. |
| `no_day_after_night` | boolean | `true` | Prevent DAY immediately after NIGHT. |
| `friday_shift2_priority_names` | array(string) | `[]` | Prefer these names on Fridays in Shift 2. |
| `wednesday_day_overfill` | boolean | `true` | Enable Wednesday day overfill behavior. |
| `min_days_off_after_night_streak` | integer | `0` | Require at least N OFF days immediately after finishing a NIGHT streak. |

### Example `config.json`
```json
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
		"wednesday_day_overfill": true,
		"min_days_off_after_night_streak": 2
	}
}
```

## CSV Output
Rows contain both DAY and NIGHT entries for each date.

| Column | Description |
|--------|-------------|
| `week_index` | Zero-based index from start date; repeats per pattern length. |
| `date` | ISO date for the assignment. |
| `weekday` | Human-readable weekday name. |
| `shift_name` | Name of the shift. |
| `shift_type` | `DAY` or `NIGHT`. |
| `members` | Semicolon-separated list of assigned names. |

## Project Structure
- `src/models.py`: data classes and constants
- `src/config.py`: parse and validate configuration
- `src/scheduling.py`: scheduling engine + CSV writer
- `src/main.py`: primary CLI entry point
- `scheduler.py`: backward-compatible wrapper

## Tips
- Start on a Monday to align week indices.
- If constraints are tight, the tool increases pattern length until valid (up to 24 weeks).
- OFF days are implied by absence from DAY/NIGHT rows for a date.
