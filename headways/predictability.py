"""How predictable is a route? Replay it on real days of actual train movements.

For each of the last N weekdays (with the following day's data too, since runs pass midnight), the
day's actual trains (subwaydata.nyc, from the MTA GTFS-realtime feeds) become a connection list.
Each route is then run with the strategy a rider would use: keep the route's station order (first
visits) and take whichever train actually gets you to the next station soonest. Every route is run
at its planned start time shifted by --offsets minutes, on every day, and the same is done on the
static timetable for comparison.

    python3 headways/predictability.py --routes label:rules:path ... --days 5 --out headways/results

Reports per route: mean, standard deviation, 10th/50th/90th/95th percentile, buffer index
((P95 - mean) / mean), day-to-day vs within-day spread, and runs that could not finish.
"""
import argparse, io, json, os, sys, tarfile, urllib.request, zipfile, collections, statistics, subprocess
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "solver")); sys.path.insert(0, HERE)
ET = ZoneInfo("America/New_York")
META = "https://data.subwaydata.nyc/subwaydatanyc_metadata.json"
GTFS = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"
UA = {"User-Agent": "subway-surf-predictability/1.0"}
INF = 1 << 40


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()


def build_static(gtfs_dir, model):
    if not os.path.exists(os.path.join(gtfs_dir, "stop_times.txt")):
        zipfile.ZipFile(io.BytesIO(get(GTFS))).extractall(gtfs_dir)
    if not os.path.exists(model + ".npz"):
        os.makedirs(os.path.dirname(model), exist_ok=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "solver", "model.py"), gtfs_dir, model], check=True)
        subprocess.run([sys.executable, os.path.join(ROOT, "solver", "passes.py"), gtfs_dir, model], check=True)


def day_files(meta, day):
    d = next((x for x in meta["ProcessedDays"] if x["Day"] == day), None)
    if not d: return None
    path = d.get("Csv", {}).get("Path") or f"subwaydatanyc_{day}_csv.tar.xz"
    for url in (f"https://data.subwaydata.nyc/{path}", f"https://subwaydata.nyc/data/{os.path.basename(path)}"):
        try:
            tf = tarfile.open(fileobj=io.BytesIO(get(url)), mode="r:xz")
            files = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
            tr = next(v for k, v in files.items() if k.endswith("trips.csv")); st = next(v for k, v in files.items() if k.endswith("stop_times.csv"))
            return tf.extractfile(tr).read().decode(), tf.extractfile(st).read().decode()
        except Exception as e:
            print("  failed", url, e)
    return None


class Network:
    """Connection arrays in the solver's format (sorted by departure)."""
    def __init__(self, conns, n, static):
        conns.sort()
        C = np.array(conns, dtype=np.int64) if conns else np.zeros((0, 6), np.int64)
        self.dep_t, self.arr_t, self.dep_s, self.arr_s, self.trip, hop = (C[:, i].copy() for i in range(6))
        self.nxt = np.full(len(C), -1, np.int64)
        order = np.lexsort((self.dep_t, self.trip))
        same = self.trip[order[:-1]] == self.trip[order[1:]]
        self.nxt[order[:-1][same]] = order[1:][same]
        self.ntrips = int(self.trip.max()) + 1 if len(C) else 1
        # pass-through lists per connection (express rules), from the static hop table
        lst, ptr = [], [0]
        for h in hop:
            lst.extend(static.hop_pass[h] if h >= 0 else []); ptr.append(len(lst))
        self.pp_ptr = np.array(ptr, np.int64); self.pp_lst = np.array(lst, np.int64)
        served = np.zeros(n, bool); served[self.dep_s] = True; served[self.arr_s] = True
        if len(self.pp_lst): served[self.pp_lst] = True
        self.served = served


class Static:
    def __init__(self, model):
        z = np.load(model + ".npz"); self.meta = json.load(open(model + ".json"))
        self.m = {k: z[k] for k in z.files}; self.n = len(self.meta["stations"])
        self.sid = {s: i for i, s in enumerate(self.meta["stations"])}; T = self.meta["T"]
        p = np.load(model + "_pass.npz")
        # hop key (route, s1, s2) -> stations passed (most common list), and an id per hop
        hp = collections.defaultdict(collections.Counter)
        for c in np.nonzero(np.diff(p["ptr"]))[0]:
            tr = int(self.m["trip"][c])
            hp[(self.meta["trip_route"][tr % T], int(self.m["dep_s"][c]), int(self.m["arr_s"][c]))][tuple(p["lst"][p["ptr"][c]:p["ptr"][c + 1]].tolist())] += 1
        self.hop_id = {}; self.hop_pass = []
        for k, v in hp.items(): self.hop_id[k] = len(self.hop_pass); self.hop_pass.append(list(v.most_common(1)[0][0]))
        # the static timetable as a Network (two service days, as in the solver)
        tr = self.m["trip"]; rt = self.meta["trip_route"]
        hops = [self.hop_id.get((rt[int(t) % T], int(a), int(b)), -1) for t, a, b in zip(tr, self.m["dep_s"], self.m["arr_s"])]
        conns = list(zip(self.m["dep_t"].tolist(), self.m["arr_t"].tolist(), self.m["dep_s"].tolist(), self.m["arr_s"].tolist(), tr.tolist(), hops))
        self.net = Network(conns, self.n, self)


