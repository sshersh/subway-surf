"""Export a solved route to viewer rows + an itinerary, with independent checks."""
import sys, json
import numpy as np
from engine import Engine

E = Engine("model"); m = E.m; meta = E.meta
sol = np.load(sys.argv[1]).astype(np.int64)
EXPRESS = "--express" in sys.argv     # passing through a station counts (needs model_pass.npz)
END_AT = int(sys.argv[sys.argv.index("--end") + 1]) if "--end" in sys.argv else -1   # trial: fixed start + finish
ROBUST = "--robust" in sys.argv     # robust planner: hard minimum slack (robust.py); records each boarding's risk
RISK = []
PP = None
if ROBUST:
    from robust import FastR, record as rrecord
    F = FastR("model", express=EXPRESS, weight=float(sys.argv[sys.argv.index("--weight") + 1]) if "--weight" in sys.argv else 1.0,
              hard="--soft" not in sys.argv)
    t0, order = int(sol[0]), sol[1:]
    score = F.full(order, t0); plan_s, pen_s = F.parts()
    end, first, nv, rlegs, pen = rrecord(F, order, t0)
    assert end - first == plan_s and pen == pen_s, (end - first, plan_s, pen, pen_s)
    legs = [x[:3] for x in rlegs]; RISK = [x[3:] for x in rlegs]
    if EXPRESS: PP = F.pp
elif EXPRESS:
    from expr import FastX, recordx
    F = FastX(); t0, order = int(sol[0]), sol[1:]
    score = F.full(order, t0)
    end, first, nv, legs = recordx(F, order, t0)
    assert end - first == score, (end - first, score)
    PP = F.pp
elif sol.ndim == 2:   # line-aware solution [order, okey, t0]
    from fast2 import Fast, record, sanitize
    F = Fast(); order, okey, t0 = sol[0], sanitize(F, sol[0], sol[1]), int(sol[2][0])
    score = F.full(order, okey, t0)
    end, first, nv, legs = record(F, order, okey, t0)
    assert end - first == score, (end - first, score)
else:
    t0, order = int(sol[0]), sol[1:]
    end, first, nv, legs = E.record(order, t0)
if END_AT >= 0:   # add the closing ride to the finish station; the clock starts on the first platform
    from ends import Ends
    end_arr, extra = Ends(END_AT, EXPRESS).final_legs(order, t0)
    legs = list(legs) + extra
st = meta["stations"]; names = meta["names"]; troute = meta["trip_route"]; T = meta["T"]
from busrows import bus_leg
tids = meta.get("trip_ids") or []
BUS0 = meta.get("bus0", 1 << 40)
if BUS0 < (1 << 40) and (EXPRESS or sol.ndim == 2): raise SystemExit("bus links are supported for local rules (robust/engine replay) only")
route_of = lambda tr: troute[int(tr) % T] if int(tr) < BUS0 else meta["bus_route"][int(tr) - BUS0]
def tdir(tr):   # MTA trip IDs end in ..N or ..S (e.g. 000600_1..S03R): the direction the train runs
    if int(tr) >= BUS0: return None
    tid = tids[int(tr) % len(tids)] if tids else ""
    return "N" if "..N" in tid else "S" if "..S" in tid else None
dep_t, arr_t, dep_s, arr_s, trip, nxt = m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"], m["nxt"]
fp = {}
for s in range(E.n):
    for k in range(m["fp_ptr"][s], m["fp_ptr"][s + 1]):
        fp[(s, int(m["fp_to"][k]))] = int(m["fp_t"][k])

def hms(s): return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"
rows, itin = [], []
visited = {}
t = None; here = None
if END_AT >= 0:
    t, here = int(t0), int(order[0])
    rows.append({"stop_id": st[here], "time": hms(t), "route": ""})
