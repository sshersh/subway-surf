"""Robustness-aware replay: hard minimum slack at boardings + expected miss cost in the objective.

Same station-order replay as fast.py / expr.py (local or express rules), with two additions:

1. Hard slack. A boarding is allowed only if the rider is ready (arrival + realistic change time, or
   end of a walk) at least buf[c] seconds before the train leaves. buf comes from model.py: 0-3 min by
   the headway to the next equivalent train, +1 min at night when that headway is >= 10 min
   (realistic.board_buffer). Staying on the same train and the very first boarding are exempt.
2. Expected miss cost. For every boarding the remaining slack s gives P(miss) = 0.5 (1 + x/2) e^-x,
   x = s / B (B = Laplace scale of the difference in two trains' lateness, larger at night and after a
   street walk). Missing costs the gap to the next train that also gets you to the ride's end (max of
   the boarding hop's and the alighting hop's headway), capped at MISS_CAP. The annealer minimises
   plan time + weight x sum(P x cost).

    from robust import FastR, record
    F = FastR("model", express=True, weight=1.0)
"""
import numpy as np
from numba import njit
from engine import INF
import realistic as R

MAXL = 600


@njit(cache=True)
def _loss(slack, c, lt, sl, adj, cap):
    """Interpolated expected loss (s) for this slack in loss-table row c, + adj, clipped to [0, cap]."""
    k = sl.shape[0]
    if slack <= sl[0]:
        v = lt[c, 0]
    elif slack >= sl[k - 1]:
        v = lt[c, k - 1]
    else:
        i = 0
        while sl[i + 1] < slack:
            i += 1
        f = (slack - sl[i]) / (sl[i + 1] - sl[i])
        v = lt[c, i] * (1 - f) + lt[c, i + 1] * f
    v += adj
    if v < 0.0:
        v = 0.0
    if v > cap:
        v = cap
    return v


@njit(cache=True)
def _legr(src, t, cur_trip, target, express, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
          buf, hw, cls, lt, sl, ladj, rp, ar, ready, kind, jin, jout, jfp, stamp, tb, tbstamp, gen, out_b, out_e, out_w, pen):
    """Earliest arrival at target (stopping there, or with express passing it) under the hard-slack
    rule. Fills out_b/out_e/out_w in reverse order; pen[0] = expected miss cost (s) of this leg's
    boardings. Returns (arrival, nlegs)."""
    # cur_trip: the train you arrived on, -1 at the very start (no change time, no buffer), or -2 when
    # re-planning mid-route off a train the model doesn't know (change time and buffer apply)
    stamp[src] = gen; ar[src] = t; kind[src] = 0
    ready[src] = t + chg[src] if cur_trip != -1 else t
    for k in range(fp_ptr[src], fp_ptr[src + 1]):
        j = fp_to[k]; w = t + fp_t[k]
        if stamp[j] != gen or w < ar[j]:
            stamp[j] = gen; ar[j] = w; ready[j] = w; kind[j] = 2; jfp[j] = src
    best_t = INF; best_in = -1; best_out = -1
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
            if tr == cur_trip and s == src:
                tbstamp[tr] = gen; tb[tr] = c; boarded = True
            elif stamp[s] == gen:
                need = ready[s]
                if not (s == src and cur_trip == -1):
                    need += buf[c]
                if need <= d:
                    tbstamp[tr] = gen; tb[tr] = c; boarded = True
        if boarded:
            a = arr_t[c]; s2 = arr_s[c]
            if a < best_t:
                hit = s2 == target
                if express and not hit:
                    for k in range(pp_ptr[c], pp_ptr[c + 1]):
                        if pp_lst[k] == target:
                            hit = True; break
                if hit:
                    best_t = a; best_in = tb[tr]; best_out = c
            if stamp[s2] != gen or a < ar[s2]:
                stamp[s2] = gen; ar[s2] = a; ready[s2] = a + chg[s2]; kind[s2] = 1
                jin[s2] = tb[tr]; jout[s2] = c
                for k in range(fp_ptr[s2], fp_ptr[s2 + 1]):
                    j = fp_to[k]; w = a + fp_t[k]
                    if stamp[j] != gen or w < ar[j]:
                        stamp[j] = gen; ar[j] = w; ready[j] = w; kind[j] = 2; jfp[j] = s2
    pen[0] = 0.0
    if best_t >= INF:
        return INF, 0
    m = 0
    b = best_in; e = best_out
    while True:
        out_b[m] = b; out_e[m] = e
        s = dep_s[b]
        # expected real-day loss of this boarding: calibrated expected lateness at the alighting stop
        # given the slack (headway class x day/night table, plus a per-line adjustment), floored at 0
        if not ((trip[b] == cur_trip and s == src) or (s == src and cur_trip == -1)):
            pen[0] += rp[0] * _loss(dep_t[b] - ready[s] - (rp[2] if kind[s] == 2 else 0.0), cls[b], lt, sl, ladj[b], rp[1])
        if kind[s] == 2:
            out_w[m] = jfp[s]
            s = jfp[s]
        else:
            out_w[m] = -1
        m += 1
        if kind[s] == 0 or (s == src and trip[b] == cur_trip):
            break
        b = jin[s]; e = jout[s]
        if m >= out_b.shape[0]:
            break
    return best_t, m


