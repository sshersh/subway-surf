"""Build the weekday timetable model for the Subway Challenge solver.

Output (model.npz + model.json):
  connections sorted by departure: dep_stop, arr_stop, dep_t, arr_t, trip, next_in_trip
  footpaths (CSR): walking links and GTFS inter-station transfers
  change time per station, station list, trip -> route
Two consecutive service days are included so a run can pass midnight.

    python3 model.py <gtfs_json_dir> <out> [--changes changes.json]

With --changes (from status/alerts.py), skipped and cut stops are applied to each service day
(see service.py). Stations no train stops at are then left out, so the route doesn't need them;
meta["dropped"] lists them.
"""
import json, math, sys, collections
import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
CHANGES = None
if "--changes" in sys.argv:
    from service import Changes
    CHANGES = Changes(sys.argv[sys.argv.index("--changes") + 1])
L = lambda n: json.load(open(f"{SRC}/{n}.json"))
stops, trips, transfers = L("stops"), L("trips"), L("transfers")
stop_times = L("stop_times")

WALK_SPEED = 1.4          # m/s, brisk walk
DETOUR = 1.3              # street-grid factor over straight line
WALK_MAX = 1600           # m straight-line cap for generated walking links
WALK_OVERHEAD = 120       # s to exit one station and enter the other
DEFAULT_CHANGE = 60       # s, default time to change trains within a station

parent = {s["stop_id"]: (s["parent_station"] or s["stop_id"]) for s in stops}
trip_info = {t["trip_id"]: t for t in trips if t["service_id"] == "Weekday" and t["route_id"] != "SI"}  # SIR needs the ferry; excluded like the official challenge

seqs = collections.defaultdict(list)
def tsec(t):
    h, m, s = map(int, t.split(":")); return h * 3600 + m * 60 + s
for st in stop_times:
    if st["trip_id"] in trip_info:
        seqs[st["trip_id"]].append((int(st["stop_sequence"]), parent[st["stop_id"]], tsec(st["arrival_time"]), tsec(st["departure_time"]), st["stop_id"]))
for v in seqs.values(): v.sort()
base_served = set(p for v in seqs.values() for _, p, _, _, _ in v)
if CHANGES:   # which direction each worded alert ("Flushing-bound 7 skips ...") applies to
    from service import resolve
    for text, line, d in resolve(CHANGES, seqs, {t: v["route_id"] for t, v in trip_info.items()}, stops):
        print(f"  direction: {line} {d}-platforms only  ({text})")

# runnable trips per service day: (day, gtfs trip id, stop times)
runs, nskip, ncut = [], 0, 0
for day in (0, 1):
    for t in sorted(seqs):
        if CHANGES:
            pieces, k, c = CHANGES.apply(seqs[t], trip_info[t]["route_id"], day); nskip += k; ncut += c
        else:
            pieces = [seqs[t]]
        runs.extend((day, t, p) for p in pieces)
if CHANGES:
    print(f"service changes: {nskip} stop times skipped, {ncut} cut")
served = set(p for day, _, v in runs if day == 0 for _, p, _, _, _ in v)   # stations trains stop at on the run day
runs = [(day, t, w) for day, t, v in runs for w in [[x for x in v if x[1] in served]] if len(w) >= 2]
stations = [s for s in stops if s["location_type"] == "1" and s["stop_id"] in served]
sid = {s["stop_id"]: i for i, s in enumerate(stations)}
N = len(stations)
all_parents = set(s["stop_id"] for s in stops if s["location_type"] == "1" and not s["stop_id"].startswith("S"))
print("weekday-served stations", N, "of", len(all_parents), "missing:", sorted(all_parents - served))
dropped = sorted(base_served - served)   # no train stops there on the run day: left out
if dropped:
    print("no train stops at (left out of the route):", dropped)

if CHANGES:
    # trips differ by day (and may be split): number every runnable piece; trip_ids holds its GTFS trip
    trip_ids = [t for _, t, _ in runs]
    T = len(runs)
    run_ix = list(range(T))
else:
    trip_ids = sorted(seqs)
    tix = {t: i for i, t in enumerate(trip_ids)}
    T = len(trip_ids)
    run_ix = [tix[t] + day * T for day, t, _ in runs]
route_of_trip = [trip_info[t]["route_id"] for t in trip_ids]

conns = []  # (dep_t, arr_t, dep_stop, arr_stop, trip)
for (day, t, v), ix in zip(runs, run_ix):
    off = day * 86400
    for a, b in zip(v, v[1:]):
        conns.append((a[3] + off, b[2] + off, sid[a[1]], sid[b[1]], ix))
