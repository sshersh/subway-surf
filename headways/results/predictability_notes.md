# Headway model and real-day predictability

Branch `headway-model`. Results as of 2026-10-15.

## Directed ½-headway model

Waits are priced at ½ the average headway for each line, direction, station and hour, measured from last week's real-time data. The (station, line, direction) tour comes from Christofides. It is then polished by annealing and re-priced at its own clock times until it is consistent.

| Rules | Expected (model) | Same order on the timetable | Annealed timetable route |
|---|---|---|---|
| Express | 25 h 12 m (start 06:00) | 26 h 43 m | 23 h 48 m |
| Local | 26 h 38 m (start 07:00) | 27 h 34 m | 24 h 25 m |

Both directed routes pass `solver/verify.py`. Neither beats the annealed timetable routes on the timetable, or Trail of Bits' 20:42.

## Predictability on real days

`headways/predictability.py` runs in the "Route predictability on real days" workflow. Each route is ridden as planned: the same lines, the same boarding and alighting stations and the same walks. At each boarding it takes the first train of the planned line that actually reaches the planned stop. If that line isn't running there, it takes any train. Stations still missed at the end are swept up.

The test covers 5 weekdays (Oct 7–13) of actual train movements from subwaydata.nyc. Each day is run at 7 start times, from 30 minutes early to 30 minutes late.

| Route | Plan | Real days: mean | SD | P95 | Buffer index | Day-to-day SD | Within-day SD |
|---|---|---|---|---|---|---|---|
| Annealed local | 24:25 | 41:26 | 171 min | 44:55 | 8.4% | 109 min | 98 min |
| Annealed express | 23:48 | 32:25 | 143 min | 36:59 | 14.1% | 139 min | 30 min |
| Directed local | 27:33 | 37:06 | 51 min | 38:23 | 3.5% | 44 min | 25 min |
| Directed express | 26:42 | 36:07 | 110 min | 38:21 | 6.2% | 108 min | 19 min |

### Why real days are 8–17 h slower

- **The time lost is all waiting.** Actual ride times match the plan (ratio 1.00–1.01). Average wait per boarding is 8–12 min, against an observed ½-headway of 4.4–4.9 min at those stations and hours, so 1.8–2.4× higher.
- **Branches.** Line headways at a trunk station count every train on the line. A ride bound for one branch (A to Lefferts or Far Rockaway, 5 to Dyre Av) waits for that branch's trains only, often half as frequent. The headway model has the same blind spot.
- **Cascading lateness.** One late train (e.g. an 18-minute hold on the 05:12 A from Far Rockaway on Oct 7) makes the next connections miss too. The run then drifts into late-night service, where headways are 20 minutes and express lines run local.
- **Service changes.** Last week the F ran via 53 St, which isn't in the static schedule, so planned F rides via 57 St had to be replaced. Replaced rides per day: annealed local 9.4, annealed express 2.0, directed local 0.6, directed express 4.2.
- **These figures are for rigid plan-following.** A real runner re-plans after a missed connection, so they overstate the real-day time.

The directed local route has the most consistent finish time (SD 51 min, buffer index 3.5%). The timetable-tuned routes are fastest on paper but the most fragile.

## Next steps

- Make headways branch-aware, keyed by line × destination branch.
- Add an adaptive replay policy that re-plans the rest of the route after each ride, to measure what a runner who re-plans would get.
