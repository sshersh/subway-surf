"""Stations each train hop passes through without stopping (for the 'express' rules).

A hop A->B on a trip passes station X when some other trip stops at A, then X, then B in that order
(so X lies between them on the same corridor) AND X sits within PASS_TOL metres of this trip's own
track shape between A and B. The shape test keeps out stations on a different line that happens to
connect A and B (and stations on lines that merely cross under or over).

    python3 passes.py <gtfs_json_dir> model     -> model_pass.npz (CSR per connection)
"""
import sys, json, math, collections
import numpy as np

SRC, OUT = sys.argv[1], sys.argv[2]
PASS_TOL = 120.0   # m from the express track shape
L = lambda n: json.load(open(f"{SRC}/{n}.json"))
stops = {s["stop_id"]: s for s in L("stops")}
trips = {t["trip_id"]: t for t in L("trips")}
meta = json.load(open(OUT + ".json")); m = np.load(OUT + ".npz")
st = meta["stations"]; sid = {s: i for i, s in enumerate(st)}; T = meta["T"]
parent = {k: (v["parent_station"] or k) for k, v in stops.items()}
KX = 111_000 * math.cos(math.radians(40.72)); KY = 111_000
xy = {s: (float(stops[s]["stop_lon"]) * KX, float(stops[s]["stop_lat"]) * KY) for s in st}

# stop sequences of weekday trips (parents)
seq = collections.defaultdict(list)
wk = set(meta["trip_ids"])
for r in L("stop_times"):
    if r["trip_id"] in wk:
        seq[r["trip_id"]].append((int(r["stop_sequence"]), parent[r["stop_id"]]))
seqs = {t: [p for _, p in sorted(v)] for t, v in seq.items()}

# candidate intermediates for every pair (A, B) that some trip visits with stops in between
between = collections.defaultdict(set)
for t, s in seqs.items():
    pos = {p: i for i, p in enumerate(s)}
    for i, a in enumerate(s):
        for j in range(i + 2, min(len(s), i + 25)):
            between[(a, s[j])].update(s[i + 1:j])

# shapes
shp = collections.defaultdict(list)
for p in L("shapes"):
    shp[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]) * KX, float(p["shape_pt_lat"]) * KY))
shp = {k: [(x, y) for _, x, y in sorted(v)] for k, v in shp.items()}

def project(line, p):
    """(distance along line, distance from line)"""
    best = (0.0, 1e18); acc = 0.0
    for (x1, y1), (x2, y2) in zip(line, line[1:]):
        dx, dy = x2 - x1, y2 - y1; L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - x1) * dx + (p[1] - y1) * dy) / L2))
        qx, qy = x1 + t * dx, y1 + t * dy; d = math.hypot(p[0] - qx, p[1] - qy)
        if d < best[1]: best = (acc + t * math.sqrt(L2), d)
        acc += math.sqrt(L2)
    return best

hop_pass = {}
def passes(a, b, shape_id):
    key = (a, b, shape_id)
    if key in hop_pass: return hop_pass[key]
    cands = between.get((a, b), set()) - {a, b}
    out = []
    line = shp.get(shape_id)
    if cands and line and len(line) > 1:
        pa, da = project(line, xy[a]); pb, db = project(line, xy[b])
        if da < PASS_TOL and db < PASS_TOL:
            lo, hi = min(pa, pb), max(pa, pb)
            for x in cands:
                if x not in sid: continue
                px, dx_ = project(line, xy[x])
                if dx_ <= PASS_TOL and lo < px < hi:
                    out.append((abs(px - pa), sid[x]))
    hop_pass[key] = [s for _, s in sorted(out)]
    return hop_pass[key]

tids = meta["trip_ids"]
ptr = np.zeros(len(m["dep_s"]) + 1, dtype=np.int64); lst = []
for c, (a, b, tr) in enumerate(zip(m["dep_s"], m["arr_s"], m["trip"])):
    tid = tids[int(tr) % T]
    lst.extend(passes(st[int(a)], st[int(b)], trips[tid]["shape_id"]))
    ptr[c + 1] = len(lst)
np.savez(OUT + "_pass.npz", ptr=ptr, lst=np.array(lst, dtype=np.int64))
nz = int((np.diff(ptr) > 0).sum())
covered = set(lst)
only_pass = [meta["names"][s] for s in covered]
print(f"connections passing stations: {nz} of {len(ptr)-1}; distinct passed stations: {len(covered)}")
ex = [(k, [meta['names'][s] for s in v]) for k, v in hop_pass.items() if v][:0]
for (a, b, sh), v in list(hop_pass.items()):
    if v and a in ("A24", "120", "631") and len(v) > 2:
        print(f"  {stops[a]['stop_name']} -> {stops[b]['stop_name']} ({sh}): passes {[meta['names'][s] for s in v]}")
