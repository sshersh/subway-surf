# Subway Surf

A route planner for the NYC Subway Challenge, which means visiting every subway station in one run. It plans against the MTA's real weekday timetable and includes a map viewer that plays the route back.

**Best routes found so far** (heuristic results, not proven optima), on the weekday schedule with 1-minute transfers:

| Rules | Time | Start | Finish | Trains | Walks |
|---|---|---|---|---|---|
| **Local**: the train must stop at every station (the full-system record rule) | **25 h 06 min** | Far Rockaway–Mott Av, 05:52 | Pelham Bay Park, 06:58 next day | 79 | 26 |
| **Express**: passing through a station counts | **24 h 59 min** | Far Rockaway–Mott Av, 08:13 | Pelham Bay Park, 09:12 next day | 73 | 32 |

The official record is 22 h 14 m for 472 stations (Kate Jones, 2023), set under local rules with running and buses allowed. Trail of Bits reported 20 h 42 min under express rules, but that's an estimate from an undirected graph with average waits, never checked against the timetable. Both routes here pass `solver/verify.py` against the raw GTFS.

Open `viewer/index.html` in a browser to watch it play back.

## Rules modeled

- **Local rules** (default): a station counts only when a train you're riding **stops** there.
- **Express rules**: a station also counts when your train passes through it without stopping. `solver/passes.py` works out which stations each express hop passes: the station must lie between the hop's two stops on some other trip, and within 120 m of the express's own track shape.
- Staten Island Railway is excluded: it can't be reached without the ferry, and the challenge excludes it.
- Weekday GTFS schedule. Trains run exactly on time.
- Changing trains takes 1 min within a station, 30 s cross-platform, and 3 min at the six big complexes the MTA rates at 5 min. Between linked stations (e.g. Times Sq ↔ Port Authority) it takes 1 min plus the walk at 1.1 m/s, never more than the MTA's `min_transfer_time`. The MTA's own figures (mostly 3 min) are conservative trip-planner allowances, not measured walks.
- Walking between stations is allowed up to 1.6 km straight-line. The walking model is 1.4 m/s with a ×1.3 street factor, plus 2 min to leave one station and enter the other.

## How it works

1. **`solver/model.py`** turns the GTFS feed into about 455k time-ordered train connections across two service days, plus transfers and walking links.
2. **Seeds** are first guesses at the route:
   - `solver/seed.py` builds an open-path TSP over all stations, using static travel times (LKH via `elkai`).
   - `solver/gseed.py` builds a line-aware version: a generalized TSP over (station, line, direction) states. Staying on a train is free, and boarding costs half the headway. It's solved through the Noon–Bean transform.
   - `solver/tseed.py` is the time-of-day-aware version. Given expected visit times (`--times`, e.g. from a previous solution), each boarding costs half the gap between trains on that line around that hour, or the wait for the next train if none run then. Ride segments use that hour's run times, so an express making local stops at night is only cheap at night. Iterate: solve, re-estimate times, solve again.
3. **`solver/engine.py`** replays a station order against the timetable using the Connection Scan Algorithm, compiled with numba. From each point it takes the earliest train to the next station not yet visited, and every stop along the way counts. `solver/fast.py` makes the replay incremental: a change at position *p* re-simulates only from *p* onward, at about 1 ms per evaluation.
4. **`solver/sa2.py`** runs simulated annealing over the station order and start time. Moves are segment relocation, reversal, swaps and start-time shifts.
   - `solver/sa3.py` is a line-constrained variant built on `fast2.py`. It's more robust to start-time changes but scored worse in testing (29.3 h vs 25.9 h).
5. **`solver/export.py`** writes viewer rows and an itinerary, then checks the result: walks start where you are, you board after you arrive, times only move forward, and every station is visited.

## Run it

```bash
pip install -r requirements.txt

# 1. Get the subway GTFS as JSON (an npm mirror of the MTA feed, refreshed daily)
npm pack mta-gtfs-static && mkdir -p gtfs && tar xzf mta-gtfs-static-*.tgz -C gtfs
python3 -c "import zipfile; zipfile.ZipFile('gtfs/package/gtfs_json.zip').extractall('gtfs')"
GTFS=$PWD/gtfs/gtfs_json/subway   # stops.json, trips.json, stop_times.json, ...

# 2. Build the model and a seed, then anneal (run from solver/)
cd solver
python3 model.py $GTFS model
python3 gseed.py $GTFS run 1 0.5                  # line-aware seed -> run_gseed.npy
python3 -c "import numpy as np; np.save('run_order.npy', np.load('run_gseed.npy')[0])"
python3 sa2.py run_order.npy 1 20 best.npy 150 2   # 20 minutes
python3 export.py best.npy ../results/best_route.json
python3 verify.py $GTFS ../results/best_route.json        # independent check against raw GTFS

# Express rules: pass-through map, line-aware seed with pass-through states, anneal, export
python3 passes.py $GTFS model                               # -> model_pass.npz
python3 tseed.py $GTFS X 1 0.5 --times times.json --passes model_pass.npz
python3 -c "import numpy as np; np.save('X_order.npy', np.load('X_gseed.npy')[0])"
python3 sax.py X_order.npy 1 15 bestx.npy 120 2
python3 export.py bestx.npy ../results/best_route_express.json --express
python3 verify.py $GTFS ../results/best_route_express.json --express

# 3. Rebuild the viewer
cd ..
python3 viewer/prep.py $GTFS viewer/data.json
python3 viewer/build.py viewer/data.json results/best_route.json viewer/index.html results/best_route_express.json
```

To replay the saved best routes, run `python3 export.py ../results/best_solution.npy out.json` (and `best_solution_express.npy … --express`) from `solver/` after building the model. Its timings depend on the GTFS version: the saved route was solved on feed `20260826` (valid 2026-05-26 to 2026-10-31).

The MTA's own feed is at <https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip> (CSV). The scripts expect the JSON export, but each file has the same columns.

## Live service status

`.github/workflows/status.yml` runs every 15 minutes (GitHub may delay scheduled runs). It downloads the MTA subway alerts feed, then runs `status/check_status.py` to compare each alert with every stop the route needs on each line. It then redeploys GitHub Pages with a fresh `status.json`, and the page shows a banner at the top:

- **Blocks route** (red): an active suspension, skipped stops or express run hits a station the plan needs on that line.
- **May affect** (amber): a disruption on a line the plan uses, where the alert names no stations.
- **Delays**: delays on a line the plan uses. The route's timing assumes trains run on time.
- **Planned work during the next run**: planned alerts that overlap a leg's clock time if the run started at its scheduled time on the next weekday.

The banner is only shown where a `status.json` sits next to the page, so it's on GitHub Pages but not in a local copy. For this to work, set **Settings → Pages → Source** to **GitHub Actions**.

## Results format

`results/best_route.json`:
- `rows` has one entry per station arrival: `stop_id`, `time`, and `route`, which is blank for a walk. Times past 24:00 are the next day.
- `itin` has one entry per leg.
- `stats` holds the totals.

The viewer's "Compare another route" box accepts the same CSV or JSON.

## Ideas to get closer to the record

- Running speed between stations, and measured transfer times (e.g. from station layouts in OpenStreetMap).
- Allowing buses, which Guinness permits.
- Counting with the 472 rule, where some transfer complexes count as one station.
- A replay that prefers trains covering new stations, and robustness to delays.
