# gtfs-hub-gzm

GZM provider for [gtfs-hub](https://github.com/grozycki/gtfs-hub). It finds the current schedule files through the publisher's data portal, because their names and IDs change with each publication.

Data source: GZM ZTM, Creative Commons Attribution. Consumers must show the provider's `attribution`.

## Installation

```bash
pip install gtfs-hub-gzm
```

It pulls in a matching `gtfs-hub`. Versions follow [Semantic Versioning](https://semver.org/); see the [changelog](CHANGELOG.md).

## Usage

Installed beside `gtfs-hub`, core finds it by its key:

```python
from gtfs_hub import create_provider

provider = create_provider("gzm")
```

The vehicle key is the feed's vehicle ID without its trip, and the provider declares it stable. The survey below found that one key never ran two trips at once, keys outlive trips and blocks, and fleet numbers match.

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
- **Fleet numbers:** the key ends in the fleet number. On 2026-10-31, zbiorkom.live showed key `108_108001347` as vehicle `1347`, a Solaris Urbino 18 on line 11, which matches the line and the 18 m class in the schedule. The site was used only to check this by hand and is not a data source.
- **Publication:** a new complete set appears each night with new resource IDs and file names, at 00:09 on 2026-10-31 and 01:29 on 2026-11-01. The 8 files with identical windows on both days all had different ZIP hashes, and `feed_version` alone holds the date, so core compares member CRCs and the window instead. On 2026-11-02 the set appeared between 00:36 and 01:01, and all 7 files with windows matching the previous day had a new fingerprint, which was a real change: see the next point. On 2026-11-03 every file changed again, in most tables: the replacement lines Z-2, Z-20 and T31 got new route IDs once more, Z-2 going from 9020 to 7203, which touches routes, trips, stop times and shapes. For the selected lines, trips, stop times and stops were the same as the day before. GZM therefore never keeps a fingerprint from one day to the next, and core reimports the selected lines each night, about 20 s. A finer fingerprint per line would avoid it.
- **Route IDs:** `route_id` is not stable between publications. On 2026-11-02, T31 moved from 9021 to 9019, Z-2 from 9022 to 9020 and Z-20 from 9023 to 9021, so 9021 now means another line. Lines are therefore identified by mode and short name. In the 6 windows compared on the selected lines, 403 to 608 trips per window, every trip kept its ID and stop times, and no stop ID appeared or left.
- **Republishing and gaps in the listing:** on 2026-11-02 the set was published again during the day, with files created at 07:55, 08:20, 15:14 and later. On 2026-11-03 the file for Saturday 2026-11-07 (number 11787) was missing from the listing; core kept the previous day's snapshot for it, so Saturday stays covered.
- **Feed gaps:** both realtime feeds were empty, with fresh headers, from at least 21:08 on 2026-10-31 until some time before 05:57 the next day, but were not empty at 21:54 on 2026-11-01. They were empty again at 01:05 on 2026-11-02, with 1,325 vehicles at 06:40. The laptop sampling them slept during both nights, so neither end is known and there is no fixed pattern yet. On 2026-11-02 the feed still had 160 vehicles at 23:56; the laptop then shut down at midnight, as it is scheduled to every day, so night sampling needs another machine.
- **Vehicle key uniqueness:** in 126,910 key observations across 184 samples from 2026-10-31 to 2026-11-02, no key appeared twice in one sample, so one key never ran two trips at once.
- **Weekday:** on Monday 2026-11-02 the laptop slept for most of the day, leaving 68 samples, from 06:40 to 09:46, at 14:13 and from 17:32 to 23:56. With the evening, 49,128 observations of 1,536 keys had no key twice in one sample, and over all 252 samples since 2026-10-31, 175,999 observations had none either. The figures below are from the first 14 samples, between 06:40 and 19:26, with gaps from 09:46 to 14:13 and from 14:13 to 17:32. In 16,052 observations of 1,516 keys, no key appeared twice in one sample, 1,487 keys ran two or more trips, 195 keys ran two or more blocks, and 205 of 1,513 blocks had two or more keys. 1,136 of the keys had also run at the weekend. 9 keys served trips of two operators, but the operator in `trips_ext.txt` is a contract consortium, and the key prefix stands for the carrier, which serves several of them: prefix 122 alone served 6 operator IDs. 21 keys ran trips planned for two classes, such as 12 m and 18 m buses, so the planned class can differ from the vehicle that runs the trip.
- **More fleet numbers:** on 2026-11-02, zbiorkom.live showed vehicle `4621` on line 157 to Tychy Szpital Wojewódzki, matching key `283_283004621` on that trip. Vehicle `2667` matched its key but showed line 638 minutes after the sample had line 622, so it proves the number only. Tram key `125_125001067` did not open under the page's bus ID form and remains unchecked.