@njit(cache=True)
def replay_r(order, t0, start_leg, q, express, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
             buf, hw, cls, lt, sl, ladj, rp,
             ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen_box,
             cp_pos, cp_cur, cp_t, cp_trip, cp_first, cp_nvis, cp_vis, cp_pen, nlegs_box,
             o_pos, o_cur, o_t, o_trip, o_first, o_nvis, o_vis, o_pen, o_nlegs, o_res, res):
    """fast.replay_rj with the robust leg search and a running penalty (cp_pen: penalty accumulated
    before each leg). res = (end, first_dep, nvis, penalty). q > n disables the rejoin shortcut."""
    n = order.shape[0]
    ob = np.zeros(64, dtype=np.int64); oe = np.zeros(64, dtype=np.int64); ow = np.zeros(64, dtype=np.int64)
    pen1 = np.zeros(1, dtype=np.float64)
    if start_leg == 0:
        visited = np.zeros(n, dtype=np.bool_)
        cur = order[0]; t = t0; cur_trip = -1; first_dep = -1; nvis = 0; pos = 1; pen = 0
    else:
        visited = cp_vis[start_leg].copy()
        cur = cp_cur[start_leg]; t = cp_t[start_leg]; cur_trip = cp_trip[start_leg]
        first_dep = cp_first[start_leg]; nvis = cp_nvis[start_leg]; pos = cp_pos[start_leg]; pen = cp_pen[start_leg]
    leg = start_leg
    gen = gen_box[0]
    ol = o_nlegs[0]; ol_cp = min(ol, MAXL)
    j = 0
    while True:
        while pos < n and (visited[order[pos]] or order[pos] == cur):
            pos += 1
        if pos >= n:
            tgt = -1
            for s in range(visited.shape[0]):
                if not visited[s]:
                    tgt = s; break
            if tgt < 0:
                break
        else:
            tgt = order[pos]
            if pos >= q:
                while j < ol_cp and o_pos[j] < pos:
                    j += 1
                if (j < ol_cp and o_pos[j] == pos and o_t[j] == t and o_cur[j] == cur and o_trip[j] == cur_trip
                        and o_first[j] == first_dep and o_nvis[j] == nvis and leg + (ol - j) < MAXL):
                    same = True
                    for s in range(visited.shape[0]):
                        if visited[s] != o_vis[j, s]:
                            same = False; break
                    if same:
                        k = ol - j
                        dpen = pen - o_pen[j]
                        for i in range(k):
                            cp_pos[leg + i] = o_pos[j + i]; cp_cur[leg + i] = o_cur[j + i]; cp_t[leg + i] = o_t[j + i]
                            cp_trip[leg + i] = o_trip[j + i]; cp_first[leg + i] = o_first[j + i]; cp_nvis[leg + i] = o_nvis[j + i]
                            cp_vis[leg + i, :] = o_vis[j + i, :]; cp_pen[leg + i] = o_pen[j + i] + dpen
                        if ol < MAXL:
                            cp_cur[leg + k] = o_cur[ol]; cp_t[leg + k] = o_t[ol]; cp_trip[leg + k] = o_trip[ol]
                        gen_box[0] = gen; nlegs_box[0] = leg + k
                        res[0] = o_res[0]; res[1] = o_res[1]; res[2] = o_res[2]; res[3] = o_res[3] + dpen
                        return res[0], res[1], res[2], res[3]
        if leg < MAXL:
            cp_pos[leg] = pos; cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
            cp_first[leg] = first_dep; cp_nvis[leg] = nvis; cp_vis[leg, :] = visited; cp_pen[leg] = pen
        gen += 1
        a, m = _legr(cur, t, cur_trip, tgt, express, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
                     buf, hw, cls, lt, sl, ladj, rp, ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen,
                     ob, oe, ow, pen1)
        if a >= INF:
            gen_box[0] = gen; nlegs_box[0] = leg
            res[0] = INF; res[1] = first_dep; res[2] = nvis; res[3] = pen
            return INF, first_dep, nvis, pen
        pen += int(pen1[0] + 0.5)
        for qq in range(m - 1, -1, -1):
            c = ob[qq]
            if first_dep < 0:
                first_dep = dep_t[c]
            if not visited[dep_s[c]]:
                visited[dep_s[c]] = True; nvis += 1
            while True:
                if express:
                    for k in range(pp_ptr[c], pp_ptr[c + 1]):
                        if not visited[pp_lst[k]]:
                            visited[pp_lst[k]] = True; nvis += 1
                s2 = arr_s[c]
                if not visited[s2]:
                    visited[s2] = True; nvis += 1
                if c == oe[qq]:
                    break
                c = nxt[c]
        cur_trip = trip[oe[0]]; cur = arr_s[oe[0]]; t = a
        leg += 1
        if pos < n:
            pos += 1
    if leg < MAXL:
        cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip; cp_pen[leg] = pen
    gen_box[0] = gen; nlegs_box[0] = leg
    res[0] = t; res[1] = first_dep; res[2] = nvis; res[3] = pen
    return t, first_dep, nvis, pen


