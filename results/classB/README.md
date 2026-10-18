# Class B (Guinness) rules: stop at every station, no safety buffer, normal weekday service

Local rules, no hard slack (plain replay, plan = arrival at the last new station or Flushing minus start), 475 stations, GTFS 20260826 weekday.
Anneal: `solver/ends.py` (fixed ends, now with `--tmin/--tmax`) and `solver/sa2.py` (free), seeded from `w1/X_order` (26.5 h), 60 min each on one core
(runs 1 and 2 got 35 min more from run 1's result; run 1 did not improve, run 2 started from run 1's order). One rng seed each: single runs, not multi-start (2 cores).

| Run | Transfers | Ends | Start | Plan | Start-end | Rides / walks | Static day med | Real days med / P80 | Under 22:14 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | MTA (min_transfer_time, 60 s default) | Far Rockaway-Mott Av -> Flushing-Main St | 02:00 (window 00-02, hit the edge) | **26:51** | 02:00 -> 28:51 | 75 / 33 | 26:29 | 37:06 / 38:28 | 0% |
| 2 | realistic table | same | 02:00 (same window) | **28:45** | 02:00 -> 30:45 | 69 / 32 | 28:23 | 35:37 / 37:12 | 0% |
| 3 | MTA | free (came out Far Rockaway -> Astoria-Ditmars) | free (04:51) | **25:31** | 04:51 -> 30:22 | 70 / 27 | 26:00 | 33:11 / 34:08 | 0% |

Real replay = 2026-10-07/08 x 7 start offsets (-30..+30), plan-following rider (`adaptive.py`), static = `--static`. Run 1's plan is pinned to the
window edge: each half hour of earlier start adds exactly 30 min (28:51 at 00:00, 26:51 at 02:00), so the true optimum starts later than 02:00. Run 2 vs 1 is a warm-started re-anneal, so +1:54 is a rough, not exact, transfer effect.
All three pass `verify.py` (475/475, 0 bad hops). Routes: `run*_*.json` (+ `.npy` solutions). Breakdown script: `breakdown.py`.

## Time by category (h)

| Run | Riding | of which rides that add no new station | Walking/running | Change time (model minimum) | Waiting | Initial wait |
|---|---|---|---|---|---|---|
| 1 | 19.88 | 2.07 (11 rides) | 3.02 | 0.59 | 3.01 | 0.37 |
| 2 | 21.24 | 2.15 (12) | 3.13 | 1.02 | 3.00 | 0.37 |
| 3 | 19.87 | 2.03 (13) | 2.31 | 0.62 | 2.73 | 0 |

## Diagnosis

- Running times are not the problem: the model uses the GTFS times as is. Weekday medians (min-max): A Far Rockaway -> Inwood-207 100 (96-115) min, 2 Wakefield-241 -> Flatbush Av 101 (96-112), 7 Flushing -> 34 St-Hudson Yards 38 (35-43). These look normal for the scheduled service, but I could not check them against outside sources (blocked). Real trains run late, which the static column already excludes.
- 475 vs 472: 475 is every GTFS parent station served on a weekday, SIR excluded. 469 (Ahn, 2016) + 3 Second Av stations opened in 2017 = 472, so the official list has 3 fewer than GTFS; I cannot identify which 3 offline. Likely merged pairs among same-name complexes (Franklin Av A45/S01, Times Sq 127/725/902/R16, Grand Central 631/723/901, Court Sq 719/G22, Canal St, Fulton St ...). Upper bound on their effect: all same-name walks add up to 27-33 min and the Franklin/Times Sq-Grand Central shuttle rides to under 10 min, so they cannot explain more than about half an hour. They do not force long detours.
- Gap to 22:14 is 3.3 h (run 3) to 4.6 h (run 1). Riding alone is 19.9 h, so a 22:14 plan leaves 2.4 h for all walking, changing and waiting over 70+ rides. The model has 5.7 h (run 3).
- Largest measured lever: transfer times (+1.9 h from MTA to the realistic table), then fixed ends and start window (+1.3 h run 1 vs 3, partly the 02:00 window edge), then waiting at night/idle (2.7-3.0 h), then walking (2.3-3.0 h; 27-33 street walks, longest 1.4-1.6 km). About 2 h of riding (11-13 rides) adds no new station (backtracking, e.g. the Rockaway Park spur, 6 Pelham Bay Park -> 59 St 41 min, 4 Woodlawn -> 161 St 18 min).
- Search is probably also short: the same code reached 24:25 under 1-minute transfers (README, older feed; that solution is infeasible on the current feed), and more annealing did not help run 1 (stuck at 26:51). A better seed/multi-start is the next thing to try; the 22 h record needs roughly 3 h of idle+walk time saved, which a 1-2 h anneal from a 26 h seed does not show signs of finding.
- Real days: 33-37 h medians, 0% under 22:14, driven by no-buffer connections at night (as in FINAL.md).
