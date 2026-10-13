"""Fixed start and finish stations.

The route starts on the platform at order[0] at t0 (so waiting or walking there counts) and is
only done once every station is covered AND you have arrived by train at END. If the last new
station isn't END, the ride from there to END is added. Works with local or express rules.

    python3 ends.py <seed.npy> <rng> <minutes> <out.npy> <T_hi> <T_lo> --end <idx> [--express]
"""
import sys, time, math
import numpy as np
from engine import _leg, INF
from fast import Fast, replay_cp
from expr import FastX, replay_cpx


class Ends:
    def __init__(self, end, express=False, path="model"):
        self.F = FastX(path) if express else Fast(path)
        self.end, self.express = end, express
        self.ob = np.zeros(64, np.int64); self.oe = np.zeros(64, np.int64); self.ow = np.zeros(64, np.int64)

    def _replay(self, order, t0, k, buf):
        F = self.F
        if self.express:
            return replay_cpx(order, t0, k, *F.pp, *F.tt, *F.ws, F.gen, *buf)
        return replay_cp(order, t0, k, *F.tt, *F.ws, F.gen, *buf)

    def _finish(self, buf, end_t, nv):
        """Ride from the final position to END (if not already there). Returns (arrival, legs)."""
        F = self.F
        if end_t >= INF or nv < F.n: return INF, 0
        nl = int(buf[7][0]); cur = int(buf[1][nl]); t = int(buf[2][nl]); trip = int(buf[3][nl])
        if cur == self.end: return t, 0
        F.gen[0] += 1
        dep_t, arr_t, dep_s, arr_s, trp, nxt, chg, fp_ptr, fp_to, fp_t = F.tt
        a, m = _leg(cur, t, trip, self.end, dep_t, arr_t, dep_s, arr_s, trp, chg, fp_ptr, fp_to, fp_t,
                    *F.ws, int(F.gen[0]), self.ob, self.oe, self.ow)
        return a, m

    def full(self, order, t0):
        buf = self.F.bufs[self.F.cur]
        end_t, _, nv = self._replay(order, t0, 0, buf)
        a, _ = self._finish(buf, end_t, nv)
        return INF if a >= INF else a - t0

    def try_(self, order, t0, p):
        F = self.F
        k = F.leg_for_pos(p) if p > 0 else 0
        src, dst = F.bufs[F.cur], F.bufs[1 - F.cur]
        if k > 0:
            for i in range(7): dst[i][:k + 1] = src[i][:k + 1]
        end_t, _, nv = self._replay(order, t0, k, dst)
        a, _ = self._finish(dst, end_t, nv)
        return INF if a >= INF else a - t0

    def accept(self): self.F.accept()

    def final_legs(self, order, t0):
        """Legs of the closing ride to END, in forward order (after a full() call)."""
        buf = self.F.bufs[self.F.cur]
        end_t, _, nv = self._replay(order, t0, 0, buf)
        a, m = self._finish(buf, end_t, nv)
        return a, [(int(self.ob[q]), int(self.oe[q]), int(self.ow[q])) for q in range(m - 1, -1, -1)]


if __name__ == "__main__":
    args = sys.argv[1:]
    express = "--express" in args
    if express: args.remove("--express")
    i = args.index("--end"); END = int(args[i + 1]); del args[i:i + 2]
    seed_file, rng_seed, minutes, out, T_HI, T_LO = args[0], int(args[1]), float(args[2]), args[3], float(args[4]), float(args[5])
    S = Ends(END, express); rng = np.random.default_rng(rng_seed)
    raw = np.load(seed_file).astype(np.int64)
    order = raw[0].copy() if raw.ndim == 2 else raw[1:].copy()
    if order[-1] != END:   # keep the finish last in the order too
        order = np.concatenate([order[order != END], [END]])
    n = len(order)
    t0 = min(range(3 * 3600, 15 * 3600, 300), key=lambda t: S.full(order, t))
    cur = S.full(order, t0); best = (cur, order.copy(), t0)
    print(f"start {cur/3600:.3f} h t0 {t0/3600:.2f}", flush=True)
    save = lambda: np.save(out, np.concatenate([[best[2]], best[1]]))
    deadline = time.time() + minutes * 60; start = time.time(); it = 0
    while True:
        now = time.time()
        if now > deadline: break
        T = T_HI * (T_LO / T_HI) ** ((now - start) / (deadline - start))
        nt0 = t0; r = rng.random(); o = order
        hi = n - 1   # positions 1 .. n-2 move; first and last stay fixed
        if r < 0.45:
            L = int(rng.integers(1, 41)); L = min(L, hi - 1); i = int(rng.integers(1, hi - L + 1))
            seg = order[i:i + L]
            if rng.random() < 0.3: seg = seg[::-1]
            rest = np.concatenate([order[:i], order[i + L:]])
            j = int(rng.integers(1, len(rest)))
            o = np.concatenate([rest[:j], seg, rest[j:]]); p = min(i, j)
        elif r < 0.88:
            i = int(rng.integers(1, hi - 1)); j = min(hi, i + int(rng.integers(2, 150)))
            o = order.copy(); o[i:j] = o[i:j][::-1]; p = i
        elif r < 0.96:
            i, j = sorted(rng.integers(1, hi, 2)); o = order.copy(); o[i], o[j] = o[j], o[i]; p = int(i)
        else:
            nt0 = int(np.clip(t0 + rng.integers(-1800, 1801), 0, 20 * 3600)); p = 0
        assert o[0] == order[0] and o[-1] == END
        c = S.try_(o, nt0, p if nt0 == t0 else 0); it += 1
        if c < INF and (c <= cur or rng.random() < math.exp((cur - c) / T)):
            S.accept(); order = o if o is not order else order.copy(); t0 = nt0; cur = c
            if c < best[0]: best = (c, order.copy(), t0)
        if it % 50000 == 0:
            print(f"{(now-start)/60:5.1f} min it {it} T {T:6.1f} cur {cur/3600:.3f} best {best[0]/3600:.3f}", flush=True); save()
    save()
    print(f"done it {it} best {best[0]/3600:.3f} h t0 {best[2]/3600:.2f}", flush=True)
