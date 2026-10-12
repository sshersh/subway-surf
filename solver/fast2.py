"""Incremental replay: checkpoints at each leg so a change at order position p only
re-simulates from the last leg that started before p."""
import numpy as np
from numba import njit
from engine import INF, Engine
from numba import njit
@njit(cache=True)
def _leg2(src, t, cur_trip, target, req, tkey, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
         ar, ready, kind, jin, jout, jfp, stamp, tb, tbstamp, gen, out_b, out_e, out_w):
    """Earliest train arrival at target. Fills out_b/out_e (ride board/exit conn) and
    out_w (walk origin stop, or -1) in reverse order. Returns (arrival, nlegs)."""
    n = ar.shape[0]
    # init source
    stamp[src] = gen; ar[src] = t; kind[src] = 0
    ready[src] = t + chg[src] if cur_trip >= 0 else t
    for k in range(fp_ptr[src], fp_ptr[src + 1]):
        j = fp_to[k]; w = t + fp_t[k]
        if stamp[j] != gen or w < ar[j]:
            stamp[j] = gen; ar[j] = w; ready[j] = w; kind[j] = 2; jfp[j] = src
    best_t = INF; best_in = -1; best_out = -1
    # binary search first connection departing at/after t
    lo, hi = 0, dep_t.shape[0]
    while lo < hi:
        mid = (lo + hi) // 2
        if dep_t[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    for c in range(lo, dep_t.shape[0]):
        d = dep_t[c]
        if best_t <= d:
            break
        tr = trip[c]
        boarded = tbstamp[tr] == gen
        if not boarded:
            s = dep_s[c]
            if (tr == cur_trip and s == src) or (stamp[s] == gen and ready[s] <= d):
                tbstamp[tr] = gen; tb[tr] = c; boarded = True
        if boarded:
            a = arr_t[c]; s2 = arr_s[c]
            if s2 == target and a < best_t and (req < 0 or tkey[tr] == req):
                best_t = a; best_in = tb[tr]; best_out = c
            if stamp[s2] != gen or a < ar[s2]:
                stamp[s2] = gen; ar[s2] = a; ready[s2] = a + chg[s2]; kind[s2] = 1
                jin[s2] = tb[tr]; jout[s2] = c
                for k in range(fp_ptr[s2], fp_ptr[s2 + 1]):
                    j = fp_to[k]; w = a + fp_t[k]
                    if stamp[j] != gen or w < ar[j]:
                        stamp[j] = gen; ar[j] = w; ready[j] = w; kind[j] = 2; jfp[j] = s2
    if best_t >= INF:
        return INF, 0
    # reconstruct
    m = 0
    b = best_in; e = best_out
    while True:
        out_b[m] = b; out_e[m] = e
        s = dep_s[b]
        if kind[s] == 2:
            out_w[m] = jfp[s]
            s = jfp[s]
        else:
            out_w[m] = -1
        m += 1
        if kind[s] == 0 or (s == src and trip[b] == cur_trip):
            break
        if kind[s] == 0:
            break
        b = jin[s]; e = jout[s]
        if m >= out_b.shape[0]:
            break
    return best_t, m




MAXL = 600


@njit(cache=True)
def replay_cp(order, okey, tkey, t0, start_leg, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
              ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen_box,
              cp_pos, cp_cur, cp_t, cp_trip, cp_first, cp_nvis, cp_vis, nlegs_box):
    """Checkpoint arrays describe the state at the START of each leg. Leg start_leg's checkpoint
    must be valid (start_leg=0 builds it from t0). Returns (end, first_dep, nvis)."""
    n = order.shape[0]
    ob = np.zeros(64, dtype=np.int64); oe = np.zeros(64, dtype=np.int64); ow = np.zeros(64, dtype=np.int64)
    if start_leg == 0:
        visited = np.zeros(n, dtype=np.bool_)
        cur = order[0]; t = t0; cur_trip = -1; first_dep = -1; nvis = 0; pos = 1
    else:
        visited = cp_vis[start_leg].copy()
        cur = cp_cur[start_leg]; t = cp_t[start_leg]; cur_trip = cp_trip[start_leg]
        first_dep = cp_first[start_leg]; nvis = cp_nvis[start_leg]; pos = cp_pos[start_leg]
    leg = start_leg
    gen = gen_box[0]
    while True:
        while pos < n and (visited[order[pos]] or order[pos] == cur):
            pos += 1
        if pos >= n:
            # finish any unvisited station (only possibly the start)
            tgt = -1
            for s in range(n):
                if not visited[s]:
                    tgt = s; break
            if tgt < 0:
                break
            req = -1
        else:
            tgt = order[pos]; req = okey[pos]
        if leg < MAXL:
            cp_pos[leg] = pos; cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
            cp_first[leg] = first_dep; cp_nvis[leg] = nvis; cp_vis[leg, :] = visited
        gen += 1
        a, m = _leg2(cur, t, cur_trip, tgt, req, tkey, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
                    ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen, ob, oe, ow)
        if a >= INF:
            gen_box[0] = gen; nlegs_box[0] = leg
            return INF, first_dep, nvis
        for q in range(m - 1, -1, -1):
            c = ob[q]
            if first_dep < 0:
                first_dep = dep_t[c]
            if not visited[dep_s[c]]:
                visited[dep_s[c]] = True; nvis += 1
            while True:
                s2 = arr_s[c]
                if not visited[s2]:
                    visited[s2] = True; nvis += 1
                if c == oe[q]:
                    break
                c = nxt[c]
        cur_trip = trip[oe[0]]; cur = tgt; t = a
        leg += 1
        if pos < n:
            pos += 1
    gen_box[0] = gen; nlegs_box[0] = leg
    return t, first_dep, nvis


class Fast:
    def __init__(self, path="model"):
        self.E = Engine(path); a = self.E.args
        self.tkey = np.load(path + "_tkey.npy").astype(np.int64)
        self.tt = a[:10]; self.n = self.E.n; ntrips = a[10]
        n = self.n
        self.ws = (np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(ntrips, np.int64), np.zeros(ntrips, np.int64))
        self.gen = np.zeros(1, np.int64)
        self.bufs = [self._buf(), self._buf()]
        self.cur = 0

    def _buf(self):
        n = self.n
        return [np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64),
                np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros((MAXL, n), np.bool_), np.zeros(1, np.int64)]

    def full(self, order, okey, t0):
        """Evaluate and make this the current solution's checkpoint set."""
        b = self.bufs[self.cur]
        end, first, nv = replay_cp(order, okey, self.tkey, t0, 0, *self.tt, *self.ws, self.gen, *b)
        return self._score(end, first, nv)

    def _score(self, end, first, nv):
        return INF if (end >= INF or nv < self.n) else end - first

    def leg_for_pos(self, p):
        """Last leg whose checkpoint position is < p (safe resume point)."""
        b = self.bufs[self.cur]; nl = int(b[7][0]); pos = b[0][:nl]
        k = int(np.searchsorted(pos, p, side="right")) - 1
        return max(k, 0)

    def try_(self, order, okey, t0, p):
        """Evaluate candidate with changes at positions >= p. Writes to the spare buffer."""
        k = self.leg_for_pos(p) if p > 0 else 0
        src, dst = self.bufs[self.cur], self.bufs[1 - self.cur]
        if k > 0:
            for i in range(7):
                dst[i][:k + 1] = src[i][:k + 1]
        end, first, nv = replay_cp(order, okey, self.tkey, t0, k, *self.tt, *self.ws, self.gen, *dst)
        return self._score(end, first, nv)

    def accept(self):
        self.cur = 1 - self.cur


