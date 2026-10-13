"""Simulated annealing, express rules (passing through counts)."""
import sys, time, math
import numpy as np
from expr import FastX as Fast, INF

seed_file, rng_seed, minutes, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
T_HI = float(sys.argv[5]) if len(sys.argv) > 5 else 300.0
T_LO = float(sys.argv[6]) if len(sys.argv) > 6 else 3.0
F = Fast()
rng = np.random.default_rng(rng_seed)
raw = np.load(seed_file).astype(np.int64)
if len(raw) == F.n + 1:
    t0, order = int(raw[0]), raw[1:].copy()
else:
    order = raw
    t0 = min(range(3 * 3600, 14 * 3600, 300), key=lambda t: F.E.cost(order, t)[0])
n = len(order)
cur = F.full(order, t0)
best, best_o, best_t0 = cur, order.copy(), t0
print(f"start {cur/3600:.3f} h t0 {t0/3600:.2f}", flush=True)
deadline = time.time() + minutes * 60; start = time.time(); it = 0
while True:
    now = time.time()
    if now > deadline: break
    T = T_HI * (T_LO / T_HI) ** ((now - start) / (deadline - start))
    nt0 = t0; r = rng.random()
    if r < 0.45:
        L = int(rng.integers(1, 41)); i = int(rng.integers(0, n - L + 1))
        seg = order[i:i + L]
        if rng.random() < 0.3: seg = seg[::-1]
        rest = np.concatenate([order[:i], order[i + L:]])
        j = int(rng.integers(0, len(rest) + 1))
        o = np.concatenate([rest[:j], seg, rest[j:]]); p = min(i, j)
    elif r < 0.88:
        i = int(rng.integers(0, n - 1)); j = min(n, i + int(rng.integers(2, 150)))
        o = order.copy(); o[i:j] = o[i:j][::-1]; p = i
    elif r < 0.96:
        i, j = sorted(rng.integers(0, n, 2)); o = order.copy(); o[i], o[j] = o[j], o[i]; p = int(i)
    else:
        nt0 = int(np.clip(t0 + rng.integers(-1800, 1801), 0, 20 * 3600)); o = order; p = 0
    c = F.try_(o, nt0, p if nt0 == t0 else 0)
    it += 1
    if c < INF and (c <= cur or rng.random() < math.exp((cur - c) / T)):
        F.accept(); order, t0, cur = (o if o is not order else order.copy()), nt0, c
        if c < best:
            best, best_o, best_t0 = c, order.copy(), t0
    if it % 50000 == 0:
        print(f"{(now-start)/60:5.1f} min it {it} T {T:6.1f} cur {cur/3600:.3f} best {best/3600:.3f}", flush=True)
        np.save(out, np.concatenate([[best_t0], best_o]))
np.save(out, np.concatenate([[best_t0], best_o]))
print(f"done it {it} best {best/3600:.3f} h t0 {best_t0/3600:.2f}", flush=True)