conns.sort()
C = np.array(conns, dtype=np.int64)
dep_t, arr_t, dep_s, arr_s, trip = (C[:, i].copy() for i in range(5))
# next connection of the same trip
nxt = np.full(len(C), -1, dtype=np.int64)
last = {}
order = np.lexsort((dep_t, trip))
for k in range(len(order) - 1):
    i, j = order[k], order[k + 1]
    if trip[i] == trip[j]:
        nxt[i] = j

# change time at each station (seconds to get off one train and be ready for another)
#   same station: 1 min; cross-platform (GTFS 0) 30 s; the few big complexes GTFS rates 5 min -> 3 min
#   linked stations (different GTFS parents): 1 min + walk at ~1.1 m/s, never above the GTFS figure
SAME_STATION = {0: 30, 180: 60, 300: 180}
lat0 = {s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"])) for s in stops}
def link_time(a, b, gtfs_t):
    (la, oa), (lb, ob) = lat0[a], lat0[b]
    d = math.hypot((la - lb) * 111_000, (oa - ob) * 111_000 * math.cos(math.radians(40.72)))
    if gtfs_t == 0:            # GTFS 0 = cross-platform (e.g. Queensboro Plaza)
        return 30
    return int(min(gtfs_t, 60 + d / 1.1))
chg = np.full(N, DEFAULT_CHANGE, dtype=np.int64)
same = collections.defaultdict(list)
foot = collections.defaultdict(dict)
for tr in transfers:
    a, b = parent.get(tr["from_stop_id"], tr["from_stop_id"]), parent.get(tr["to_stop_id"], tr["to_stop_id"])
    if a not in sid or b not in sid:
        continue
    g = int(tr["min_transfer_time"] or 0)
    if a == b:
        same[sid[a]].append(SAME_STATION.get(g, DEFAULT_CHANGE))
    else:
        tt = max(30, link_time(a, b, g))
        foot[sid[a]][sid[b]] = min(tt, foot[sid[a]].get(sid[b], 1e9))
for s, v in same.items():
    chg[s] = max(v)   # a station's slowest same-station transfer applies to every change there

lat = np.array([float(s["stop_lat"]) for s in stations]); lon = np.array([float(s["stop_lon"]) for s in stations])
def dist_m(i, j):
    dy = (lat[i] - lat[j]) * 111_000; dx = (lon[i] - lon[j]) * 111_000 * math.cos(math.radians(40.72))
    return math.hypot(dx, dy)
nwalk = 0
for i in range(N):
    for j in range(N):
        if i != j:
            d = dist_m(i, j)
            if d <= WALK_MAX:
                t = int(WALK_OVERHEAD + d * DETOUR / WALK_SPEED)
                if t < foot[i].get(j, 1e9):
                    if j not in foot[i]: nwalk += 1
                    foot[i][j] = t
fp_ptr = np.zeros(N + 1, dtype=np.int64); fp_to = []; fp_t = []
for i in range(N):
    for j, t in sorted(foot[i].items()):
        fp_to.append(j); fp_t.append(t)
    fp_ptr[i + 1] = len(fp_to)

np.savez(OUT + ".npz", dep_t=dep_t, arr_t=arr_t, dep_s=dep_s, arr_s=arr_s, trip=trip, nxt=nxt,
         chg=chg, fp_ptr=fp_ptr, fp_to=np.array(fp_to, dtype=np.int64), fp_t=np.array(fp_t, dtype=np.int64),
         lat=lat, lon=lon)
json.dump({"stations": [s["stop_id"] for s in stations], "names": [s["stop_name"] for s in stations],
           "trip_route": route_of_trip, "trip_ids": trip_ids, "T": T, "dropped": dropped,
           "changes": CHANGES.raw.get("hash") if CHANGES else None,
           "params": dict(WALK_SPEED=WALK_SPEED, DETOUR=DETOUR, WALK_MAX=WALK_MAX, WALK_OVERHEAD=WALK_OVERHEAD, DEFAULT_CHANGE=DEFAULT_CHANGE)},
          open(OUT + ".json", "w"))
print("trips", T, "connections", len(C), "footpaths", len(fp_to), "(generated walks", nwalk, ")")

# line keys (route, direction) per trip, used by the line-aware seed and solver
keys = sorted({(trip_info[t]["route_id"], trip_info[t]["direction_id"]) for t in set(trip_ids)})
kid = {k: i for i, k in enumerate(keys)}
tk = np.array([kid[(trip_info[t]["route_id"], trip_info[t]["direction_id"])] for t in trip_ids] * (1 if CHANGES else 2))
np.save(OUT + "_tkey.npy", tk)
json.dump([list(k) for k in keys], open(OUT + "_keys.json", "w"))
