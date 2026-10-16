# Realistic model: transfers, running, pass-throughs, robustness

Everything here is in `solver/realistic.py`; `model.py --legacy` restores the original assumptions.
Station layouts come from MTA station diagrams and published station descriptions (levels, island vs
side platforms, passage lengths), not measurements. External sites were unreachable from the build
environment, so the values are estimates and can't be checked against live sources from here. Each
number is for a fit, experienced rider, platform to platform, with normal crowds.

## Changing trains in one station (same GTFS parent)

The old model used 60 s everywhere (30 s at "cross-platform" stations). A change between trains in
one station almost always means one of these:

- **cross-platform** (express ↔ local, same direction, island platform): about 30–60 s if the trains
  line up. The model cannot tell same-direction from reversing, so one value per station covers the
  slower case.
- **reversing** (stairs to the mezzanine or a crossunder, then down): about 90–150 s.
- **two-level stations** (Lexington 125/86/59 St, Union Sq, Brooklyn Bridge; 34 St-Penn; 7 Av 53 St;
  Rockefeller Ctr; 2 Av; Atlantic Av; Crown Hts): 150 s.

| Rule | Time |
|---|---|
| Default through station | 120 s |
| Terminal where every train starts or ends (arrivals and departures share an island) | 60 s |
| Express/local pairs on one el structure (Junction Blvd, 61 St, Queensboro Plaza, Parkchester, Hunts Point, 3 Av-138, Euclid, Marcy, Broadway Jct J/Z) | 90 s |
| Two-level stations listed above, Penn Station, Atlantic Av, 145 St (A/C, two levels) | 150 s |
| Jamaica Center, Sutphin Blvd-Archer (deep, long escalators), Coney Island (large terminal) | 180 s |

The full per-station list is `realistic.SAME`.

## Linked stations (passageways and short street links)

Each pair has one time, both directions. The old model used 60 s + distance/1.1 m/s, capped at the MTA
figure, which produced 79 s for Fulton St J ↔ A/C. Main changes (old → new):

| Link | Old | New | Why |
|---|---|---|---|
| Fulton St J/Z (M22) ↔ A/C (A38) | 1:19 | 4:00 | long passage, two level changes, Fulton Center crowds |
| Fulton St 2/3 ↔ A/C, 4/5 ↔ A/C | 3:00 | 4:00 | Dey St passage / Fulton Center |
| 14 St A/C/E ↔ 8 Av L | 1:30 | 3:00 | L platform is a level below the A/C/E mezzanine at the far end |
| Atlantic Av B/Q ↔ 2/3/4/5, D/N/R ↔ 2/3/4/5 | 3:00 | 4:00 | long passageways through the Barclays complex |
| WTC (E) ↔ Park Place (2/3) | 1:30 | 4:00 | through the Oculus/PATH concourse |
| WTC (E) ↔ Chambers St (A/C) | 3:00 | 3:00 | same platform level, long walk along the passage |
| 5 Av (7) ↔ 42 St-Bryant Pk (F/M) | 2:20 | 4:00 | 7 platform is very deep, passage under the park |
| 51 St (6) ↔ Lexington Av/53 St (E/M) | 3:00 | 5:00 | E/M platforms are deep (long escalators) |
| 168 St (1) ↔ 168 St (A/C) | 1:47 | 5:00 | the 1 is elevator-only |
| Times Sq 7 ↔ others, Port Authority ↔ others | 3:00–5:00 | 4:00–6:00 | long passages |
| Court Sq 7 ↔ E/M, G ↔ E/M | 2:00–5:00 | 4:00–5:00 | long moving walkway passage |
| Broadway Junction A/C ↔ J/Z, L | 2:00–3:00 | 5:00 | street-level crossover between structures |
| Grand Central 4/5/6 ↔ 7, ↔ shuttle | 2:00 | 4:00 | |
| Queensboro Plaza N/W ↔ 7 | 0:30 | 1:30 | cross-platform one direction, stairs the other |
| 145 St, W 4 St (two levels) | 1:00 | 2:30 | |

Pairs not listed fall back to `max(60 s + distance / 1.2 m/s, MTA min_transfer_time)` (90 s if the MTA
gives 0). The full list is `realistic.LINK`.

## Walking and running between stations

| | Old | New |
|---|---|---|
| Street factor | ×1.3 | ×1.3 |
| Station exit + entry | 120 s | 120 s |
| Speed | 1.4 m/s | 1.4 m/s for the first 300 m (straight line), then 2.5 m/s |
| Cap | 1.6 km straight line | 2.0 km straight line |

2.5 m/s (9 km/h) is an easy jog with waits at crossings included, sustainable for short stretches by
someone 15+ hours in. Examples (station to station, platform to platform):

| Link | Straight line | Old | New |
|---|---|---|---|
| 0.5 km straight line | 0.5 km | 9.7 min | 8.4 min |
| 1.0 km (e.g. Gun Hill Rd ↔ Norwood-205 St) | 1.0 km | 17.5 min | 12.7 min |
| 1.45 km (Beach 67 St ↔ Beach 90 St) | 1.45 km | 24.4 min | 16.6 min |
| 1.62 km (Van Cortlandt Park-242 St ↔ Mosholu Pkwy) | 1.62 km | not allowed | 18.1 min |

## Pass-through policy (express rules)

