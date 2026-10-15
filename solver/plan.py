"""Plan the route for the current service: the timetable with today's MTA service changes applied.

    python3 solver/plan.py --gtfs $GTFS --changes changes.json --out plan/ [--minutes 10] [--procs 2]
                           [--rules local express] [--prev plan_cache/]

1. Builds the weekday timetable with the changes from status/alerts.py applied (model.py --changes):
   skipped stops are dropped from trips, suspended stretches split trips. Stations no train stops at
   on the run day are left out of the challenge.
2. Seeds: a fresh line-aware tour on that timetable (gseed.py), the saved best routes (results/), and
   the last plan for these changes (--prev) when there is one. An old order that reaches a station
   after its service ends is repaired by moving that station earlier.
3. Anneals for --minutes, --procs runs in parallel per rules (the fresh seed hot, the best other seed
   warm), then exports and checks the best with verify.py against the same timetable. Writes to --out:
     route.json, route_express.json      viewer routes (same format as results/)
     solution*.json                      station order by stop ID, to seed the next run
     plan.json                           run day, the changes planned around, left-out stations, totals
"""
import argparse, json, os, shutil, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
RULES = {
    "local":   {"route": "best_route.json", "sol": "best_solution.npy", "sa": "sa2.py", "flag": []},
    "express": {"route": "best_route_express.json", "sol": "best_solution_express.npy", "sa": "sax.py", "flag": ["--express"]},
}
secs = lambda s: sum(int(x) * k for x, k in zip(s.split(":"), (3600, 60, 1)))


