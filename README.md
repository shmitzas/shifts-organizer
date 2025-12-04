# Shifts Organizer
Organize repeatable weekly shift patterns from a declarative configuration and export to CSV.

## Features
- Repeatable weekly patterns: schedule repeats every N weeks per shift.
- Constraints-aware: max streaks, off-day bounds, and "no day after night".
- Per-shift preferences: Wednesday day overfill and Friday priorities.
- Simple CSV output for downstream tools.

## Quick Start
1) Create a `config.json` in the project root (see schema below).
2) Provide start period in `YYYY-MM` (first day auto-selected).
3) Set up a virtual environment and install dependencies:

On Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows:

```pwsh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4) Run the CLI to generate a schedule:

```pwsh
# CSV pivot (plain, no styling)
python -m src.main --config config.json --start 2025-01 --out schedule.csv

# XLSX pivot with styling (colors, frozen headers) — requires openpyxl
python -m src.main --config config.json --start 2025-01 --out schedule.xlsx --format xlsx

# Weeks optional: defaults to the repeat cycle length (LCM of shift patterns)
python -m src.main --config config.json --start 2025-01 --out schedule.xlsx

# Specify weeks explicitly if desired
python -m src.main --config config.json --start 2025-01 --weeks 12 --out schedule.xlsx --format xlsx
```

Alternatively, the legacy entry point is still available:

```pwsh
# Weeks optional in legacy wrapper as well
python scheduler.py --config config.json --start 2025-01 --out schedule.xlsx --format xlsx
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
| `min_day_staff` | integer | `1` | Minimum people on DAY shift. |
| `max_day_staff` | integer | `people_count` | Maximum people on DAY shift. |
| `min_night_staff` | integer | `1` | Minimum people on NIGHT shift. |
| `max_night_staff` | integer | `people_count` | Maximum people on NIGHT shift. |

### Rules
| Field | Type | Default | Description |
|------|------|---------|-------------|
| `max_shifts_in_row` | integer | `5` | Upper bound for consecutive working shifts (DAY or NIGHT). |
| `max_days_off` | integer | `2` | Max OFF days per person per week. |
| `min_days_off` | integer | `1` | Min OFF days per person per week. |
| `no_day_after_night` | boolean | `true` | Prevent DAY immediately after NIGHT. |
| `friday_shift2_priority_names` | array(string) | `[]` | Prefer these names on Fridays in Shift 2. |
| `wednesday_day_overfill` | boolean | `true` | Enable Wednesday day overfill behavior. |
| `min_days_off_after_night_streak` | integer | `0` | Require at least N OFF days immediately after finishing a NIGHT streak. |
| `target_weekly_hours_min` | integer | `40` | Minimum average weekly hours per person to accept a pattern (auto-adjust may reduce OFF to reach target). |
| `enable_auto_adjust` | boolean | `true` | Allow the scheduler to relax preferred options and reduce `max_days_off` if necessary to meet the target. |

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
			"min_day_staff": 2,
			"max_day_staff": 3,
			"min_night_staff": 2,
			"max_night_staff": 3
		},
		{
			"name": "Shift 2",
			"people": ["Dina", "Evan"],
			"timezone": "GMT+7",
			"day_shift": {"start": "09:00", "end": "18:00"},
			"night_shift": {"start": "17:00", "end": "02:00"},
			"wednesday_day_overfill_count": 2,
			"min_day_staff": 2,
			"max_day_staff": 3,
			"min_night_staff": 2,
			"max_night_staff": 3
		}
	],
	"rules": {
		"max_shifts_in_row": 5,
		"max_days_off": 2,
		"min_days_off": 1,
		"no_day_after_night": true,
		"friday_shift2_priority_names": ["Dina"],
		"wednesday_day_overfill": true,
		"min_days_off_after_night_streak": 2,
		"target_weekly_hours_min": 40,
		"enable_auto_adjust": true
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
	- Also supports XLSX pivot with styling (requires `openpyxl`).
- `src/main.py`: primary CLI entry point
- `scheduler.py`: backward-compatible wrapper
- `requirements.txt`: Python dependencies (install with `pip install -r requirements.txt`)

## Tips
- Start on a Monday to align week indices.
- If constraints are tight, the tool increases pattern length until valid (up to 24 weeks).
- OFF days are implied by absence from DAY/NIGHT rows for a date.
 - Google Sheets preserves XLSX styling (backgrounds, bold, frozen panes) on import.
 - If `openpyxl` is missing, install via `pip install -r requirements.txt`.
