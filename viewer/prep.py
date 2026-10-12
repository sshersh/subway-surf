"""Turn the MTA subway GTFS (JSON export) into a compact data blob for the map page."""
import json, sys, math, collections

SRC = sys.argv[1]
OUT = sys.argv[2]
L = lambda n: json.load(open(f"{SRC}/{n}.json"))

routes = L("routes"); stops = L("stops"); trips = L("trips"); shapes = L("shapes")
feed = L("feed_info")[0]
stop_times = L("stop_times")

parent = {s["stop_id"]: (s["parent_station"] or s["stop_id"]) for s in stops}
trip_route = {t["trip_id"]: t["route_id"] for t in trips}
trip_shape = {t["trip_id"]: t["shape_id"] for t in trips}
trip_svc = {t["trip_id"]: t["service_id"] for t in trips}

# Lines serving each station, and trip stop sequences (weekday)
serves = collections.defaultdict(set)
trip_stops = collections.defaultdict(list)
for st in stop_times:
    tid = st["trip_id"]
    p = parent[st["stop_id"]]
    serves[p].add(trip_route[tid])
    if trip_svc[tid] == "Weekday":
        trip_stops[tid].append((int(st["stop_sequence"]), p, st["arrival_time"], st["departure_time"]))
for v in trip_stops.values():
    v.sort()

order = {r["route_id"]: i for i, r in enumerate(routes)}
stations = []
for s in stops:
    if s["location_type"] != "1" or s["stop_id"] not in serves:
        continue
    stations.append({
        "id": s["stop_id"], "n": s["stop_name"],
        "lat": round(float(s["stop_lat"]), 6), "lon": round(float(s["stop_lon"]), 6),
        "r": sorted(serves[s["stop_id"]], key=lambda r: order[r]),
    })

# Shapes: keep per route only shapes that add new geometry, then simplify
pts = collections.defaultdict(list)
for p in shapes:
    pts[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]), float(p["shape_pt_lat"])))
for k in pts:
    pts[k] = [(x, y) for _, x, y in sorted(pts[k])]

shape_count = collections.Counter(trip_shape.values())
route_shapes = collections.defaultdict(set)
for tid, sid in trip_shape.items():
    if sid in pts:
        route_shapes[trip_route[tid]].add(sid)

def dist_m(a, b):
    dx = (a[0] - b[0]) * 84000; dy = (a[1] - b[1]) * 111000
    return math.hypot(dx, dy)

def rdp(p, eps):
    if len(p) < 3:
        return p
    a, b = p[0], p[-1]
    ax, ay = a; bx, by = b
    dx, dy = (bx - ax) * 84000, (by - ay) * 111000
    L2 = dx * dx + dy * dy
    best, bi = -1, 0
    for i in range(1, len(p) - 1):
        px, py = (p[i][0] - ax) * 84000, (p[i][1] - ay) * 111000
        if L2 == 0:
            d = math.hypot(px, py)
        else:
            t = max(0, min(1, (px * dx + py * dy) / L2))
            d = math.hypot(px - t * dx, py - t * dy)
        if d > best:
            best, bi = d, i
    if best > eps:
        return rdp(p[: bi + 1], eps)[:-1] + rdp(p[bi:], eps)
    return [a, b]

lines = {}
for rid, sids in route_shapes.items():
    kept, grid = [], set()
    def cell(q): return (round(q[0] * 2000), round(q[1] * 2000))  # ~40-55 m cells
    for sid in sorted(sids, key=lambda s: (-len(pts[s]), -shape_count[s])):
        cells = {cell(q) for q in pts[sid]}
        new = len(cells - grid)
        if not kept or new > 5:
            kept.append(sid); grid |= cells
    lines[rid] = [[[round(x, 5), round(y, 5)] for x, y in rdp(pts[s], 6)] for s in kept]

rinfo = [{"id": r["route_id"], "c": "#" + r["route_color"], "name": r["route_long_name"]} for r in routes if r["route_id"] in lines]

# ---- Sample route: chained real weekday trips ----
def tsec(t):
    h, m, s = map(int, t.split(":")); return h * 3600 + m * 60 + s
def fmt(s):
    return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"

def ride(route, a, b, after):
    best = None
    for tid, seq in trip_stops.items():
        if trip_route[tid] != route:
            continue
        ids = [x[1] for x in seq]
        if a in ids and b in ids and ids.index(a) < ids.index(b):
            i = ids.index(a)
            dep = tsec(seq[i][3])
            if dep >= after and (best is None or dep < best[0]):
                best = (dep, tid, i, ids.index(b))
    dep, tid, i, j = best
    seq = trip_stops[tid]
    return [(seq[k][1], tsec(seq[k][2]), route) for k in range(i, j + 1)]

rows = []
leg = ride("7", "701", "726", tsec("06:00:00"))           # Flushing-Main St -> 34 St-Hudson Yards
rows += leg
walk_arr = leg[-1][1] + 11 * 60                             # walk to 34 St-Penn Station (8 Av)
rows.append(("A28", walk_arr, ""))
leg = ride("C", "A28", "A42", walk_arr + 60)                # C to Hoyt-Schermerhorn
rows.append(("A28", leg[0][1], "C")); rows += leg[1:]
leg = ride("G", "A42", "G22", leg[-1][1] + 120)             # G to Court Sq
rows.append(("A42", leg[0][1], "G")); rows += leg[1:]
sample = [{"stop_id": s, "time": fmt(t), "route": r} for s, t, r in rows]
# first row is the start: no route needed
sample[0]["route"] = ""

data = {
    "feed": {"version": feed["feed_version"], "start": feed["feed_start_date"], "end": feed["feed_end_date"]},
    "routes": rinfo, "lines": lines, "stations": stations, "sample": sample,
}
json.dump(data, open(OUT, "w"), separators=(",", ":"))
print("stations", len(stations), "routes", len(rinfo),
      "points", sum(len(l) for v in lines.values() for l in v), "sample rows", len(sample),
      sample[0], sample[-1])
