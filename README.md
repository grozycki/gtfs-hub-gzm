# gtfs-hub-gzm

GZM provider for [gtfs-hub](https://github.com/grozycki/gtfs-hub). It finds the current schedule files through the publisher's data portal, because their names and IDs change with each publication.

Data source: GZM ZTM, Creative Commons Attribution. Consumers must show the provider's `attribution`.

## Usage

Install it beside `gtfs-hub`, and core finds it by its key:

```python
from gtfs_hub import create_provider

provider = create_provider("gzm")
```

A vehicle key is derived from the feed, but the provider does not declare it stable, because the survey has not proven that.

## Measurements

Measured on 2026-10-31 on an Apple laptop with the real feed: all 10 current files, one selected line (bus 11), 5.5 million `stop_times` rows in the source.

| Measure | Result |
|---|---|
| First sync, including download | 20.5 s |
| Peak process memory | 62 MB |
| Database size | 14 MB |
| Repeated sync with unchanged files | 0.1 s, no downloads |

Low-power hardware has not been tested yet.

## Findings

- **Line 11 stops:** all 39 stops on the publisher's timetable page for 2026-10-31 are found. The schedule adds 10 more names: non-passenger points such as `Czeladź Wojkowicka Pętla [TECH]` and `Granica Kato - Sosn (Milowice)`, and stops of other variants in other snapshots, such as `Katowice Arena`. Whether to hide the non-passenger points is decided with departures.
- **Links:** in one file, `route_url` was filled on all 414 routes and `stop_url` on all 7,138 stops, so no provider code is needed for timetable links. `stop_url` leads to a stop page by `stop_code`.
- **Trip updates:** `stop_sequence` is the next stop. In 2,327 changes of it on 2026-10-31, the vehicle was closer to the previous stop in 85% of cases, at a median of 93 m from it.
- **Non-passenger points:** every stop time at `[TECH]` and `Granica` points in the checked file has `pickup_type` and `drop_off_type` of 1.
- **Live departures:** on 2026-10-31 at 13:43, for all 85 passenger stops of bus 11 with the next 4 departures each, 49 of 280 had a prediction, delays ranged from -60 to 600 s, and none was in the past. The feed was 10 s old. Single results were checked against the clock only, not against SDIP.
- **Feed rhythm:** measured over 4 minutes on 2026-10-31, both headers change about every 10.5 s, a vehicle position changes at a median of 15 s (10 to 25 s), and a trip's delay at a median of 40 s (10 to 95 s). A position message is about 76 KB.
- **Vehicle key:** over 7.6 hours on 2026-10-31, 104 of 983 keys ran two or more blocks, 74 of 1,013 blocks had two or more keys, every key stayed with one operator, and 980 keys stayed with one planned vehicle class. So the key follows something other than a block, which fits a physical vehicle. This covers one Saturday, and a full day, a weekday and a real fleet number are still unchecked.