LOSS_TABLE = __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "loss_table.json")


def loss_model(z, meta, path=LOSS_TABLE):
    """Per-connection loss-table row (headway class x night), the table (s) on its slack grid, and a
    per-connection line adjustment (s). From headways/calibrate.py (real train movements)."""
    import json, os
    hw = z["hw"] if "hw" in z.files else np.full(len(z["dep_t"]), 600, np.int64)
    sod = z["dep_t"] % 86400
    night = ((sod >= R.NIGHT[0]) | (sod < R.NIGHT[1])).astype(np.int64)
    if not os.path.exists(path):   # no calibration: Laplace miss model folded into a table
        sl = np.array([0, 30, 60, 90, 120, 180, 240, 300, 420, 600, 900], np.float64)
        hwb = np.array([0, 300, 450, 600, 900, 1500, 99999])
        lt = np.zeros((2 * (len(hwb) - 1), len(sl)))
        for hb in range(len(hwb) - 1):
            for nt in (0, 1):
                B = R.B_NIGHT if nt else R.B_DAY; h = min((hwb[hb] + min(hwb[hb + 1], 1800)) / 2, R.MISS_CAP)
                x = sl / B; lt[2 * hb + nt] = 0.5 * (1 + x / 2) * np.exp(-x) * h
        cls = (np.searchsorted(hwb, hw, side="right") - 1) * 2 + night
        return cls.astype(np.int64), lt, sl, np.zeros(len(hw))
    tab = json.load(open(path)); sl = np.array(tab["slack"], np.float64); hwb = np.array(tab["hw"])
    nb = len(hwb) - 1
    lt = np.zeros((2 * nb, len(sl)))
    for hb in range(nb):
        for nt in (0, 1):
            row = []
            for s_ in tab["slack"]:
                x = tab["table"].get(f"{s_}|{hb}|{nt}")
                if x is None or x["n"] < 30:   # thin cell: borrow the next lower headway class
                    x = next((tab["table"].get(f"{s_}|{h2}|{nt}") for h2 in range(hb - 1, -1, -1)
                              if tab["table"].get(f"{s_}|{h2}|{nt}") and tab["table"][f"{s_}|{h2}|{nt}"]["n"] >= 30), None)
                    x = x or tab["table"].get(f"{s_}|{hb}|{1 - nt}") or {"mean": 0.0}
                row.append(x["mean"])
            # monotone non-increasing in slack (more slack never hurts)
            for i in range(1, len(row)): row[i] = min(row[i], row[i - 1])
            lt[2 * hb + nt] = row
    cls = (np.minimum(np.searchsorted(hwb, hw, side="right") - 1, nb - 1)) * 2 + night
    T = meta["T"]; rt = meta["trip_route"]; base = lambda r: r[:-1] if len(r) == 2 and r.endswith("X") else r
    adj = tab.get("line_adj", {})
    tr = z["trip"]
    radj = {}
    lines = [base(rt[int(x) % T]) for x in range(int(tr.max()) + 1)]
    a0 = np.array([adj.get(f"{l}|0", 0.0) for l in lines]); a1 = np.array([adj.get(f"{l}|1", 0.0) for l in lines])
    ladj = np.where(night == 1, a1[tr], a0[tr])
    return cls.astype(np.int64), lt, sl, ladj.astype(np.float64)


