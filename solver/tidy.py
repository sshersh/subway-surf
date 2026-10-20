"""Tidy-up pass on a finished route, at the level of its rides.

    python3 tidy.py <route.json> <out.json> [--express] [--window K] [--order-out out.npy]

Run from the model directory the route was solved on (cwd holds model.json/.npz, and
model_pass.npz for --express). The route JSON needs "rides" ([line, board, alight, dep, arr], as
export.py writes).

The annealer works on a priority order of stations that a timetable replay turns into rides, so a
small wasted detour in the rides (out and back for a station a later ride stops at anyway, a
pointless change of direction) usually can't be removed by moving one station in the order: the
replay of everything after it changes. This pass edits the rides directly and keeps the rest:

  - the route is a list of rides; replaying it takes, for each ride, the first train of that line
    from the boarding station that gets to the alighting station (staying on the same train when
    it can), walking between rides where the next one boards elsewhere;
  - a move replaces rides i..k (up to --window rides, default 4) with the fastest way from where
    ride i starts to where ride k ends (any trains and walks), or drops them if that's the same
    place; everything after is replayed with its own lines;
  - a move is kept if every station is still visited and the route finishes earlier.

Moves repeat until none helps. Writes the tidied route (same format as export.py, plus "rides")
and, with --order-out, a station order for seeding (the rides' alighting stations in order).
"""
import sys, json, bisect, collections
import numpy as np
from engine import _leg, INF

args = sys.argv[1:]
def opt(name, default, cast=str):
    if name in args:
        i = args.index(name); v = cast(args[i + 1]); del args[i:i + 2]; return v
    return default
EXPRESS = "--express" in args
if EXPRESS: args.remove("--express")
WINDOW = opt("--window", 4, int); ORDER_OUT = opt("--order-out", None)
SRC, OUT = args[0], args[1]

meta = json.load(open("model.json")); m = np.load("model.npz")
st = meta["stations"]; names = meta["names"]; T = meta["T"]; trip_route = meta["trip_route"]
sid = {s: i for i, s in enumerate(st)}; n = len(st)
dep_t, arr_t, dep_s, arr_s, trip, nxt, chg = (m[k] for k in ("dep_t", "arr_t", "dep_s", "arr_s", "trip", "nxt", "chg"))
fp_ptr, fp_to, fp_t = m["fp_ptr"], m["fp_to"], m["fp_t"]
if EXPRESS:
    P = np.load("model_pass.npz"); pptr, plst = P["ptr"], P["lst"]
base = lambda r: r[:-1] if len(r) == 2 and r.endswith("X") else r
line_of = lambda c: base(trip_route[int(trip[c]) % T])

bys = collections.defaultdict(list)
for c in np.argsort(dep_t, kind="stable"):
    bys[int(dep_s[c])].append(int(c))
byt = {s: [int(dep_t[c]) for c in v] for s, v in bys.items()}
foot = {}
for a in range(n):
    for k in range(fp_ptr[a], fp_ptr[a + 1]):
        foot[(a, int(fp_to[k]))] = int(fp_t[k])
nt = int(trip.max()) + 1
ws = [np.zeros(n, np.int64) for _ in range(7)] + [np.zeros(nt, np.int64), np.zeros(nt, np.int64)]
ob, oe, ow = (np.zeros(64, np.int64) for _ in range(3))
GEN = [0]


def cover(c, seen):
    seen.add(int(dep_s[c])); seen.add(int(arr_s[c]))
    if EXPRESS:
        seen.update(int(x) for x in plst[pptr[c]:pptr[c + 1]])


def ride(line, b, e, t, cur_trip, here):
    """first train of `line` from b reaching e. Returns (arrival, trip, conns) or None."""
    walked = here != b
    if walked:
        if (here, b) not in foot: return None
        t += foot[(here, b)]; cur_trip = -1
    ready = t + (chg[b] if cur_trip >= 0 else 0)
    lst = bys.get(b, []); i = bisect.bisect_left(byt.get(b, []), t)
    for c in lst[i:]:
        if dep_t[c] > t + 4 * 3600: break
        if line_of(c) != line: continue
        if dep_t[c] < ready and int(trip[c]) != cur_trip: continue
        chain = []; k = c
        while k >= 0 and len(chain) < 150:
            chain.append(k)
            if arr_s[k] == e: return int(arr_t[k]), int(trip[k]), chain
            k = int(nxt[k])
    return None


def path(here, t, cur_trip, e):
    """fastest way (any trains, walks) from here to arriving at e by train"""
    GEN[0] += 1
    a, k = _leg(here, t, cur_trip, e, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t, *ws, GEN[0], ob, oe, ow)
    if a >= INF: return None
    rides_ = []
    for q in range(k - 1, -1, -1):
        b, x = int(ob[q]), int(oe[q]); chain = [b]
        while chain[-1] != x: chain.append(int(nxt[chain[-1]]))
        rides_.append(chain)
    return int(a), int(trip[oe[0]]), rides_


