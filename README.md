# Shifts Organizer
Python script that organizes shifts based on configurable criteria.

## Configuration

### Shift 1
| Setting                                 | Default |
|-----------------------------------------|---------|
| People                                  | Name 1, Name 2 |
| Time zone                               | EET     |
| Day shift start                         | 09:00   |
| Day shift end                           | 18:00   |
| Night shift start                       | 17:00   |
| Night shift end                         | 02:00   |
| Wednesday day shift overfill count      | 2       |
| Prefer 2 or more people in shift        | true    |

### Shift 2
| Setting                                 | Default |
|-----------------------------------------|---------|
| People                                  | Name 1, Name 2 |
| Time zone                               | GMT+7   |
| Day shift start                         | 09:00   |
| Day shift end                           | 18:00   |
| Night shift start                       | 17:00   |
| Night shift end                         | 02:00   |
| Wednesday day shift overfill count      | 2       |
| Prefer 2 or more people in shift        | true    |

### Extra Rules
| Rule                          | Default |
|------------------------------|---------|
| Maximum day shifts in a row  | 5       |
| Maximum night shifts in a row| 5       |
| Maximum days off             | 2       |
| Minimum days off             | 1       |
| No day shift after night shift| true   |
| Friday shift 2 priority names| ""      |
| Wednesday day shift overfill | true    |

## Notes
- “People” can be expanded per shift.
- Times are local to each shift’s time zone.
- Overfill rules allow temporarily exceeding typical capacity.