walk_s = ride_s = bus_s = 0
for li, (b, e, w) in enumerate(legs):
    b, e, w = int(b), int(e), int(w)
    r = route_of(trip[b]); dr = tdir(trip[b])
    if w >= 0 and here is None:
        w = -1   # a walk before the first train just means starting at the next station
    if w >= 0:
        assert here == w, "walk must start where we are"
        wt = fp[(w, int(dep_s[b]))]; ta = t + wt
        rows.append({"stop_id": st[int(dep_s[b])], "time": hms(ta), "route": ""})
        itin.append({"kind": "walk", "from": names[w], "to": names[int(dep_s[b])], "t0": hms(t), "t1": hms(ta), "min": round(wt / 60)})
        walk_s += wt; t = ta; here = int(dep_s[b])
    assert here is None or here == int(dep_s[b]), "board where we are"
    assert t is None or dep_t[b] >= t, "board after arriving"
    if nxt[b] == -2:   # a bus leg: a way from A to B that visits nothing (busrows.py)
        assert b == e
        row, it = bus_leg(meta, hms, names, st, trip[b], dep_t[b], arr_t[b], int(dep_s[b]), int(arr_s[b]))
        if not rows: rows.append({"stop_id": st[int(dep_s[b])], "time": hms(int(dep_t[b])), "route": ""})
        rows.append(row); itin.append(it)
        if RISK and RISK[li][0] is not None: it.update({"slack_s": int(RISK[li][0])})
        bus_s += int(arr_t[b] - dep_t[b]); t = int(arr_t[b]); here = int(arr_s[b])
        continue
    if not rows or rows[-1]["stop_id"] != st[int(dep_s[b])] or rows[-1]["route"] != r or t != dep_t[b]:
        rows.append({"stop_id": st[int(dep_s[b])], "time": hms(int(dep_t[b])), "route": r if rows else "", **({"dir": dr} if rows and dr else {})})
    visited.setdefault(int(dep_s[b]), int(dep_t[b]))
    c = b; nstops = 0; new = 0
    while True:
        if PP is not None:   # stations this hop passes without stopping
            plist = PP[1][PP[0][c]:PP[0][c + 1]]
            for i, p in enumerate(plist):
                tp = int(dep_t[c] + (arr_t[c] - dep_t[c]) * (i + 1) / (len(plist) + 1))
                if int(p) not in visited: new += 1
                visited.setdefault(int(p), tp)
                rows.append({"stop_id": st[int(p)], "time": hms(tp), "route": r, "pass": True, **({"dir": dr} if dr else {})})
        s2 = int(arr_s[c]); nstops += 1
        if s2 not in visited: new += 1
        visited.setdefault(s2, int(arr_t[c]))
        rows.append({"stop_id": st[s2], "time": hms(int(arr_t[c])), "route": r, **({"dir": dr} if dr else {})})
        if c == e: break
        n2 = int(nxt[c]); assert trip[n2] == trip[c]; c = n2
    ride_s += int(arr_t[e] - dep_t[b])
    if itin and itin[-1]["kind"] == "ride" and itin[-1]["trip"] == int(trip[b]):
        L = itin[-1]; L["to"] = names[int(arr_s[e])]; L["t1"] = hms(int(arr_t[e])); L["stops"] += nstops; L["new"] += new
    else:
        itin.append({"kind": "ride", "route": r, "trip": int(trip[b]), "from": names[int(dep_s[b])], "to": names[int(arr_s[e])],
                     "t0": hms(int(dep_t[b])), "t1": hms(int(arr_t[e])), "stops": nstops, "new": new})
        if RISK and RISK[li][0] is not None:   # slack before this boarding, cost of missing it, P(miss)
            itin[-1].update({"slack_s": int(RISK[li][0]), "miss_s": int(RISK[li][1]), "p_miss": round(RISK[li][2], 3)})
    t = int(arr_t[e]); here = int(arr_s[e])
rows[0]["route"] = ""
times = [sum(int(x) * k for x, k in zip(r["time"].split(":"), (3600, 60, 1))) for r in rows]
assert all(a <= b for a, b in zip(times, times[1:])), "times monotonic"
assert len(visited) == E.n, f"visited {len(visited)} of {E.n}"
last_new = max(visited.values())
if END_AT >= 0:
    last_new = max(last_new, int(end_arr)); first = int(t0)
total = last_new - first
# trim rows after the last new station
k = max(i for i, x in enumerate(times) if x <= last_new)
rows = rows[:k + 1]
nride = sum(1 for L in itin if L["kind"] == "ride")
stats = {"total_s": int(total), "start": hms(int(first)), "end": hms(int(last_new)), "stations": len(visited), "rules": "express" if EXPRESS else "local",
         "passed_only": len(set(r["stop_id"] for r in rows if r.get("pass")) - set(r["stop_id"] for r in rows if not r.get("pass"))),
         "ride_s": ride_s, "walk_s": walk_s, "wait_s": int(total) - ride_s - walk_s - bus_s, "bus_s": bus_s, "buses": sum(1 for L in itin if L["kind"] == "bus"), "fixed_ends": END_AT >= 0, "rides": nride,
         "walks": sum(1 for L in itin if L["kind"] == "walk"), "start_station": names[int(order[0])],
         "end_station": names[END_AT] if END_AT >= 0 else names[max(visited, key=visited.get)]}
if ROBUST:
    stats["expected_miss_s"] = int(pen_s); stats["robust"] = True
    mp = json.load(open("model.json")).get("params", {})
    stats["model"] = {k: mp.get(k) for k in ("LEGACY", "RUN_SPEED", "RUN_FROM", "WALK_MAX")}
# full plan for replays/re-planning: station order (stop ids), start time, and the planned rides
# (route, board stop, alight stop, planned dep, planned arr) as headways/predictability.py expects
order_ids = [st[int(i)] for i in order]
rides_plan = [[route_of(trip[b]), st[int(dep_s[b])], st[int(arr_s[e])], int(dep_t[b]), int(arr_t[e])] for b, e, w in legs]
for L in itin: L.pop("trip", None)
json.dump({"rows": rows, "itin": itin, "stats": stats, "order": order_ids, "t0": int(t0), "rides": rides_plan}, open(sys.argv[2], "w"))
print(json.dumps(stats, indent=1))