def run(cmd, cwd):
    r = subprocess.run([sys.executable] + cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
        raise SystemExit(f"failed: {' '.join(cmd)}")
    return r.stdout


def build(d, gtfs, changes, express):
    os.makedirs(d, exist_ok=True)
    run([f"{HERE}/model.py", gtfs, "model"] + (["--changes", changes] if changes else []), d)
    if express:
        run([f"{HERE}/passes.py", gtfs, "model"], d)
    return json.load(open(f"{d}/model.json"))


class Scorer:
    def __init__(self, d, express):
        from engine import INF
        self.INF = INF
        if express:
            from expr import FastX
            self.F = FastX(f"{d}/model")
        else:
            from fast import Fast
            self.F = Fast(f"{d}/model")
        self.st = json.load(open(f"{d}/model.json"))["stations"]
        self.ix = {s: i for i, s in enumerate(self.st)}

    def order(self, stop_ids):
        """Station order for this timetable: keep known stations, add any new ones at the end."""
        seen, out = set(), []
        for s in stop_ids:
            if s in self.ix and s not in seen: seen.add(s); out.append(self.ix[s])
        out += [i for i, s in enumerate(self.st) if s not in seen]
        return np.array(out, dtype=np.int64)

    def cost(self, order, t0):
        c = self.F.full(order, int(t0))
        return None if c >= self.INF else int(c)

    def best_start(self, order, t0):
        """Keep the seed's start time unless another start on a 10-minute grid is faster."""
        cands = [int(t0)] + list(range(0, 20 * 3600 + 1, 600))
        scored = [(c, t) for t in cands for c in [self.cost(order, t)] if c is not None]
        return min(scored) if scored else (None, int(t0))


_REPAIRED = {}
def repair(d, order, t0, tries=300):
    key = (d, tuple(int(x) for x in order), int(t0))
    if key not in _REPAIRED: _REPAIRED[key] = _repair(d, order, t0, tries)
    return _REPAIRED[key]


REPAIR_SECONDS = 45   # each try replays the whole order (~5 s); the fresh seed covers what this misses


def _repair(d, order, t0, tries):
    """Make a station order feasible on a changed timetable. When the replay can't reach a station
    any more (its service ends, e.g. a line suspended from Saturday 03:30), move that station earlier,
    to just after the last point where the run is still 2 hours ahead of its last train, and retry.
    Uses local rules (stopping counts), which also makes it feasible under express rules."""
    from engine import _leg, INF
    m = np.load(f"{d}/model.npz"); n = len(m["chg"]); nt = int(m["trip"].max()) + 1
    last = np.zeros(n, np.int64)
    np.maximum.at(last, m["dep_s"], m["dep_t"]); np.maximum.at(last, m["arr_s"], m["arr_t"])
    ws = [np.zeros(n, np.int64) for _ in range(7)] + [np.zeros(nt, np.int64), np.zeros(nt, np.int64)]
    ob, oe, ow = (np.zeros(64, np.int64) for _ in range(3))
    order = [int(x) for x in order]; gen = 0; deadline = time.time() + REPAIR_SECONDS
    for _ in range(tries):
        if time.time() > deadline: break
        vis = np.zeros(n, bool); cur, t, ct = order[0], int(t0), -1; at = [t]; bad = None
        for p in range(1, len(order)):
            tgt = order[p]
            if vis[tgt] or tgt == cur: at.append(t); continue
            gen += 1
            a, k = _leg(cur, t, ct, tgt, m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"], m["chg"],
                        m["fp_ptr"], m["fp_to"], m["fp_t"], *ws, gen, ob, oe, ow)
            if a >= INF: bad = p; break
            for q in range(k - 1, -1, -1):
                c = int(ob[q]); vis[m["dep_s"][c]] = True
                while True:
                    vis[m["arr_s"][c]] = True
                    if c == oe[q]: break
                    c = int(m["nxt"][c])
            ct = int(m["trip"][oe[0]]); cur = tgt; t = int(a); at.append(t)
        if bad is None: return np.array(order, dtype=np.int64), True
        x = order.pop(bad)
        q = max([i for i in range(bad) if at[i] < last[x] - 7200], default=0)
        order.insert(q + 1, x)
    return np.array(order, dtype=np.int64), False


def seeds(rules, base_meta, prev_dir):
    """Candidate (label, stop-id order, t0) seeds for these rules."""
    cfg, out = RULES[rules], []
    sol = os.path.join(ROOT, "results", cfg["sol"])
    if os.path.exists(sol):
        a = np.load(sol).astype(np.int64)
        if a.ndim == 1 and len(a) == len(base_meta["stations"]) + 1:   # same station list as this feed
            out.append(("saved best", [base_meta["stations"][i] for i in a[1:]], int(a[0])))
    rows = json.load(open(os.path.join(ROOT, "results", cfg["route"])))["rows"]
    first = list(dict.fromkeys(r["stop_id"] for r in rows))
    out.append(("saved best (visit order)", first, secs(rows[0]["time"])))
    if prev_dir:
        p = os.path.join(prev_dir, f"solution{'' if rules == 'local' else '_' + rules}.json")
        if os.path.exists(p):
            j = json.load(open(p)); out.append(("last plan", j["order"], j["t0"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gtfs", required=True); ap.add_argument("--changes", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--work", default=None)
    ap.add_argument("--prev", default=None); ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--procs", type=int, default=2); ap.add_argument("--rules", nargs="+", default=["local", "express"])
    a = ap.parse_args()
    gtfs, changes = os.path.abspath(a.gtfs), os.path.abspath(a.changes)
    work = os.path.abspath(a.work or os.path.join(a.out, "_work")); out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    ch = json.load(open(changes))
    t_start = time.time()
    d = f"{work}/model"
    meta = build(d, gtfs, changes if ch["changes"] else None, "express" in a.rules)
    names = dict(zip(meta["stations"], meta["names"]))
    base_names = {s["stop_id"]: s["stop_name"] for s in json.load(open(f"{gtfs}/stops.json"))}
    nm = lambda s: names.get(s) or base_names.get(s) or base_names.get(s[:-1], s)
    summary = {"run_date": ch["run_date"], "hash": ch["hash"], "solved_at": None, "feed_timestamp": ch["feed_timestamp"],
               "changes": [dict(c, station_names=[nm(s) for s in c["stops"]]) for c in ch["changes"]],
               "not_modeled": ch["not_modeled"], "dropped": [{"id": s, "name": nm(s)} for s in meta.get("dropped", [])],
               "stations": len(meta["stations"]), "rules": {}}

    # a fresh line-aware tour on this timetable, so the plan isn't tied to the normal route's shape
    t = time.time()
    run([f"{HERE}/gseed.py", gtfs, "run", "1", "0.5"], d)
    fresh = np.load(f"{d}/run_gseed.npy")[0].astype(np.int64)
    print(f"fresh line-aware seed: {time.time() - t:.0f} s", flush=True)

    jobs = {}
    for rules in a.rules:
        X = rules == "express"
        cur = Scorer(d, X)
        scored = []
        for label, o, t0 in [("fresh line-aware seed", None, 6 * 3600)] + seeds(rules, meta, a.prev):
            order = fresh if o is None else cur.order(o)
            c, t1 = cur.best_start(order, t0)
            if c is None:   # a station loses service before this order gets there: move it earlier
                order, ok = repair(d, order, t0)
                if ok: c, t1 = cur.best_start(order, t0); label += ", repaired"
            print(f"{rules}: seed {label}: {'unreachable' if c is None else f'{c/3600:.3f} h'}", flush=True)
            if c is not None: scored.append((c, label, order, t1))
        if not scored: raise SystemExit(f"{rules}: no seed can visit every station under these changes")
        scored.sort(key=lambda x: x[0])
        info = {"seed": scored[0][1], "seed_s": scored[0][0]}
        summary["rules"][rules] = info
        # parallel anneals: the best seed warm, the fresh seed hot, then the rest
        fr = [x for x in scored if x[1].startswith("fresh")]
        starts = [(scored[0], "60")] + [(x, "150") for x in fr if x is not scored[0]] + [(x, "100") for x in scored[1:] if x not in fr]
        procs = []
        for k in range(a.procs):
            (_, lab, o_, t_), hot = starts[k % len(starts)]
            sf = f"{work}/seed_{rules}_{k}.npy"; np.save(sf, np.concatenate([[t_], o_]))
            o = f"{work}/sa_{rules}_{k}.npy"
            procs.append((o, subprocess.Popen([sys.executable, f"{HERE}/{RULES[rules]['sa']}", sf, str(k + 1), str(a.minutes), o, hot, "2"],
                                              cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)))
        seed = f"{work}/seed_{rules}.npy"; np.save(seed, np.concatenate([[scored[0][3]], scored[0][2]]))
        jobs[rules] = (seed, procs, info, X)

    for rules, (seed, procs, info, X) in jobs.items():
        cur = Scorer(d, X)
        best = (info["seed_s"], seed)
        for o, p in procs:
            err = p.communicate()[1]
            if p.returncode or not os.path.exists(o):
                print(f"{rules}: anneal run failed\n{err[-2000:]}", file=sys.stderr); continue
            s = np.load(o).astype(np.int64); c = cur.cost(s[1:], s[0])
            if c is not None and c < best[0]: best = (c, o)
        sfx = "" if rules == "local" else "_" + rules
        route = f"{out}/route{sfx}.json"
        run([f"{HERE}/export.py", best[1], route] + RULES[rules]["flag"], d)
        v = run([f"{HERE}/verify.py", gtfs, route] + RULES[rules]["flag"] + (["--changes", changes] if ch["changes"] else []), d)
        verdict = v.strip().splitlines()[-1]
        r = json.load(open(route)); s = np.load(best[1]).astype(np.int64)
        r["conditions"] = {"hash": ch["hash"], "run_date": ch["run_date"], "changes": len(ch["changes"])}
        json.dump(r, open(route, "w"), separators=(",", ":"))
        json.dump({"t0": int(s[0]), "order": [cur.st[i] for i in s[1:]], "hash": ch["hash"]}, open(f"{out}/solution{sfx}.json", "w"))
        info.update({"total_s": r["stats"]["total_s"], "route": os.path.basename(route), "verify": verdict,
                     "start": r["stats"]["start"], "start_station": r["stats"]["start_station"], "end_station": r["stats"]["end_station"]})
        print(f"{rules}: {info['total_s']/3600:.3f} h (seed {info['seed_s']/3600:.3f} h, {info['seed']}), verify {verdict}", flush=True)
    summary["solved_at"] = int(time.time()); summary["seconds"] = round(time.time() - t_start)
    json.dump(summary, open(f"{out}/plan.json", "w"), indent=1)
    if not a.work: shutil.rmtree(work, ignore_errors=True)
    if any(i.get("verify") != "PASS" for i in summary["rules"].values()): raise SystemExit("a planned route failed verify.py")


if __name__ == "__main__":
    main()