def observed_network(static, day, tr_txt, st_txt, tr2, st2):
    """Actual trains of `day` and the next day, times in seconds after `day`'s local midnight."""
    import csv
    mid = datetime(day.year, day.month, day.day, tzinfo=ET).timestamp()
    conns = []; tix = 0
    for trips_txt, stops_txt in ((tr_txt, st_txt), (tr2, st2)):
        if not trips_txt: continue
        route = {}
        for t in csv.DictReader(io.StringIO(trips_txt)):
            if t["route_id"] and t["route_id"] != "SI": route[t["trip_uid"]] = t["route_id"]
        seq = collections.defaultdict(list)
        for r in csv.DictReader(io.StringIO(stops_txt)):
            rid = route.get(r["trip_uid"])
            if rid is None or not r["marked_past"]: continue
            a = r["arrival_time"] or r["departure_time"]; d = r["departure_time"] or r["arrival_time"]
            if not a: continue
            sid = r["stop_id"]; par = sid[:-1] if sid[-1:] in "NS" else sid
            s = static.sid.get(par)
            if s is not None: seq[r["trip_uid"]].append((int(a) - mid, int(d) - mid, s))
        for uid, v in seq.items():
            v.sort(); rid = route[uid]
            for (a1, d1, s1), (a2, d2, s2) in zip(v, v[1:]):
                if s1 != s2 and a2 >= d1 and a2 - d1 < 3 * 3600:
                    conns.append((int(d1), int(a2), s1, s2, tix, static.hop_id.get((rid, s1, s2), -1)))
            tix += 1
    return Network(conns, static.n, static)


def replay(static, net, order, t0, express):
    """Follow the station order, taking the earliest actual arrival to the next unvisited station.
    Returns (finish time - t0 seconds, stations that could not be reached)."""
    from engine import _leg
    from expr import _legx
    m = static.m; n = static.n
    ws = (np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
          np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
          np.zeros(net.ntrips, np.int64), np.zeros(net.ntrips, np.int64))
    ob = np.zeros(64, np.int64); oe = np.zeros(64, np.int64); ow = np.zeros(64, np.int64)
    visited = ~net.served.copy()           # stations with no observed service that day are not required
    cur, t, cur_trip, gen = int(order[0]), int(t0), -1, 0
    targets = [s for s in order[1:]] + [s for s in range(n)]
    for tgt in targets:
        if visited[tgt] or tgt == cur and visited[tgt]: continue
        if tgt == cur: continue
        gen += 1
        if express:
            a, k = _legx(cur, t, cur_trip, tgt, net.pp_ptr, net.pp_lst, net.dep_t, net.arr_t, net.dep_s, net.arr_s,
                         net.trip, m["chg"], m["fp_ptr"], m["fp_to"], m["fp_t"], *ws, gen, ob, oe, ow)
        else:
            a, k = _leg(cur, t, cur_trip, tgt, net.dep_t, net.arr_t, net.dep_s, net.arr_s,
                        net.trip, m["chg"], m["fp_ptr"], m["fp_to"], m["fp_t"], *ws, gen, ob, oe, ow)
        if a >= INF: continue                 # unreachable now (e.g. service ended); try the rest
        for q in range(k - 1, -1, -1):
            c = int(ob[q]); visited[net.dep_s[c]] = True
            while True:
                if express: visited[net.pp_lst[net.pp_ptr[c]:net.pp_ptr[c + 1]]] = True
                visited[net.arr_s[c]] = True
                if c == oe[q]: break
                c = int(net.nxt[c])
        cur_trip = int(net.trip[oe[0]]); cur = int(net.arr_s[oe[0]]); t = int(a)
    missing = int((~visited).sum())
    return t - t0, missing


def route_plan(static, path):
    r = json.load(open(path)); rows = r["rows"]; s = r["stats"]
    seen, order = set(), []
    for row in rows:
        i = static.sid.get(row["stop_id"])
        if i is not None and i not in seen: seen.add(i); order.append(i)
    t0 = sum(int(x) * k for x, k in zip(s["start"].split(":"), (3600, 60, 1)))
    return order, t0, s.get("rules", "local") == "express", s["total_s"]


