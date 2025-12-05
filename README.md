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
# CSV output (--format is required)
python -m src.main --config config.json --start 2025-01 --out schedule --format csv

# XLSX output with styling (colors, frozen headers) — requires openpyxl
python -m src.main --config config.json --start 2025-01 --out schedule --format xlsx

# Specify weeks explicitly (optional, defaults to pattern cycle length)
python -m src.main --config config.json --start 2025-01 --weeks 12 --out schedule --format xlsx
```

**Note:** The `--format` flag is required and will automatically add the correct file extension (`.csv` or `.xlsx`) to the output filename.

Alternatively, the legacy entry point is still available:

```pwsh
python scheduler.py --config config.json --start 2025-01 --out schedule --format xlsx
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
| `max_shifts_in_row` | integer | `5` | Maximum consecutive working shifts (DAY or NIGHT combined). |
| `max_days_off` | integer | `2` | Maximum consecutive OFF days allowed. |
| `min_days_off` | integer | `1` | Minimum consecutive OFF days required (enforced strictly). |
| `no_day_after_night` | boolean | `true` | Prevent DAY shift immediately after NIGHT shift. |
| `friday_shift2_priority_names` | array(string) | `[]` | Prefer these people on Friday NIGHT shifts. |
| `wednesday_day_overfill` | boolean | `true` | Enable extra DAY staff on Wednesdays. |
| `min_days_off_after_night_streak` | integer | `0` | Mandatory OFF days after finishing a NIGHT streak. |
| `target_weekly_hours_min` | integer | `40` | Minimum average weekly hours per person (auto-adjust tries to meet this). |
| `target_weekly_hours_max` | integer | `48` | Maximum average weekly hours across the pattern (legal compliance limit). |
| `enable_auto_adjust` | boolean | `true` | Allow relaxing preferences if pattern generation fails within 104 weeks. |
| `require_equal_hours` | boolean | `false` | Enforce equal average hours for all people (within 0.5h tolerance). May require longer patterns. |

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
			"min_day_staff": 1,
			"max_day_staff": 2,
			"min_night_staff": 2,
			"max_night_staff": 2
		},
		{
			"name": "Shift 2",
			"people": ["Dina", "Evan", "Frank"],
			"timezone": "GMT+7",
			"day_shift": {"start": "06:00", "end": "15:00"},
			"night_shift": {"start": "17:00", "end": "02:00"},
			"wednesday_day_overfill_count": 2,
			"min_day_staff": 1,
			"max_day_staff": 2,
			"min_night_staff": 2,
			"max_night_staff": 2
		}
	],
	"rules": {
		"max_shifts_in_row": 5,
		"max_days_off": 2,
		"min_days_off": 1,
		"no_day_after_night": true,
		"friday_shift2_priority_names": ["Dina"],
		"wednesday_day_overfill": true,
		"min_days_off_after_night_streak": 1,
		"target_weekly_hours_min": 35,
		"target_weekly_hours_max": 45,
		"enable_auto_adjust": true,
		"require_equal_hours": false
	}
}
```

## Output Formats

### CSV/XLSX Pivot Format
The scheduler generates a pivot-style layout with one row per person per shift type:

- **Shift column**: Shows shift name and type (e.g., "LT S1: 09-18" for DAY, "LT S2: 17-02" for NIGHT)
- **Week columns**: Each week has:
  - 7 day columns (M, T, W, Th, F, S, Su) showing person names when working
  - **Hours**: Weekly hours for that shift type
  - **Total**: Combined DAY+NIGHT hours for the week (DAY rows only)
- **Avg column**: Average combined hours per week across the entire pattern (DAY rows only)

**Example output:**

| Shift | Week 1 | | | | | | | | | Week 2 | | | | | | | | | Avg |
|-------|--------|---|---|---|---|---|---|---|---|--------|---|---|---|---|---|---|---|---|-----|
| | M | T | W | Th | F | S | Su | Hours | Total | M | T | W | Th | F | S | Su | Hours | Total | |
| LT S1: 09-18 | | Alice | | | Alice | | | 18.0 | 36.0 | Alice | | | Alice | | | Alice | 27.0 | 45.0 | 40.5 |
| LT S1: 09-18 | | | Bob | | | Bob | | 18.0 | 45.0 | | Bob | | | Bob | | | 18.0 | 36.0 | 40.5 |
| LT S2: 17-02 | | | | Alice | | | Alice | 18.0 | | | | | Alice | | | Alice | 18.0 | | |
| LT S2: 17-02 | Bob | | | Bob | | | Bob | 27.0 | | | | Bob | | | Bob | | 18.0 | | |

### XLSX Styling
When using `--format xlsx`, the output includes:
- Color-coded rows per shift/team
- Bold headers and average columns
- Frozen top rows for easy scrolling
- Borders and center alignment
- Column width optimization

## Project Structure
- `src/models.py`: data classes and constants
- `src/config.py`: parse and validate configuration
- `src/scheduling.py`: scheduling engine + CSV writer
	- Also supports XLSX pivot with styling (requires `openpyxl`).
- `src/main.py`: primary CLI entry point
- `scheduler.py`: backward-compatible wrapper
- `requirements.txt`: Python dependencies (install with `pip install -r requirements.txt`)

## Tips
- Start on a Monday to align week indices with calendar weeks.
- If constraints are tight, the tool increases pattern length automatically (up to 104 weeks).
- OFF days are implied by absence from DAY/NIGHT assignments for a date.
- Google Sheets preserves XLSX styling (backgrounds, bold, frozen panes) on import.
- If `openpyxl` is missing, install via `pip install -r requirements.txt`.

### Constraint Conflicts
Some combinations of constraints may be impossible to satisfy simultaneously:
- High `min_days_off` (e.g., 3+) with `require_equal_hours` may fail with small teams
- Very tight staffing requirements reduce scheduling flexibility
- `target_weekly_hours_max` of 40 (legal limit) may conflict with staffing needs

**If pattern generation fails or produces unequal hours:**
1. Lower `min_days_off` to 1 or 2 for more flexibility
2. Disable `require_equal_hours` to allow hour variation
3. Add more people to shifts to increase scheduling options
4. Adjust `max_days_off` to allow longer rest periods
5. Review minimum staffing requirements (`min_day_staff`, `min_night_staff`)
