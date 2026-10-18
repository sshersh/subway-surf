# Final round: express rules, normal weekday service

Real-day replay = 2 days (2026-10-07/08) x 7 start offsets (-30..+30 min) = 14 runs. Offsets mostly catch the
same trains, so there are really only a few independent outcomes per day. Unfinished = not done 40 h after start.

| Route | Plan | Median | P80 | Max | Under 22:14 | Unfinished | Static-day median |
|---|---|---|---|---|---|---|---|
| **n (daytime start, 05:12 Far Rockaway) = final** | 25:15 | **29:35** | **29:49** | 30:41 | 0% | 0 | 25:15 |
| robust_express | 25:57 | 31:29 | 32:11 | 32:19 | 0% | 0 | 25:49 |
| hand_express | 25:38 | 32:20 | 33:45 | 34:45 | 0% | 0 | 27:07 |
| sensitivity/d_best (no hard slack) | 24:47 | 30:33 | 35:46 | 36:01 | 0% | 0 | 25:07 |

Dumb baseline (keep plan order, next train, no search): n 29:54, robust 32:58, hand 33:15, d_best 31:49 (medians).
The fixed rider is at least as good as the baseline on every route, in median and P80 (n: 29:35/29:49 vs 29:54/31:03).

Chosen route: `results/final_express.json` (= sensitivity/n; `verify.py --express` passes: 475/475 stations, 0 bad hops).

## Evaluator fix (headways/adaptive.py)

- Static day (timetable as reality), offsets -30..+30: robust_express 25:49 median (plan 25:57), n 25:15 (plan 25:15). Within 15 min.
  d_best ends 20 min over its plan and hand_express +1.5 h (P80 +4 h): those plans have no slack, so any shift costs.
- The old rider re-planned after every ride more than 3 min late (35-80 re-plans per run), each time re-ordering the remaining
  stations with a short local search. Measured against the baseline, that made things worse (robust: re-planning rider
  median 37 h and runs scored unfinished, plan-following baseline 33 h). Tests: postpone rule (target pushed 40 places back after a 20 min delay):
  worse (all unfinished in one test); lateness trigger 15 min plus 15 or 40 min margin: 36-37 h; re-plan only on replaced rides: 35 h;
  re-plan with no search: worse still. Projected finishes on the static timetable jump by hours after a 10-15 min slip
  (e.g. +4 h at Avenue U for 14 min late) because the plan chains several overnight, 15-30 min headway connections; a re-plan
  can only see that, not avoid it, and its weak search then reorders the tour into new fragile chains.
- So the rider now follows the plan: next train of the planned line, switch to any train when the line is gone or 10+ min late with
  an alternative 5 min sooner (existing rule), and re-plan with the local search only when the plan runs out with stations left.
  `--replan` restores the full re-planner, `--dumb` the baseline, `--static` the validation day. Postpone code stays behind POSTPONE_ON=1.
- Runs are parallel over 2 processes (about 1 min per route) and capped at 900 s wall each.
- Loss attribution (results/loss_attribution.txt) now ends with an unattributed remainder (negative: planned slack soaks up part of
  the delays) instead of a +10 h "re-plan residual". For n the biggest items are replaced rides at night.

## Is 22:14 beatable?

Not with what we have. On paper under express rules the best plan is 24:47 (no slack at all) and the best with realistic
transfers and slack is 25:15; both are 2.5-3 h over 22:14. On real days the same routes took 29.5-32 h at the median, and not one of
56 runs finished under 22:14. Every sensitivity (no pass deny list, MTA transfer times, faster running) stayed above 25:15. Getting under
22:14 would need transfers and running faster than the realistic model allows plus a day with almost no delays. Caveats: two weekdays
of data, feed holes filled from the timetable, street running estimated, and the planner is heuristic, not proven optimal.

## Top 3 practical risks of the chosen route (n)

1. Overnight connections (22 of 79 rides run 23:00-06:00). The worst boardings in the replay are all night: F Roosevelt Island -> Jackson Hts
   (up to +3 h), 6 Grand Central -> Westchester Sq/Zerega (about 03:00, +3 h), 5 Eastchester-Dyre (+3 h). With 15-30 min night headways one
   miss cascades into the next sparse service.
2. Zero-slack transfers: 21 of 59 same-station changes have at most 2 min of slack, several at 0 min. Wait loss is 4 h per run on average,
   and the model's transfer times are estimates that can't be checked from here.
3. Station-pass credit and street running: the finish depends on express pass-throughs counting (deny list in realistic.py) and on about
   19 street walks or runs (longest 1.7 km at 2.5 m/s); a station that doesn't count, or a closure on a walk, costs a detour.
