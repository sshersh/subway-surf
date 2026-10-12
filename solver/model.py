"""Build the weekday timetable model for the Subway Challenge solver.

Output (model.npz + model.json):
  connections sorted by departure: dep_stop, arr_stop, dep_t, arr_t, trip, next_in_trip
  footpaths (CSR): walking links and GTFS inter-station transfers
  change time per station, station list, trip -> route
Two consecutive service days are included so a run can pass midnight.
"""
import json, math, sys, collections
import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
L = lambda n: json.load(open(f"{SRC}/{n}.json"))
stops, trips, transfers = L("stops"), L("trips"), L("transfers")
stop_times = L("stop_times")

WALK_SPEED = 1.4          # m/s, brisk walk
DETOUR = 1.3              # street-grid factor over straight line
WALK_MAX = 1600           # m straight-line cap for generated walking links
WALK_OVERHEAD = 120       # s to exit one station and enter the other
DEFAULT_CHANGE = 180      # s, matches GTFS same-station min_transfer_time

parent = {s["stop_id"]: (s["parent_station"] or s["stop_id"]) for s in stops}
trip_info = {t["trip_id"]: t for t in trips if t["service_id"] == "Weekday" and t["route_id"] != "SI"}  # SIR needs the ferry; excluded like the official challenge

seqs = collections.defaultdict(list)
def tsec(t):
    h, m, s = map(int, t.split(":")); return h * 3600 + m * 60 + s
for st in stop_times:
    if st["trip_id"] in trip_info:
        seqs[st["trip_id"]].append((int(st["stop_sequence"]), parent[st["stop_id"]], tsec(st["arrival_time"]), tsec(st["departure_time"])))

served = set(p for v in seqs.values() for _, p, _, _ in v)
stations = [s for s in stops if s["location_type"] == "1" and s["stop_id"] in served]
sid = {s["stop_id"]: i for i, s in enumerate(stations)}
N = len(stations)
all_parents = set(s["stop_id"] for s in stops if s["location_type"] == "1" and not s["stop_id"].startswith("S"))
print("weekday-served stations", N, "of", len(all_parents), "missing:", sorted(all_parents - served))

trip_ids = sorted(seqs)
tix = {t: i for i, t in enumerate(trip_ids)}
T = len(trip_ids)
route_of_trip = [trip_info[t]["route_id"] for t in trip_ids]

conns = []  # (dep_t, arr_t, dep_stop, arr_stop, trip)
for day in (0, 1):
    off = day * 86400
    for t in trip_ids:
        v = sorted(seqs[t])
        for a, b in zip(v, v[1:]):
            conns.append((a[3] + off, b[2] + off, sid[a[1]], sid[b[1]], tix[t] + day * T))
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

# change time at each station
chg = np.full(N, DEFAULT_CHANGE, dtype=np.int64)
foot = collections.defaultdict(dict)
for tr in transfers:
    a, b = parent.get(tr["from_stop_id"], tr["from_stop_id"]), parent.get(tr["to_stop_id"], tr["to_stop_id"])
    if a not in sid or b not in sid:
        continue
    t = int(tr["min_transfer_time"] or DEFAULT_CHANGE)
    if a == b:
        chg[sid[a]] = t
    else:
        foot[sid[a]][sid[b]] = min(t, foot[sid[a]].get(sid[b], 1e9))

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
           "trip_route": route_of_trip, "trip_ids": trip_ids, "T": T,
           "params": dict(WALK_SPEED=WALK_SPEED, DETOUR=DETOUR, WALK_MAX=WALK_MAX, WALK_OVERHEAD=WALK_OVERHEAD, DEFAULT_CHANGE=DEFAULT_CHANGE)},
          open(OUT + ".json", "w"))
print("trips", T, "connections", len(C), "footpaths", len(fp_to), "(generated walks", nwalk, ")")

# line keys (route, direction) per trip, used by the line-aware seed and solver
keys = sorted({(trip_info[t]["route_id"], trip_info[t]["direction_id"]) for t in trip_ids})
kid = {k: i for i, k in enumerate(keys)}
tk = np.array([kid[(trip_info[t]["route_id"], trip_info[t]["direction_id"])] for t in trip_ids] * 2)
np.save(OUT + "_tkey.npy", tk)
json.dump([list(k) for k in keys], open(OUT + "_keys.json", "w"))
