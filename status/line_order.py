"""Write results/line_order.json: each line's weekday stop patterns (station IDs in order) and the
stations that are one complex under two IDs. status/alerts.py uses it to tell which stations lie
"between A and B" without downloading the timetable. Rebuild when the GTFS changes:

    python3 status/line_order.py $GTFS
"""
import collections, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "solver"))
from service import complexes, line_of

SRC = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "..", "results", "line_order.json")
L = lambda n: json.load(open(f"{SRC}/{n}.json"))
stops, transfers = L("stops"), L("transfers")
parent = {s["stop_id"]: (s["parent_station"] or s["stop_id"]) for s in stops}
trips = {t["trip_id"]: t["route_id"] for t in L("trips") if t["service_id"] == "Weekday" and t["route_id"] != "SI"}
seq = collections.defaultdict(list)
for r in L("stop_times"):
    if r["trip_id"] in trips: seq[r["trip_id"]].append((int(r["stop_sequence"]), parent[r["stop_id"]]))
pats = collections.defaultdict(set)
for t, v in seq.items():
    pats[line_of(trips[t])].add(tuple(p for _, p in sorted(v)))
# drop patterns contained in a longer one (short turns); keep one direction of each
out = {}
for ln, ps in pats.items():
    keep = []
    for p in sorted(ps, key=len, reverse=True):
        s = f" {' '.join(p)} "; r = f" {' '.join(reversed(p))} "
        if not any(s in f" {' '.join(k)} " or r in f" {' '.join(k)} " for k in keep): keep.append(p)
    out[ln] = [list(p) for p in keep]
same = {k: sorted(v) for k, v in complexes(stops, transfers).items()}
json.dump({"lines": out, "complexes": same}, open(OUT, "w"), separators=(",", ":"))
print(f"wrote {OUT}: {sum(len(v) for v in out.values())} patterns over {len(out)} lines, {len(same)} split-ID stations")