class FastR:
    """Drop-in for fast.Fast / expr.FastX in anneal.main, scoring plan time + weight x expected miss cost.
    hard=False drops the hard-slack rule (buf = 0); weight=0 drops the penalty."""
    def __init__(self, path="model", express=True, weight=1.0, hard=True, pass_path=None):
        z = np.load(path + ".npz")
        import json
        self.meta = json.load(open(path + ".json"))
        self.n = n = len(self.meta["stations"])
        self.tt = (z["dep_t"], z["arr_t"], z["dep_s"], z["arr_s"], z["trip"], z["nxt"], z["chg"], z["fp_ptr"], z["fp_to"], z["fp_t"])
        self.m = {k: z[k] for k in z.files}
        ncon = len(z["dep_t"]); ntrips = int(z["trip"].max()) + 1
        buf = z["buf"] if (hard and "buf" in z.files) else np.zeros(ncon, np.int64)
        hw = z["hw"] if "hw" in z.files else np.full(ncon, 600, np.int64)
        cls, lt, sl, ladj = loss_model(z, self.meta)
        self.rob = (buf.astype(np.int64), hw.astype(np.int64), cls, lt, sl, ladj,
                    np.array([float(weight), float(R.MISS_CAP), float(R.WALK_SLACK_LOSS)]))
        self.express = bool(express)
        if express:
            p = np.load(pass_path or (path + "_pass.npz")); self.pp = (p["ptr"].astype(np.int64), p["lst"].astype(np.int64))
        else:
            self.pp = (np.zeros(ncon + 1, np.int64), np.zeros(1, np.int64))
        self.ws = (np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(ntrips, np.int64), np.zeros(ntrips, np.int64))
        self.gen = np.zeros(1, np.int64)
        self.bufs = [self._buf(), self._buf()]
        self.res = [np.zeros(4, np.int64), np.zeros(4, np.int64)]
        self.cur = 0
        self.E = self   # anneal.main uses F.E.cost for the start-time search

    def _buf(self):
        n = self.n
        return [np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64),
                np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros((MAXL, n), np.bool_), np.zeros(MAXL, np.int64),
                np.zeros(1, np.int64)]

    def _run(self, order, t0, k, q, dst, src, rs, rd):
        return replay_r(order, int(t0), k, q, self.express, *self.pp, *self.tt, *self.rob, *self.ws, self.gen, *dst, *src, rs, rd)

    def _score(self, r):
        end, first, nv, pen = (int(x) for x in r)
        return INF if (end >= INF or nv < self.n) else end - first + pen

    def full(self, order, t0):
        b = self.bufs[self.cur]
        r = self._run(order, t0, 0, order.shape[0] + 1, b, self.bufs[1 - self.cur], self.res[1 - self.cur], self.res[self.cur])
        return self._score(r)

    def cost(self, order, t0):
        c = self.full(order, t0)
        return c, int(self.res[self.cur][1])

    def parts(self):
        """(plan seconds, penalty seconds) of the current solution."""
        end, first, nv, pen = (int(x) for x in self.res[self.cur])
        return end - first, pen

    def leg_for_pos(self, p):
        b = self.bufs[self.cur]; nl = int(b[8][0]); pos = b[0][:nl]
        k = int(np.searchsorted(pos, p, side="right")) - 1
        return max(k, 0)

    def try_(self, order, t0, p, q=None):
        k = self.leg_for_pos(p) if p > 0 else 0
        src, dst = self.bufs[self.cur], self.bufs[1 - self.cur]
        if k > 0:
            for i in range(8):
                dst[i][:k + 1] = src[i][:k + 1]
        if q is None:
            q = order.shape[0] + 1
        r = self._run(order, t0, k, q, dst, src, self.res[self.cur], self.res[1 - self.cur])
        return self._score(r)

    def accept(self):
        self.cur = 1 - self.cur