def serve_keys(F):
    import collections
    m = F.E.m; sv = collections.defaultdict(set)
    for s, tr in zip(m["arr_s"], m["trip"]): sv[int(s)].add(int(F.tkey[tr]))
    return sv


def sanitize(F, order, okey):
    """A planned key that never ARRIVES at the station (e.g. the line's origin terminal) means
    'board here', so drop the constraint."""
    sv = serve_keys(F); k = okey.copy()
    for i, (s, q) in enumerate(zip(order, okey)):
        if q >= 0 and int(q) not in sv[int(s)]: k[i] = -1
    return k


def record(F, order, okey, t0):
    """Python mirror of replay_cp that also returns the ride legs (board, exit, walk-from)."""
    a_ = F.tt; n = F.n
    dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t = a_
    ws = F.ws
    ob = np.zeros(64, np.int64); oe = np.zeros(64, np.int64); ow = np.zeros(64, np.int64)
    visited = np.zeros(n, bool); cur = int(order[0]); t = t0; cur_trip = -1; first = -1; pos = 1
    legs = []; gen = int(F.gen[0])
    while True:
        while pos < n and (visited[order[pos]] or order[pos] == cur): pos += 1
        if pos >= n:
            rem = np.where(~visited)[0]
            if not len(rem): break
            tgt, req = int(rem[0]), -1
        else:
            tgt, req = int(order[pos]), int(okey[pos])
        gen += 1
        a, mm = _leg2(cur, t, cur_trip, tgt, req, F.tkey, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
                      *ws, gen, ob, oe, ow)
        if a >= INF: return None
        for q in range(mm - 1, -1, -1):
            c = int(ob[q])
            if first < 0: first = int(dep_t[c])
            visited[dep_s[c]] = True
            while True:
                visited[arr_s[c]] = True
                if c == oe[q]: break
                c = int(nxt[c])
            legs.append((int(ob[q]), int(oe[q]), int(ow[q])))
        cur_trip = int(trip[oe[0]]); cur = tgt; t = int(a)
        if pos < n: pos += 1
    F.gen[0] = gen
    return t, first, int(visited.sum()), legs
