# Route predictability on real days

Each route keeps its station order and takes whichever train actually gets to the next station soonest. Runs: weekdays 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-12, 2026-10-13 (each continuing into the next day) x start shifted by [-30, -20, -10, 0, 10, 20, 30] min. Actual trains from subwaydata.nyc (MTA GTFS-realtime).

| Route | Rules | Planned | Static timetable (mean) | Actual: mean | SD | P10 | P50 | P90 | P95 | Buffer index | Day-to-day SD | Within-day SD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Annealed timetable local | local | 24:25 | 37:06 | **46:22** | 109.4 min | 44:56 | 47:03 | 47:37 | 47:56 | 3.4% | 62.8 min | 62.8 min |
| Annealed timetable express | express | 23:48 | 32:17 | **38:49** | 73.2 min | 37:22 | 39:07 | 39:47 | 39:47 | 2.5% | 39.5 min | 49.6 min |

Per-day means (h): Annealed timetable local: 10-07 45.54, 10-08 47.34, 10-09 46.58, 10-12 47.55, 10-13 44.81; Annealed timetable express: 10-07 38.84, 10-08 37.55, 10-09 39.31, 10-12 39.31, 10-13 39.07
