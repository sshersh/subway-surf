"""Check an exported route against the raw GTFS feed, independently of the solver's model.

    python3 verify.py <gtfs_json_dir> <route.json> [--express] [--changes changes.json]

Checks: every train hop (stop -> next stop on a route at an arrival time) exists in the weekday
schedule; times never go backwards; every required station is reached by a train that stops there
(local rules) or that stops at or passes through it (express rules: the passed station must lie
between the hop's two stops on some other weekday trip, and not be in realistic.PASS_DENY); walks are between nearby stations.
With --changes, skipped and cut stops (service.py) are applied first: hops must exist in the
changed timetable, and stations no train stops at any more aren't required.
"""
import json, sys, math, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from realistic import PASS_DENY   # stations the express runs past on a separate level/bypass: never count
if "--no-deny" in sys.argv: PASS_DENY = {}   # sensitivity runs: geometric pass test only

SRC, ROUTE = sys.argv[1], sys.argv[2]
EXPRESS = "--express" in sys.argv
CHANGES = None
if "--changes" in sys.argv:
    from service import Changes
    CHANGES = Changes(sys.argv[sys.argv.index("--changes") + 1])
L = lambda n: json.load(open(f"{SRC}/{n}.json"))
stops = {s["stop_id"]: s for s in L("stops")}
parent = {k: (v["parent_station"] or k) for k, v in stops.items()}
wk = {t["trip_id"]: t["route_id"] for t in L("trips") if t["service_id"] == "Weekday" and t["route_id"] != "SI"}
dirn = {t["trip_id"]: t["direction_id"] for t in L("trips")}
ts = lambda x: sum(int(a) * k for a, k in zip(x.split(":"), (3600, 60, 1)))
seq = collections.defaultdict(list)
for r in L("stop_times"):
    if r["trip_id"] in wk: seq[r["trip_id"]].append(r)
if CHANGES:
    from service import complexes
    CHANGES.link(complexes(list(stops.values()), L("transfers")))
    CHANGES.learn((wk[t], [parent[r["stop_id"]] for r in sorted(v, key=lambda r: int(r["stop_sequence"]))]) for t, v in seq.items())
hops, between, served = set(), collections.defaultdict(set), set()
for v in seq.values(): v.sort(key=lambda r: int(r["stop_sequence"]))
sts = {tid: [(int(r["stop_sequence"]), parent[r["stop_id"]], ts(r["arrival_time"]), ts(r["departure_time"]), r["stop_id"]) for r in v] for tid, v in seq.items()}
for tid, v in seq.items():
    ps = [parent[r["stop_id"]] for r in v]; st = sts[tid]
    for day, off in ((0, 0), (1, 86400)):
        pieces = CHANGES.apply(st, wk[tid], dirn[tid], day)[0] if CHANGES else [st]
        for pc in pieces:
            for a, b in zip(pc, pc[1:]):
                hops.add((wk[tid], a[1], b[1], b[2] + off))
            if day == 0: served.update(x[1] for x in pc)   # required: stations a train stops at on the run day
    for i in range(len(ps)):
        for j in range(i + 2, min(len(ps), i + 25)): between[(ps[i], ps[j])].update(ps[i + 1:j])
rows = json.load(open(ROUTE))["rows"]
bad_hops, bad_pass, walks = [], [], []
stopped, passed = set(), set()
prev_stop = None
for a, b in zip(rows, rows[1:]):
    if ts(b["time"]) < ts(a["time"]): sys.exit(f"time goes backwards at {b}")
for i, b in enumerate(rows):
    if i == 0: prev_stop = b; continue
    if b.get("pass"):
        nxt = next(r for r in rows[i + 1:] if not r.get("pass"))
        if b["stop_id"] not in between.get((prev_stop["stop_id"], nxt["stop_id"]), set()) or b["stop_id"] in PASS_DENY: bad_pass.append(b)
        passed.add(b["stop_id"]); continue
    a = prev_stop
    if not b["route"]:
        sa, sb = stops[a["stop_id"]], stops[b["stop_id"]]
        walks.append(math.hypot((float(sa["stop_lat"]) - float(sb["stop_lat"])) * 111000, (float(sa["stop_lon"]) - float(sb["stop_lon"])) * 84000))
    elif a["stop_id"] != b["stop_id"]:
        if (b["route"], a["stop_id"], b["stop_id"], ts(b["time"])) not in hops: bad_hops.append((a, b))
        stopped.update([a["stop_id"], b["stop_id"]])
    prev_stop = b
got = stopped | (passed if EXPRESS else set())
print(f"rules: {'express' if EXPRESS else 'local'}")
print(f"train hops not in the weekday schedule: {len(bad_hops)}")
if EXPRESS: print(f"pass-throughs not between their hop's stops: {len(bad_pass)}")
print(f"stations required {len(served)}, covered {len(served & got)}, missing {sorted(served - got)[:10]}")
print(f"walks {len(walks)}, longest {max(walks):.0f} m" if walks else "walks 0")
ok = not bad_hops and not (EXPRESS and bad_pass) and served <= got
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