def replay(legs, t0):
    """legs: [(line, b, e)] rides or ("*", None, e) fastest paths. Returns (finish, rides_out) or None."""
    here, t, ct = legs[0][1] if legs[0][1] is not None else 0, t0, -1
    seen = {here}; out = []
    for line, b, e in legs:
        if line == "*":
            r = path(here, t, ct, e)
            if r is None: return None
            t, ct, chains = r
            for ch in chains:
                for c in ch: cover(c, seen)
                out.append((line_of(ch[0]), int(dep_s[ch[0]]), int(arr_s[ch[-1]]), int(dep_t[ch[0]]), int(arr_t[ch[-1]]), ch))
        else:
            r = ride(line, b, e, t, ct, here)
            if r is None: return None
            t, ct, ch = r
            for c in ch: cover(c, seen)
            out.append((line, b, e, int(dep_t[ch[0]]), t, ch))
        here = e
    if len(seen) < n: return None
    return t, out


def key(r):
    """finish first; at the same finish, fewer boardings, then less walking (a free detour still costs risk)"""
    t, out = r; boards = 0; walk = 0; prev = None; pe = None
    for _, b, e, d, a, ch in out:
        if prev is None or int(trip[ch[0]]) != prev: boards += 1
        if pe is not None and b != pe: walk += foot.get((pe, b), 0)
        prev = int(trip[ch[-1]]); pe = e
    return (t, boards, walk)


route = json.load(open(SRC))
t0 = int(route["t0"]) if "t0" in route else int(route["rides"][0][3])
legs = [(base(r[0]), sid[r[1]], sid[r[2]]) for r in route["rides"]]
first = replay(legs, t0)
if first is None: raise SystemExit("the route's rides don't replay on this model")
best, out = first; bk = key(first); k0 = bk
print(f"start: {bk[1]} boardings, {bk[2]//60} min walking, finish {(best - t0)/3600:.3f} h", flush=True)
improved = True
while improved:
    improved = False
    for i in range(len(legs)):
        for k in range(i, min(len(legs), i + WINDOW)):
            start = legs[i][1]; end = legs[k][2]
            cand = legs[:i] + ([] if start == end else [("*", None, end)]) + legs[k + 1:]
            # expand the fastest path into concrete rides, so later moves see real lines
            r = replay(cand, t0)
            if r and key(r) < bk:
                nk = key(r)
                print(f"  rides {i}..{k} ({names[start]} -> {names[end]}): finish -{(bk[0] - nk[0])/60:.1f} min, "
                      f"boardings {bk[1]} -> {nk[1]}, walking {bk[2]//60} -> {nk[2]//60} min", flush=True)
                best, out = r; bk = nk
                legs = [(ln, b, e) for ln, b, e, *_ in out]
                improved = True; break
        if improved: break

# write the tidied route in export.py's format
hms = lambda s: f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"
s0 = out[0][3]   # the route starts with the first train (as export.py counts it), not the planner's t0
rows = [{"stop_id": st[out[0][1]], "time": hms(s0), "route": ""}]; seen = {out[0][1]}; itin = []; prev_e = out[0][1]; prev_a = s0; walk_s = 0
for _, b, e, d, a, ch in out:
    line = trip_route[int(trip[ch[0]]) % T]   # the trip's own route id (7X, 6X ...), as the schedule has it
    if b != prev_e:
        w = foot.get((prev_e, b), 0); walk_s += w
        itin.append({"kind": "walk", "from": names[prev_e], "to": names[b], "t0": hms(prev_a), "t1": hms(prev_a + w), "min": round(w / 60)})
        rows.append({"stop_id": st[b], "time": hms(prev_a + w), "route": ""})
    new0 = len(seen)
    for c in ch:
        if EXPRESS:
            for x in plst[pptr[c]:pptr[c + 1]]:
                rows.append({"stop_id": st[int(x)], "time": hms(int(dep_t[c])), "route": line, "pass": True}); seen.add(int(x))
        rows.append({"stop_id": st[int(arr_s[c])], "time": hms(int(arr_t[c])), "route": line}); seen.add(int(arr_s[c]))
    itin.append({"kind": "ride", "route": line, "from": names[b], "to": names[e], "t0": hms(d), "t1": hms(a), "stops": len(ch), "new": len(seen) - new0})
    prev_e = e; prev_a = a
stats = dict(route.get("stats", {}))
stats.update({"total_s": best - s0, "start": hms(s0), "end": hms(best), "rides": len(out), "walks": sum(1 for x in itin if x["kind"] == "walk"),
              "walk_s": walk_s, "start_station": names[out[0][1]], "end_station": names[out[-1][2]], "tidied": True})
order = list(dict.fromkeys([out[0][1]] + [e for _, _, e, *_ in out])); order += [i for i in range(n) if i not in set(order)]
json.dump({"rows": rows, "itin": itin, "stats": stats, "order": [st[i] for i in order], "t0": t0,
           "rides": [[trip_route[int(trip[ch[0]]) % T], st[b], st[e], d, a] for ln, b, e, d, a, ch in out]}, open(OUT, "w"))
if ORDER_OUT: np.save(ORDER_OUT, np.array([t0] + order, dtype=np.int64))
print(f"done: {(first[0] - first[1][0][3])/3600:.3f} -> {(best - out[0][3])/3600:.3f} h ({(first[0] - best)/60:.1f} min saved), "
      f"boardings {k0[1]} -> {bk[1]}, walking {k0[2]//60} -> {bk[2]//60} min", flush=True)
