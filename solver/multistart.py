"""Multi-start search: many short anneals from diverse starting routes, run in parallel.

Run from a model directory (the cwd holds model.json/.npz and, for express, model_pass.npz):

    python3 ../solver/multistart.py --rules express|local --job J --hours H --minutes M --out DIR
        [--procs P] [--seeds a.npy b.json ...] [--elites a.npy ...] [--kick LO HI] [--thi T] [--tlo T]

Each start takes one base order and perturbs it, picks a start-time window, and runs sar.py for M
minutes (convergence logs showed most gains land in the first 20-30 min and a converged run never
improves when continued, so many short independent runs beat one long one).

Base orders:
  --seeds   line-aware tours (gseed/tseed output) and saved routes (.npy solutions or route .json)
  --elites  stage-2 refinement: the best results of stage 1; every start kicks one of them
Perturbation: K random segment moves (K drawn from --kick LO HI), so starts from the same base
differ. Start windows are drawn from WINDOWS. Rules: express = robust objective (hard slack,
weight 1); local = Guinness rules, plan time only (--local --soft --weight 0).

Writes DIR/job<J>_<k>.npy (t0 + order) for every start and DIR/job<J>.json (one row per start:
seed, kick, window, start/final objective, seconds), so the collector can rank everything.
"""
import sys, os, json, time, subprocess, random, re
import numpy as np
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = [(0, 3), (1, 4), (2, 5), (3, 6), (4, 7), (5, 8), (0, 8), (6, 10)]


def opt(name, default, cast=str, n=1):
    if name in sys.argv:
        i = sys.argv.index(name)
        if n == "*":
            j = i + 1
            while j < len(sys.argv) and not sys.argv[j].startswith("--"): j += 1
            v = sys.argv[i + 1:j]; del sys.argv[i:j]; return v
        v = [cast(x) for x in sys.argv[i + 1:i + 1 + n]]; del sys.argv[i:i + 1 + n]
        return v[0] if n == 1 else v
    return default


rules = opt("--rules", "express"); job = opt("--job", 0, int); hours = opt("--hours", 1.0, float)
minutes = opt("--minutes", 25.0, float); out = opt("--out", "ms"); procs = opt("--procs", os.cpu_count() or 2, int)
seeds = opt("--seeds", [], n="*"); elites = opt("--elites", [], n="*")
kick = opt("--kick", [0, 25], int, n=2); thi = opt("--thi", 300.0, float); tlo = opt("--tlo", 3.0, float)
win_opt = opt("--windows", None)          # e.g. "0-2.5,1-3": start-time windows (h) to draw from instead of WINDOWS
then_ride = opt("--then-ride", 0.0, float)  # minutes of ride-level search (ridesearch.py) after each anneal, local rules
if win_opt: WINDOWS = [tuple(float(x) for x in w.split("-")) for w in win_opt.split(",")]
os.makedirs(out, exist_ok=True)

meta = json.load(open("model.json")); sid = {s: i for i, s in enumerate(meta["stations"])}; n = len(sid)


def load_order(path):
    if path.endswith(".json"):
        r = json.load(open(path))
        o = [sid[s] for s in r["order"] if s in sid]
    else:
        a = np.load(path)
        o = list(a[0]) if a.ndim == 2 else (list(a[1:]) if len(a) == n + 1 else list(a))
    seen = set(); o = [int(x) for x in o if not (x in seen or seen.add(x))]
    o += [i for i in range(n) if i not in seen]          # stations this model has that the route lacks
    return o


bases = [(p, load_order(p)) for p in (elites or seeds)]
if not bases: raise SystemExit("no --seeds/--elites")


def perturb(o, k, rng):
    o = list(o)
    for _ in range(k):
        L = rng.randint(1, 30); i = rng.randint(0, len(o) - L); seg = o[i:i + L]
        if rng.random() < 0.3: seg = seg[::-1]
        rest = o[:i] + o[i + L:]; j = rng.randint(0, len(rest)); o = rest[:j] + seg + rest[j:]
    return o


def one(k):
    rng = random.Random(job * 100003 + k)
    bname, base = bases[(job + k) % len(bases)] if not elites else bases[rng.randrange(len(bases))]
    K = rng.randint(*kick); w = rng.choice(WINDOWS)
    seed_f = f"{out}/seed_{job}_{k}.npy"; np.save(seed_f, np.array(perturb(base, K, rng), dtype=np.int64))
    res_f = f"{out}/job{job}_{k}.npy"
    cmd = [sys.executable, f"{HERE}/sar.py", seed_f, str(job * 1000 + k), str(minutes), res_f, str(thi), str(tlo),
           "--tmin", str(w[0]), "--tmax", str(w[1])]
    if rules == "local": cmd += ["--local", "--soft", "--weight", "0"]
    t = time.time(); p = subprocess.run(cmd, capture_output=True, text=True)
    st = re.search(r"start ([\d.]+) h", p.stdout); fn = re.search(r"best ([\d.]+) h t0 ([\d.]+)", p.stdout.split("done")[-1])
    os.remove(seed_f)
    ride = None
    if then_ride and rules == "local" and os.path.exists(res_f):
        rj = res_f[:-4] + ".json"; rr = res_f[:-4] + "_ride.json"
        e = subprocess.run([sys.executable, f"{HERE}/export.py", res_f, rj, "--robust", "--soft", "--weight", "0"], capture_output=True, text=True)
        if e.returncode == 0:
            q = subprocess.run([sys.executable, f"{HERE}/ridesearch.py", rj, rr, "--minutes", str(then_ride), "--seed", str(job * 1000 + k)],
                               capture_output=True, text=True)
            mm = re.search(r"-> ([\d.]+) h", q.stdout.split("done")[-1]) if q.returncode == 0 else None
            if mm: ride = (float(mm.group(1)), os.path.basename(rr))
    trace = [(float(a), float(b)) for a, b in re.findall(r"([\d.]+) min it \d+ T\s+[\d.]+ cur [\d.]+ best ([\d.]+)", p.stdout)]
    row = {"job": job, "k": k, "rules": rules, "base": os.path.basename(bname), "kick": K, "window": w,
            "start_h": float(st.group(1)) if st else None, "best_h": float(fn.group(1)) if fn else None,
            "t0_h": float(fn.group(2)) if fn else None, "secs": round(time.time() - t), "file": os.path.basename(res_f),
            "trace": trace, "err": p.stderr[-400:] if p.returncode else ""}
    if ride:   # the ride-level search's result, plan time (h); it is the start's result when better
        row["anneal_h"] = row["best_h"]; row["ride_h"] = ride[0]
        if row["best_h"] is None or ride[0] < row["best_h"]: row["best_h"], row["file"] = ride[0], ride[1]
    return row


deadline = time.time() + hours * 3600; rows = []; k = 0
with ThreadPoolExecutor(procs) as ex:
    futs = []
    while True:
        # keep `procs` starts running; launch a new one only if it can finish before the deadline
        futs = [f for f in futs if not f.done() or rows.append(f.result())]
        json.dump(rows, open(f"{out}/job{job}.json", "w"))
        if time.time() + minutes * 60 + 120 > deadline: break
        while len(futs) < procs and time.time() + minutes * 60 + 120 <= deadline:
            futs.append(ex.submit(one, k)); k += 1
        time.sleep(10)
    for f in futs: rows.append(f.result())
json.dump(rows, open(f"{out}/job{job}.json", "w"))
ok = [r for r in rows if r["best_h"]]
print(f"job {job} {rules}: {len(rows)} starts, best {min(r['best_h'] for r in ok) if ok else None} h")