def stats(vals):
    v = sorted(vals); n = len(v)
    pct = lambda p: v[min(n - 1, int(round(p / 100 * (n - 1))))]
    mean = statistics.mean(v)
    return {"n": n, "mean_h": round(mean / 3600, 3), "sd_min": round(statistics.pstdev(v) / 60, 1),
            "p10_h": round(pct(10) / 3600, 3), "p50_h": round(pct(50) / 3600, 3), "p90_h": round(pct(90) / 3600, 3),
            "p95_h": round(pct(95) / 3600, 3), "buffer_index": round((pct(95) - mean) / mean, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--routes", nargs="+", required=True, help="label:path (route JSON from solver/export.py)")
    ap.add_argument("--days", type=int, default=5); ap.add_argument("--offsets", type=int, nargs="+",
                    default=[-30, -20, -10, 0, 10, 20, 30])
    ap.add_argument("--out", default="headways/results"); ap.add_argument("--work", default="_work")
    a = ap.parse_args()
    gtfs = os.path.join(a.work, "gtfs"); model = os.path.join(a.work, "model", "model")
    build_static(gtfs, model); static = Static(model)
    routes = []
    for spec in a.routes:
        label, path = spec.split(":", 1); order, t0, express, planned = route_plan(static, path)
        routes.append({"label": label, "path": path, "order": order, "t0": t0, "express": express, "planned_s": planned})
    meta = json.loads(get(META)); have = {d["Day"] for d in meta["ProcessedDays"]}
    days = sorted(d for d in have if date.fromisoformat(d).weekday() < 5 and
                  (date.fromisoformat(d) + timedelta(days=1)).isoformat() in have)[-a.days:]
    print("weekdays:", days, flush=True)
    res = {r["label"]: {"static": [], "observed": collections.defaultdict(list), "missing": 0} for r in routes}
    for r in routes:     # static timetable, same offsets
        for o in a.offsets:
            tt, miss = replay(static, static.net, r["order"], r["t0"] + 60 * o, r["express"])
            res[r["label"]]["static"].append(tt)
    for d in days:
        f1 = day_files(meta, d); f2 = day_files(meta, (date.fromisoformat(d) + timedelta(days=1)).isoformat())
        if not f1: continue
        net = observed_network(static, date.fromisoformat(d), f1[0], f1[1], *(f2 or (None, None)))
        print(f"{d}: {len(net.dep_t):,} actual connections, {int(net.served.sum())} stations served", flush=True)
        for r in routes:
            for o in a.offsets:
                tt, miss = replay(static, net, r["order"], r["t0"] + 60 * o, r["express"])
                res[r["label"]]["observed"][d].append(tt); res[r["label"]]["missing"] += miss
            print(f"   {r['label']}: {[round(x/3600, 2) for x in res[r['label']]['observed'][d]]}", flush=True)
    out = {}
    for r in routes:
        R = res[r["label"]]; allv = [x for v in R["observed"].values() for x in v]
        day_means = [statistics.mean(v) for v in R["observed"].values()]
        within = [statistics.pstdev(v) for v in R["observed"].values()]
        out[r["label"]] = {"rules": "express" if r["express"] else "local", "planned_h": round(r["planned_s"] / 3600, 3),
                           "static_timetable": stats(R["static"]), "actual_days": stats(allv),
                           "between_day_sd_min": round(statistics.pstdev(day_means) / 60, 1),
                           "within_day_sd_min": round(statistics.mean(within) / 60, 1),
                           "per_day_mean_h": {d: round(statistics.mean(v) / 3600, 3) for d, v in R["observed"].items()},
                           "unreached_station_visits": R["missing"], "days": days, "offsets_min": a.offsets}
    os.makedirs(a.out, exist_ok=True)
    json.dump(out, open(os.path.join(a.out, "predictability.json"), "w"), indent=1)
    L = ["# Route predictability on real days", "",
         f"Each route keeps its station order and takes whichever train actually gets to the next station soonest. "
         f"Runs: weekdays {', '.join(days)} (each continuing into the next day) x start shifted by {a.offsets} min. "
         f"Actual trains from subwaydata.nyc (MTA GTFS-realtime).", "",
         "| Route | Rules | Planned | Static timetable (mean) | Actual: mean | SD | P10 | P50 | P90 | P95 | Buffer index | Day-to-day SD | Within-day SD |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    hm = lambda h: f"{int(h)}:{int(round((h % 1) * 60)):02d}"
    for k, v in out.items():
        s, o = v["static_timetable"], v["actual_days"]
        L.append(f"| {k} | {v['rules']} | {hm(v['planned_h'])} | {hm(s['mean_h'])} | **{hm(o['mean_h'])}** | {o['sd_min']} min | "
                 f"{hm(o['p10_h'])} | {hm(o['p50_h'])} | {hm(o['p90_h'])} | {hm(o['p95_h'])} | {o['buffer_index']:.1%} | "
                 f"{v['between_day_sd_min']} min | {v['within_day_sd_min']} min |")
    L += ["", "Per-day means (h): " + "; ".join(f"{k}: " + ", ".join(f"{d[5:]} {x:.2f}" for d, x in v["per_day_mean_h"].items()) for k, v in out.items())]
    open(os.path.join(a.out, "predictability.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
