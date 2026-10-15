"""Re-plan the route around current service changes (skipped stops, suspensions, closures).

    python3 solver/replan.py --gtfs $GTFS --changes changes.json --out site/ [--minutes 8] [--procs 2]
                             [--rules local express] [--prev cache/]

1. Builds two timetables: the normal one, and one with the changes from status/alerts.py applied
   (model.py --changes). Stations no train stops at are dropped from the challenge.
2. Seeds from the saved best route (results/), and from --prev (the last re-planned route) when given.
   Each seed's station order is replayed against the changed timetable.
3. If the best seed is no slower than the normal plan, the changes don't touch the route and it's used
   as is. Otherwise it adds a fresh line-aware seed (gseed.py on the changed timetable, ~2 min) and
   anneals for --minutes: --procs runs in parallel per rules, the best seed warm and the fresh one hot.
4. Exports, checks with verify.py against the changed timetable, and writes to --out:
     current_route.json, current_route_express.json    viewer routes (same format as results/)
     current_solution*.json                            station order by stop ID, to seed the next run
     replan.json                                       summary for the status banner
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
        p = os.path.join(prev_dir, f"current_solution{'' if rules == 'local' else '_' + rules}.json")
        if os.path.exists(p):
            j = json.load(open(p)); out.append(("last re-plan", j["order"], j["t0"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gtfs", required=True); ap.add_argument("--changes", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--work", default=None)
    ap.add_argument("--prev", default=None); ap.add_argument("--minutes", type=float, default=8)
    ap.add_argument("--procs", type=int, default=2); ap.add_argument("--rules", nargs="+", default=["local", "express"])
    a = ap.parse_args()
    gtfs, changes = os.path.abspath(a.gtfs), os.path.abspath(a.changes)
    work = os.path.abspath(a.work or os.path.join(a.out, "_work")); out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    ch = json.load(open(changes))
    express = "express" in a.rules
    t_start = time.time()
    base_meta = build(f"{work}/base", gtfs, None, express)
    cur_meta = build(f"{work}/cur", gtfs, changes, express) if ch["changes"] else base_meta
    cur_dir = f"{work}/cur" if ch["changes"] else f"{work}/base"
    names = dict(zip(base_meta["stations"], base_meta["names"]))
    summary = {"run_date": ch["run_date"], "hash": ch["hash"], "solved_at": None, "feed_timestamp": ch["feed_timestamp"],
               "changes": [dict(c, station_names=[names.get(s) or names.get(s[:-1], s) for s in c["stops"]]) for c in ch["changes"]],
               "not_modeled": ch["not_modeled"], "dropped": [{"id": s, "name": names.get(s, s)} for s in cur_meta.get("dropped", [])],
               "rules": {}}

    jobs, plans = {}, {}
    for rules in a.rules:
        X = rules == "express"
        base, cur = Scorer(f"{work}/base", X), Scorer(cur_dir, X)
        cands = seeds(rules, base_meta, a.prev)
        normal = min((c for c in (base.cost(base.order(o), t) for _, o, t in cands[:2]) if c is not None), default=None)
        scored = []
        for label, o, t in cands:
            order = cur.order(o)
            c, t0 = cur.best_start(order, t)
            if c is not None: scored.append((c, label, order, t0))
            print(f"{rules}: seed {label}: {'unreachable' if c is None else f'{c/3600:.3f} h'}", flush=True)
        plans[rules] = (normal, scored, cur)

    # The changes slow the route down: also seed from scratch (line-aware LKH tour on the changed
    # timetable), since the old route's shape may no longer suit the network.
    if any(n is None or not sc or min(sc)[0] > n for n, sc, _ in plans.values()):
        t = time.time()
        run([f"{HERE}/gseed.py", gtfs, "run", "1", "0.5"], cur_dir)
        g = np.load(f"{cur_dir}/run_gseed.npy")[0].astype(np.int64)
        print(f"fresh line-aware seed: {time.time() - t:.0f} s", flush=True)
        for rules, (normal, scored, cur) in plans.items():
            c, t0 = cur.best_start(g, 6 * 3600)
            if c is not None: scored.append((c, "fresh line-aware seed", g, t0))
            print(f"{rules}: seed fresh line-aware seed: {'unreachable' if c is None else f'{c/3600:.3f} h'}", flush=True)

    for rules, (normal, scored, cur) in plans.items():
        X = rules == "express"
        if not scored: raise SystemExit(f"{rules}: no seed can visit every station under these changes")
        scored.sort(key=lambda x: x[0])
        c, label, order, t0 = scored[0]
        seed = f"{work}/seed_{rules}.npy"; np.save(seed, np.concatenate([[t0], order]))
        info = {"normal_s": normal, "seed": label, "seed_s": c, "annealed": False}
        summary["rules"][rules] = info
        if normal is not None and c <= normal:
            jobs[rules] = (seed, [], info, X); continue
        # parallel anneals: the best seed warm (cool start), then the fresh seed hot, then the rest
        starts = [(scored[0], "60")] + [(x, "150") for x in scored[1:] if x[1] == "fresh line-aware seed"] + [(x, "100") for x in scored[1:] if x[1] != "fresh line-aware seed"]
        procs = []
        for k in range(a.procs):
            (_, lab, o_, t_), hot = starts[k % len(starts)]
            sf = f"{work}/seed_{rules}_{k}.npy"; np.save(sf, np.concatenate([[t_], o_]))
            o = f"{work}/sa_{rules}_{k}.npy"
            procs.append((o, subprocess.Popen([sys.executable, f"{HERE}/{RULES[rules]['sa']}", sf, str(k + 1), str(a.minutes), o, hot, "2"],
                                              cwd=cur_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)))
        info["annealed"] = True
        jobs[rules] = (seed, procs, info, X)

    for rules, (seed, procs, info, X) in jobs.items():
        cur = Scorer(cur_dir, X)
        best = (info["seed_s"], seed)
        for o, p in procs:
            err = p.communicate()[1]
            if p.returncode or not os.path.exists(o):
                print(f"{rules}: anneal run failed\n{err[-2000:]}", file=sys.stderr); continue
            s = np.load(o).astype(np.int64); c = cur.cost(s[1:], s[0])
            if c is not None and c < best[0]: best = (c, o)
        sfx = "" if rules == "local" else "_" + rules
        route = f"{out}/current_route{sfx}.json"
        run([f"{HERE}/export.py", best[1], route] + RULES[rules]["flag"], cur_dir)
        v = run([f"{HERE}/verify.py", gtfs, route] + RULES[rules]["flag"] + (["--changes", changes] if ch["changes"] else []), cur_dir)
        verdict = v.strip().splitlines()[-1]
        r = json.load(open(route)); s = np.load(best[1]).astype(np.int64)
        r["conditions"] = {"hash": ch["hash"], "run_date": ch["run_date"], "normal_s": info["normal_s"]}
        json.dump(r, open(route, "w"), separators=(",", ":"))
        json.dump({"t0": int(s[0]), "order": [cur.st[i] for i in s[1:]], "hash": ch["hash"]}, open(f"{out}/current_solution{sfx}.json", "w"))
        info.update({"total_s": r["stats"]["total_s"], "route": os.path.basename(route), "verify": verdict,
                     "start": r["stats"]["start"], "start_station": r["stats"]["start_station"], "end_station": r["stats"]["end_station"]})
        d = "" if info["normal_s"] is None else f" ({(info['total_s'] - info['normal_s']) / 60:+.0f} min vs normal)"
        print(f"{rules}: {info['total_s']/3600:.3f} h{d}, {'annealed' if info['annealed'] else 'seed kept'}, verify {verdict}", flush=True)
    summary["solved_at"] = int(time.time()); summary["seconds"] = round(time.time() - t_start)
    json.dump(summary, open(f"{out}/replan.json", "w"), indent=1)
    if not a.work: shutil.rmtree(work, ignore_errors=True)
    if any(i.get("verify") != "PASS" for i in summary["rules"].values()): raise SystemExit("a re-planned route failed verify.py")


if __name__ == "__main__":
    main()
