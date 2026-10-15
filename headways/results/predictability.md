# Route predictability on real days

Each route keeps its station order and takes whichever train actually gets to the next station soonest. Runs: weekdays 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-12, 2026-10-13 (each continuing into the next day) x start shifted by [-30, -20, -10, 0, 10, 20, 30] min. Actual trains from subwaydata.nyc (MTA GTFS-realtime).

| Route | Rules | Planned | Static timetable (mean) | Actual: mean | SD | P10 | P50 | P90 | P95 | Buffer index | Day-to-day SD | Within-day SD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Annealed timetable local | local | 24:25 | 27:43 | **31:31** | 71.7 min | 30:02 | 31:30 | 33:15 | 33:38 | 6.7% | 48.2 min | 38.9 min |
| Annealed timetable express | express | 23:48 | 27:49 | **32:05** | 92.9 min | 30:42 | 31:34 | 35:08 | 35:09 | 9.5% | 91.3 min | 16.6 min |

Per-day means (h): Annealed timetable local: 10-07 30.27, 10-08 32.74, 10-09 31.73, 10-12 31.19, 10-13 31.69; Annealed timetable express: 10-07 31.15, 10-08 30.85, 10-09 35.06, 10-12 31.74, 10-13 31.64
