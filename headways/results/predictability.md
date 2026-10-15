# Route predictability on real days

Each route is ridden as planned: same lines, same boarding and alighting stations, same walks, taking the first train of the planned line that actually gets there (any train if the line is not running), then any station still missed is swept up at the end. Runs: weekdays 2026-10-07, 2026-10-08, 2026-10-09, 2026-10-12, 2026-10-13 (each continuing into the next day) x start shifted by [-30, -20, -10, 0, 10, 20, 30] min. Actual trains from subwaydata.nyc (MTA GTFS-realtime).

| Route | Rules | Planned | Static timetable (mean) | Actual: mean | SD | P10 | P50 | P90 | P95 | Buffer index | Day-to-day SD | Within-day SD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Annealed timetable local | local | 24:25 | 26:53 | **41:26** | 171.1 min | 36:55 | 41:55 | 44:55 | 44:55 | 8.4% | 108.8 min | 97.5 min |
| Annealed timetable express | express | 23:48 | 25:03 | **32:25** | 143.4 min | 30:06 | 31:53 | 36:57 | 36:59 | 14.1% | 139.4 min | 30.0 min |
| Directed headway model local | local | 27:33 | 28:53 | **37:06** | 51.1 min | 36:04 | 37:04 | 38:13 | 38:23 | 3.5% | 44.0 min | 25.3 min |
| Directed headway model express | express | 26:42 | 27:39 | **36:07** | 109.8 min | 32:46 | 36:37 | 38:15 | 38:21 | 6.2% | 108.1 min | 18.7 min |

Rides replaced (planned line had no train) / stations never reached, summed over all runs: Annealed timetable local: 313 / 133; Annealed timetable express: 68 / 182; Directed headway model local: 25 / 28; Directed headway model express: 141 / 63

Per-day means (h): Annealed timetable local: 10-07 41.47, 10-08 40.36, 10-09 39.05, 10-12 41.82, 10-13 44.51; Annealed timetable express: 10-07 31.95, 10-08 30.17, 10-09 36.90, 10-12 31.53, 10-13 31.50; Directed headway model local: 10-07 36.87, 10-08 37.00, 10-09 38.34, 10-12 37.20, 10-13 36.06; Directed headway model express: 10-07 36.59, 10-08 32.73, 10-09 38.13, 10-12 36.75, 10-13 36.39
