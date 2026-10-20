"""Timetable replay engine (Connection Scan Algorithm, numba-compiled).

A route is an ORDER over all stations. Replay starts at order[0] at time t0, then repeatedly
travels by earliest arrival (train arrival required) to the next station in the order that has
not been visited yet. Every station where a ridden train stops counts as visited.
"""
import json
import numpy as np
from numba import njit

INF = 1 << 40


def load(path):
    z = np.load(path + ".npz")
    meta = json.load(open(path + ".json"))
    return {k: z[k] for k in z.files}, meta


@njit(cache=True)
def _leg(src, t, cur_trip, target, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
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
            if s2 == target and a < best_t and nxt[c] != -2:   # a bus arrival is not a visit
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


@njit(cache=True)
def replay(order, t0, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t, ntrips,
           record, rec_b, rec_e, rec_w):
    """Returns (end_time, first_departure, nvisited, nrec). If record, ride legs are written
    to rec_b/rec_e/rec_w in forward order."""
    n = order.shape[0]
    visited = np.zeros(n, dtype=np.bool_)
    ar = np.zeros(n, dtype=np.int64); ready = np.zeros(n, dtype=np.int64)
    kind = np.zeros(n, dtype=np.int64); jin = np.zeros(n, dtype=np.int64)
    jout = np.zeros(n, dtype=np.int64); jfp = np.zeros(n, dtype=np.int64)
    stamp = np.zeros(n, dtype=np.int64)
    tb = np.zeros(ntrips, dtype=np.int64); tbstamp = np.zeros(ntrips, dtype=np.int64)
    ob = np.zeros(64, dtype=np.int64); oe = np.zeros(64, dtype=np.int64); ow = np.zeros(64, dtype=np.int64)
    cur = order[0]; t = t0; cur_trip = -1
    nvis = 0; first_dep = -1; gen = 0; nrec = 0; pos = 1
    while pos < n:
        tgt = order[pos]
        if visited[tgt]:
            pos += 1
            continue
        if tgt == cur:
            # standing here but not yet visited by train: go anywhere by train that stops here;
            # handled naturally by riding on from here, so skip to next target.
            pos += 1
            continue
        gen += 1
        a, m = _leg(cur, t, cur_trip, tgt, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
                    ar, ready, kind, jin, jout, jfp, stamp, tb, tbstamp, gen, ob, oe, ow)
        if a >= INF:
            return INF, first_dep, nvis, nrec
        for q in range(m - 1, -1, -1):
            c = ob[q]
            if first_dep < 0:
                first_dep = dep_t[c]
            if nxt[c] != -2:   # a bus leg visits nothing
                if not visited[dep_s[c]]:
                    visited[dep_s[c]] = True; nvis += 1
                while True:
                    s2 = arr_s[c]
                    if not visited[s2]:
                        visited[s2] = True; nvis += 1
                    if c == oe[q]:
                        break
                    c = nxt[c]
            if record:
                rec_b[nrec] = ob[q]; rec_e[nrec] = oe[q]; rec_w[nrec] = ow[q]; nrec += 1
        cur_trip = trip[oe[0]]
        cur = tgt; t = a
        pos += 1
    # any station never targeted after being skipped (only the start can be): try to finish it
    for s in range(n):
        if not visited[s]:
            gen += 1
            a, m = _leg(cur, t, cur_trip, s, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
                        ar, ready, kind, jin, jout, jfp, stamp, tb, tbstamp, gen, ob, oe, ow)
            if a >= INF:
                return INF, first_dep, nvis, nrec
            for q in range(m - 1, -1, -1):
                c = ob[q]
                if nxt[c] != -2:
                    if not visited[dep_s[c]]:
                        visited[dep_s[c]] = True; nvis += 1
                    while True:
                        s2 = arr_s[c]
                        if not visited[s2]:
                            visited[s2] = True; nvis += 1
                        if c == oe[q]:
                            break
                        c = nxt[c]
                if record:
                    rec_b[nrec] = ob[q]; rec_e[nrec] = oe[q]; rec_w[nrec] = ow[q]; nrec += 1
            cur_trip = trip[oe[0]]; cur = s; t = a
    return t, first_dep, nvis, nrec


class Engine:
    def __init__(self, path):
        self.m, self.meta = load(path)
        m = self.m
        self.args = (m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"], m["nxt"], m["chg"],
                     m["fp_ptr"], m["fp_to"], m["fp_t"], int(m["trip"].max()) + 1)
        self.n = len(self.meta["stations"])
        self._z = np.zeros(1, dtype=np.int64)

    def cost(self, order, t0):
        end, first, nv, _ = replay(order, t0, *self.args, False, self._z, self._z, self._z)
        if end >= INF or nv < self.n:
            return INF, first
        return end - first, first

    def record(self, order, t0):
        b = np.zeros(4000, dtype=np.int64); e = np.zeros(4000, dtype=np.int64); w = np.zeros(4000, dtype=np.int64)
        end, first, nv, nr = replay(order, t0, *self.args, True, b, e, w)
        return end, first, nv, list(zip(b[:nr], e[:nr], w[:nr]))