def record(F, order, t0, start_state=None, partial=False):
    """Python mirror of replay_r returning ride legs with their risk:
    (end, first_dep, nvisited, legs, penalty) where legs = [(board conn, exit conn, walk-from or -1, slack s, miss cost s,
    expected loss s)].
    start_state = (station, time, current trip, visited bool array) to replay from mid-route (re-planning).
    partial=True: when a station can't be reached any more, return the legs up to there instead of None."""
    dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t = F.tt; n = len(order); pp_ptr, pp_lst = F.pp
    buf, hw, cls, lt, sl, ladj, rp = F.rob
    ar, ready, kind = F.ws[0], F.ws[1], F.ws[2]
    ob = np.zeros(64, np.int64); oe = np.zeros(64, np.int64); ow = np.zeros(64, np.int64); pen1 = np.zeros(1)
    if start_state is None:
        visited = np.zeros(F.n, bool); cur = int(order[0]); t = int(t0); cur_trip = -1
    else:
        cur, t, cur_trip, visited = start_state; visited = visited.copy()
    first = -1; pos = 1 if start_state is None else 0; legs = []; pen = 0
    gen = int(F.gen[0])
    while True:
        while pos < n and (visited[order[pos]] or order[pos] == cur): pos += 1
        if pos >= n:
            rem = np.where(~visited)[0]
            if not len(rem): break
            tgt = int(rem[0])
        else:
            tgt = int(order[pos])
        gen += 1
        a, mm = _legr(cur, t, cur_trip, tgt, F.express, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
                      buf, hw, cls, lt, sl, ladj, rp, *F.ws, gen, ob, oe, ow, pen1)
        if a >= INF:
            F.gen[0] = gen
            return (t, first, int(visited.sum()), legs, pen) if partial and legs else None
        pen += int(pen1[0] + 0.5)
        for q in range(mm - 1, -1, -1):
            c = int(ob[q]); e = int(oe[q]); s = int(dep_s[c])
            exempt = (int(trip[c]) == cur_trip and s == cur) or (s == cur and cur_trip == -1)
            slack = int(dep_t[c] - ready[s]); cost = min(max(int(hw[c]), int(hw[e])), int(R.MISS_CAP))
            P = float(_loss(slack - (rp[2] if kind[s] == 2 else 0.0), cls[c], lt, sl, ladj[c], rp[1]))   # expected loss (s)
            if first < 0: first = int(dep_t[c])
            visited[dep_s[c]] = True
            while True:
                if F.express: visited[pp_lst[pp_ptr[c]:pp_ptr[c + 1]]] = True
                visited[arr_s[c]] = True
                if c == e: break
                c = int(nxt[c])
            legs.append((int(ob[q]), e, int(ow[q]), None if exempt else slack, None if exempt else cost, 0.0 if exempt else P))
        cur_trip = int(trip[oe[0]]); cur = int(arr_s[oe[0]]); t = int(a)
        if pos < n: pos += 1
    F.gen[0] = gen
    return t, first, int(visited.sum()), legs, pen
