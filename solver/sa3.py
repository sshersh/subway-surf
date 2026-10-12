"""Annealing over (station order, planned arrival line per station, start time)."""
import sys, time, math, collections
import numpy as np
from fast2 import Fast, INF, sanitize

seed_file, rng_seed, minutes, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
T_HI = float(sys.argv[5]) if len(sys.argv) > 5 else 300.0
T_LO = float(sys.argv[6]) if len(sys.argv) > 6 else 3.0
F = Fast(); m = F.E.m
rng = np.random.default_rng(rng_seed)
raw = np.load(seed_file).astype(np.int64)
if raw.ndim == 2 and raw.shape[0] == 3:      # saved solution: [order, okey, t0-row]
    order, okey, t0 = raw[0].copy(), raw[1].copy(), int(raw[2][0])
else:
    order, okey = raw[0].copy(), raw[1].copy()
    t0 = min(range(3 * 3600, 14 * 3600, 300), key=lambda t: F.full(order, okey, t))
okey = sanitize(F, order, okey); n = len(order)
serve = collections.defaultdict(set)
for s, tr in zip(m["arr_s"], m["trip"]): serve[int(s)].add(int(F.tkey[tr]))
serve = {s: np.array(sorted(v)) for s, v in serve.items()}

cur = F.full(order, okey, t0)
best = (cur, order.copy(), okey.copy(), t0)
print(f"start {cur/3600:.3f} h t0 {t0/3600:.2f}", flush=True)
deadline = time.time() + minutes * 60; start = time.time(); it = 0
def save():
    np.save(out, np.array([best[1], best[2], np.full(n, best[3])]))
while True:
    now = time.time()
    if now > deadline: break
    T = T_HI * (T_LO / T_HI) ** ((now - start) / (deadline - start))
    nt0 = t0; r = rng.random()
    o, k = order, okey
    if r < 0.40:
        L = int(rng.integers(1, 41)); i = int(rng.integers(0, n - L + 1))
        idx = np.arange(i, i + L)
        if rng.random() < 0.3: idx = idx[::-1]
        rest = np.concatenate([np.arange(0, i), np.arange(i + L, n)])
        j = int(rng.integers(0, len(rest) + 1))
        perm = np.concatenate([rest[:j], idx, rest[j:]])
        o, k = order[perm], okey[perm]; p = min(i, j)
    elif r < 0.75:
        i = int(rng.integers(0, n - 1)); j = min(n, i + int(rng.integers(2, 150)))
        o, k = order.copy(), okey.copy(); o[i:j] = o[i:j][::-1]; k[i:j] = k[i:j][::-1]; p = i
    elif r < 0.80:
        i, j = sorted(rng.integers(0, n, 2)); o, k = order.copy(), okey.copy()
        o[i], o[j] = o[j], o[i]; k[i], k[j] = k[j], k[i]; p = int(i)
    elif r < 0.96:
        i = int(rng.integers(0, n)); k = okey.copy()
        opts = serve[int(order[i])]
        k[i] = -1 if rng.random() < 0.15 else int(rng.choice(opts)); p = i
    else:
        nt0 = int(np.clip(t0 + rng.integers(-1800, 1801), 0, 20 * 3600)); p = 0
    c = F.try_(o, k, nt0, p if nt0 == t0 else 0)
    it += 1
    if c < INF and (c <= cur or rng.random() < math.exp((cur - c) / T)):
        F.accept()
        order, okey, t0, cur = (o.copy() if o is order else o), (k.copy() if k is okey else k), nt0, c
        if c < best[0]:
            best = (c, order.copy(), okey.copy(), t0)
    if it % 50000 == 0:
        print(f"{(now-start)/60:5.1f} min it {it} T {T:6.1f} cur {cur/3600:.3f} best {best[0]/3600:.3f}", flush=True)
        save()
save()
print(f"done it {it} best {best[0]/3600:.3f} h t0 {best[3]/3600:.2f}", flush=True)
