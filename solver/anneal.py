"""Simulated annealing over the station order and start time, with incremental timetable replay.

    python3 sa2.py <seed.npy> <rng seed> <minutes> <out.npy> [T_hi] [T_lo] [--iters N] [--stall F] [--fix P]
    (sax.py: same, express rules)

The temperature falls from T_hi to T_lo over --iters moves (or over <minutes> when --iters is 0).
<minutes> is always a hard cap. Speed-ups that don't change the search:
  - each move is replayed only from the leg before its first changed position, and stops as soon as
    the run rejoins the current solution (same next target, station, time, train and visited set),
    since the rest is then identical (fast.replay_rj)
  - --stall F: in the last 30% of the schedule, stop when the best hasn't improved for F x --iters moves
  - --fix P: leave order positions < P and the start time alone (re-planning after a late change)
"""
import sys, time, math
import numpy as np
from fast import INF


def main(Fast):
    args = [a for a in sys.argv[1:]]
    opt = {"--iters": 0, "--stall": 0.0, "--fix": 0}
    for k in list(opt):
        if k in args:
            i = args.index(k); opt[k] = type(opt[k])(args[i + 1]); del args[i:i + 2]
    seed_file, rng_seed, minutes, out = args[0], int(args[1]), float(args[2]), args[3]
    T_HI = float(args[4]) if len(args) > 4 else 300.0
    T_LO = float(args[5]) if len(args) > 5 else 3.0
    iters, stall, fix = opt["--iters"], opt["--stall"], opt["--fix"]
    F = Fast()
    rng = np.random.default_rng(rng_seed)
    raw = np.load(seed_file).astype(np.int64)
    if len(raw) == F.n + 1:
        t0, order = int(raw[0]), raw[1:].copy()
    else:
        order = raw
        t0 = min(range(3 * 3600, 14 * 3600, 300), key=lambda t: F.E.cost(order, t)[0])
    n = len(order); lo = max(0, min(fix, n - 2))
    cur = F.full(order, t0)
    best, best_o, best_t0 = cur, order.copy(), t0
    print(f"start {cur/3600:.3f} h t0 {t0/3600:.2f} iters {iters} fix {lo}", flush=True)
    deadline = time.time() + minutes * 60; start = time.time(); it = 0; last_best = 0
    while True:
        now = time.time()
        if now > deadline: break
        frac = it / iters if iters else (now - start) / (deadline - start)
        if frac >= 1: break
        if stall and frac > 0.7 and it - last_best > stall * (iters or 1e12): break
        T = T_HI * (T_LO / T_HI) ** frac
        nt0 = t0; r = rng.random(); m = n - lo
        if r < 0.45:
            L = int(rng.integers(1, min(41, m))); i = lo + int(rng.integers(0, m - L + 1))
            seg = order[i:i + L]
            if rng.random() < 0.3: seg = seg[::-1]
            rest = np.concatenate([order[:i], order[i + L:]])
            j = lo + int(rng.integers(0, len(rest) - lo + 1))
            o = np.concatenate([rest[:j], seg, rest[j:]]); p = min(i, j); q = max(i, j) + L
        elif r < 0.88:
            i = lo + int(rng.integers(0, m - 1)); j = min(n, i + int(rng.integers(2, 150)))
            o = order.copy(); o[i:j] = o[i:j][::-1]; p = i; q = j
        elif r < 0.96:
            i, j = sorted(lo + rng.integers(0, m, 2)); o = order.copy(); o[i], o[j] = o[j], o[i]; p = int(i); q = int(j) + 1
        else:
            if lo: continue   # the start time is part of the fixed prefix
            nt0 = int(np.clip(t0 + rng.integers(-1800, 1801), 0, 20 * 3600)); o = order; p = 0; q = 0
        c = F.try_(o, nt0, p if nt0 == t0 else 0, q)
        it += 1
        if c < INF and (c <= cur or rng.random() < math.exp((cur - c) / T)):
            F.accept(); order, t0, cur = (o if o is not order else order.copy()), nt0, c
            if c < best:
                best, best_o, best_t0, last_best = c, order.copy(), t0, it
        if it % 50000 == 0:
            print(f"{(now-start)/60:5.1f} min it {it} T {T:6.1f} cur {cur/3600:.3f} best {best/3600:.3f}", flush=True)
            np.save(out, np.concatenate([[best_t0], best_o]))
    np.save(out, np.concatenate([[best_t0], best_o]))
    print(f"done it {it} in {(time.time()-start)/60:.1f} min, best {best/3600:.3f} h t0 {best_t0/3600:.2f}", flush=True)