A station counts as passed only if the express track physically runs through the station box,
alongside the platforms. `passes.py` keeps its geometric test (the station lies between the hop's stops
on another trip and within 120 m of the train's shape); `realistic.PASS_DENY` then removes every station
where the express runs on a separate level, in a separate tunnel or on bypass tracks, and stations whose
layout couldn't be confirmed (when unsure, deny). `verify.py --express` rejects a route that counts a
denied station.

Denied (all lines):

| Station | Reason |
|---|---|
| DeKalb Av | D/N use the Manhattan Bridge bypass tracks |
| 23 St, 14 St (6 Av) | B/D express runs on a separate deep level |
| 46 St, Steinway St (Queens Blvd) | express in a separate tunnel; E/F count 65 St, Northern Blvd and 36 St but not these |
| 51 St, 68 St, 77 St, 96 St, 103 St, 110 St, 116 St (Lexington) | 4/5 express on the lower level north of 42 St |
| 138 St-Grand Concourse | 4 express arrangement not verified |
| 161 St-Yankee Stadium, 155 St (Concourse) | two-level station; D rush express doesn't count them |
| Bergen St, Grand Army Plaza (Eastern Pkwy) | two-level, express on the lower level |
| Bergen St, Carroll St, Smith-9 Sts, 4 Av-9 St, Fort Hamilton Pkwy (Culver) | F express on a lower level or not verified |
| 50 St (8 Av), 163 St, 155 St (8 Av) | arrangement not verified |
| 169 St, Sutphin Blvd, Briarwood (Hillside Av) | arrangement not verified |

Allowed (express through the station box): 7 Av IRT locals (86/79/66/59/50, 28/23/18, Christopher,
Houston, Canal, Franklin); Lexington 33/28/23, Astor Pl, Bleecker, Spring, Canal; Eastern Pkwy-Brooklyn
Museum, Nostrand, Kingston; the 3-track els (White Plains Rd, Pelham, Flushing, Jamaica, West End);
CPW 135–72 St; 8 Av 23 St and Spring St; Concourse 182-183/174-175/170/167 St; Brighton and 4 Av local
stops; Broadway BMT locals; Queens Blvd 67 Av–Elmhurst Av, 65 St, Northern Blvd, 36 St, 75 Av.

Result on the weekday timetable: 121 distinct stations can be passed (was 133).

## Robust objective

`solver/robust.py` replays a station order like `expr.py`, with two changes:

1. **Hard minimum slack.** A boarding needs the rider ready (arrival + change time, or end of a walk)
   `buf` seconds before departure. `buf` depends on the headway to the next train making the same hop on
   the same line: 0 under 6 min, 1 min for 6–10 min, 2 min for 10–15 min, 3 min for 15 min or more;
   +1 min at night (23:00–06:00) when the headway is 10 min or more. Staying on the same train and the
   first boarding are exempt.
2. **Expected real-day loss.** Each boarding adds the calibrated expected lateness at the alighting stop
   for its slack (`solver/loss_table.json`, built by `headways/calibrate.py`): for ~60k sampled scheduled
   boardings on 2026-10-07/08, a rider ready `slack` seconds before the scheduled departure takes the
   first real train of that line that reaches the alighting stop; loss = real − scheduled arrival.
   Grouped by headway class (<5, 5–7.5, 7.5–10, 10–15, 15–25, 25+ min) and day/night, plus a per-line
   adjustment shrunk toward 0, floored at 0, capped at 30 min. A street walk counts its slack 45 s
   shorter. Examples (mean loss, minutes):

   | Slack | day, <5 min hw | day, 7.5–10 | day, 10–15 | night, 10–15 | night, 15–25 |
   |---|---|---|---|---|---|
   | 0 | 2.2 | 4.5 | 5.2 | 7.7 | 13.7 |
   | 2 min | 0.5 | 1.9 | 2.3 | 4.7 | 10.4 |
   | 5 min | 0 | 0 | 0.7 | 3.1 | 9.4 |
   | 10 min | 0 | 0 | 0 | 0 | 6.9 |

   Night service with 15–25 min headways loses ~10 min per boarding even with 5 min slack: the real
   night trains run irregularly (and some are missing from the feed), so short overnight hops are
   expensive whatever the slack. Night per-line adjustments are large (2: +5.9 min, 6: +6.7, 4: +3.3,
   3: +2.8; J −5.2, G −4.4).
   Without the table, robust.py falls back to a Laplace miss model (P(miss) = ½(1 + x/2)e^−x, x = slack/B,
   B = 96 s day / 132 s night) times the headway.

## Adaptive real-day evaluation

`headways/adaptive.py` rides a route on the actual train movements of 2026-10-07 and 2026-10-08
(subwaydata.nyc, from the `data-sample` branch), at 7 start offsets (−30…+30 min). The rider follows the
planned rides (first real train of the planned line, realistic change times), and after arriving 3+ min
late, a replaced ride or the plan running out, chooses between keeping the remaining plan and a fresh
plan (short local search + the robust planner from the real position), whichever projects earlier on
the timetable. Feed holes (a line with ≤20% of its scheduled movements in a 30-min window, e.g. the 42 St
shuttle at 17:00 on 10-07) and 00:00–05:00 on the run day (whose trips are in the previous day's file,
not in the sample) are filled with timetable trips. 10-08 has no next-day file; 10-07's file is used
for its overnight part (marked proxy). A run not finished 40 h after its start counts as 48 h.
Validation: `--static` replays on the timetable itself and reproduces the plan (25:49 vs 25:57).

`sar.py` anneals plan time + weight × expected miss cost (`--weight`, `--soft` drops the hard rule).
