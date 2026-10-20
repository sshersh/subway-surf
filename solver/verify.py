"""Check an exported route against the raw GTFS feed, independently of the solver's model.

    python3 verify.py <gtfs_json_dir> <route.json> [--express] [--changes changes.json]
        [--bus-gtfs <gtfs_json_root>] [--bus-links links.json]

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from stations472 import alias
parent = {k: alias(v["parent_station"] or k) for k, v in stops.items()}
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
prev_stop = None; bus_legs = []
for a, b in zip(rows, rows[1:]):
    if ts(b["time"]) < ts(a["time"]): sys.exit(f"time goes backwards at {b}")
for i, b in enumerate(rows):
    if i == 0: prev_stop = b; continue
    if b.get("pass"):
        nxt = next(r for r in rows[i + 1:] if not r.get("pass"))
        if b["stop_id"] not in between.get((prev_stop["stop_id"], nxt["stop_id"]), set()) or b["stop_id"] in PASS_DENY: bad_pass.append(b)
        passed.add(b["stop_id"]); continue
    a = prev_stop
    if b.get("bus"):   # a scheduled-bus leg: checked below against the bus feeds; it visits nothing
        bus_legs.append((a, b)); prev_stop = b; continue
    if not b["route"]:
        sa, sb = stops[a["stop_id"]], stops[b["stop_id"]]
        walks.append(math.hypot((float(sa["stop_lat"]) - float(sb["stop_lat"])) * 111000, (float(sa["stop_lon"]) - float(sb["stop_lon"])) * 84000))
    elif a["stop_id"] != b["stop_id"]:
        if (b["route"], a["stop_id"], b["stop_id"], ts(b["time"])) not in hops: bad_hops.append((a, b))
        stopped.update([a["stop_id"], b["stop_id"]])
    prev_stop = b
bad_bus = []
if bus_legs:
    import busdata as BD
    BROOT = sys.argv[sys.argv.index("--bus-gtfs") + 1] if "--bus-gtfs" in sys.argv else os.path.dirname(os.path.abspath(SRC.rstrip("/")))
    want = {b["bus_trip"] for _, b in bus_legs}; found = {}
    for fd in BD.FEEDS:
        d = f"{BROOT}/{fd}"
        if not os.path.isdir(d): continue
        tr_ = {t["trip_id"]: t for t in json.load(open(f"{d}/trips.json")) if t["trip_id"] in want}
        if not tr_: continue
        act = BD.active_services(d); ri = BD.routes_info(d)
        bst = {x["stop_id"]: (float(x["stop_lat"]), float(x["stop_lon"])) for x in json.load(open(f"{d}/stops.json"))}
        stt = collections.defaultdict(dict)
        for tid, sq, arr, dep, stop, pu, do in BD.read_stop_times(f"{d}/stop_times.json", set(tr_)): stt[tid][stop] = (sq, arr, dep, pu, do)
        for tid, t in tr_.items():
            found[tid] = (t["service_id"] in act, ri[t["route_id"]]["route_short_name"], stt[tid], bst)
    for a, b in bus_legs:
        why = []
        f = found.get(b["bus_trip"])
        if not f: bad_bus.append((b, "trip not in the bus feeds")); continue
        ok_day, short, sch, bst = f
        if not ok_day: why.append("service not active on the weekday")
        if short != b["bus"]: why.append(f"route {short} != {b['bus']}")
        sa, sb = sch.get(b["bus_from"]), sch.get(b["bus_to"])
        if not sa or not sb: why.append("stop not on trip")
        else:
            off = 86400 * int(b["bus_day"])
            if not sa[0] < sb[0]: why.append("stops out of order")
            if sa[3] == "1" or sb[4] == "1": why.append("no boarding/alighting allowed")
            if sa[2] + off != ts(b["bus_dep"]) or sb[1] + off != ts(b["bus_arr"]): why.append("times differ from the bus timetable")
            ll = lambda sid: (float(stops[sid]["stop_lat"]), float(stops[sid]["stop_lon"]))
            dA, dB = BD.dist_m(ll(b["from_stop"]), bst[b["bus_from"]]), BD.dist_m(ll(b["stop_id"]), bst[b["bus_to"]])
            if a["stop_id"] != b["from_stop"]: why.append("does not start where the rider is")
            if dA > BD.REACH + 1 or dB > BD.REACH + 1: why.append("stop too far from the station")
            if ts(a["time"]) + BD.walk_s(dA) > ts(b["bus_dep"]): why.append("cannot walk to the stop in time (no buffer)")
            if ts(b["bus_arr"]) + BD.walk_s(dB) > ts(b["time"]): why.append("row time before the walk from the stop ends")
        if why: bad_bus.append((b, "; ".join(why)))
    print(f"bus legs {len(bus_legs)} checked against the bus timetable, bad: {len(bad_bus)}" + (f" e.g. {bad_bus[:2]}" if bad_bus else ""))
got = stopped | (passed if EXPRESS else set())
print(f"rules: {'express' if EXPRESS else 'local'}")
print(f"train hops not in the weekday schedule: {len(bad_hops)}" + (f" e.g. {bad_hops[:3]}" if bad_hops else ""))
if EXPRESS: print(f"pass-throughs not between their hop's stops: {len(bad_pass)}")
print(f"stations required {len(served)}, covered {len(served & got)}, missing {sorted(served - got)[:10]}")
print(f"walks {len(walks)}, longest {max(walks):.0f} m" if walks else "walks 0")
ok = not bad_hops and not bad_bus and not (EXPRESS and bad_pass) and served <= got
print("PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
