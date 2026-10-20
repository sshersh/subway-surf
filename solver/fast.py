"""Incremental replay: checkpoints at each leg so a change at order position p only
re-simulates from the last leg that started before p."""
import numpy as np
from numba import njit
from engine import _leg, INF, Engine
from expr_leg import _legx

MAXL = 600


@njit(cache=True)
def replay_cp(order, t0, start_leg, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
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
        else:
            tgt = order[pos]
        if leg < MAXL:
            cp_pos[leg] = pos; cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
            cp_first[leg] = first_dep; cp_nvis[leg] = nvis; cp_vis[leg, :] = visited
        gen += 1
        a, m = _leg(cur, t, cur_trip, tgt, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
                    ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen, ob, oe, ow)
        if a >= INF:
            gen_box[0] = gen; nlegs_box[0] = leg
            return INF, first_dep, nvis
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
        cur_trip = trip[oe[0]]; cur = tgt; t = a
        leg += 1
        if pos < n:
            pos += 1
    if leg < MAXL:   # final state, for callers that add a last leg (e.g. a fixed finish)
        cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
    gen_box[0] = gen; nlegs_box[0] = leg
    return t, first_dep, nvis


@njit(cache=True)
def replay_rj(order, t0, start_leg, q, express, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
              ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen_box,
              cp_pos, cp_cur, cp_t, cp_trip, cp_first, cp_nvis, cp_vis, nlegs_box,
              o_pos, o_cur, o_t, o_trip, o_first, o_nvis, o_vis, o_nlegs, o_res, res):
    """replay_cp / replay_cpx for a candidate that differs from the current solution only at order
    positions < q. Once the candidate's state at the start of a leg (next target position, station,
    time, train, first departure, visited set) equals the current solution's state at that position,
    the rest of the run is identical: copy the current solution's remaining checkpoints and result
    instead of simulating them. Exact: same answer as a full replay. o_* is the current solution's
    buffer; res receives (end, first_dep, nvis)."""
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
    ol = o_nlegs[0]; ol_cp = min(ol, MAXL)
    j = 0
    while True:
        while pos < n and (visited[order[pos]] or order[pos] == cur):
            pos += 1
        if pos >= n:
            tgt = -1
            for s in range(n):
                if not visited[s]:
                    tgt = s; break
            if tgt < 0:
                break
        else:
            tgt = order[pos]
            if pos >= q:   # past the change: has the run rejoined the current solution?
                while j < ol_cp and o_pos[j] < pos:
                    j += 1
                if (j < ol_cp and o_pos[j] == pos and o_t[j] == t and o_cur[j] == cur and o_trip[j] == cur_trip
                        and o_first[j] == first_dep and o_nvis[j] == nvis and leg + (ol - j) < MAXL):
                    same = True
                    for s in range(n):
                        if visited[s] != o_vis[j, s]:
                            same = False; break
                    if same:
                        k = ol - j
                        for i in range(k):
                            cp_pos[leg + i] = o_pos[j + i]; cp_cur[leg + i] = o_cur[j + i]; cp_t[leg + i] = o_t[j + i]
                            cp_trip[leg + i] = o_trip[j + i]; cp_first[leg + i] = o_first[j + i]; cp_nvis[leg + i] = o_nvis[j + i]
                            cp_vis[leg + i, :] = o_vis[j + i, :]
                        if ol < MAXL:
                            cp_cur[leg + k] = o_cur[ol]; cp_t[leg + k] = o_t[ol]; cp_trip[leg + k] = o_trip[ol]
                        gen_box[0] = gen; nlegs_box[0] = leg + k
                        res[0] = o_res[0]; res[1] = o_res[1]; res[2] = o_res[2]
                        return o_res[0], o_res[1], o_res[2]
        if leg < MAXL:
            cp_pos[leg] = pos; cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
            cp_first[leg] = first_dep; cp_nvis[leg] = nvis; cp_vis[leg, :] = visited
        gen += 1
        if express:
            a, m = _legx(cur, t, cur_trip, tgt, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
                         ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen, ob, oe, ow)
        else:
            a, m = _leg(cur, t, cur_trip, tgt, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
                        ws_ar, ws_ready, ws_kind, ws_jin, ws_jout, ws_jfp, ws_stamp, ws_tb, ws_tbstamp, gen, ob, oe, ow)
        if a >= INF:
            gen_box[0] = gen; nlegs_box[0] = leg
            res[0] = INF; res[1] = first_dep; res[2] = nvis
            return INF, first_dep, nvis
        for qq in range(m - 1, -1, -1):
            c = ob[qq]
            if first_dep < 0:
                first_dep = dep_t[c]
            if nxt[c] != -2:
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
        cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
    gen_box[0] = gen; nlegs_box[0] = leg
    res[0] = t; res[1] = first_dep; res[2] = nvis
    return t, first_dep, nvis


class Fast:
    def __init__(self, path="model"):
        self.E = Engine(path); a = self.E.args
        self.tt = a[:10]; self.n = self.E.n; ntrips = a[10]
        n = self.n
        self.ws = (np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(ntrips, np.int64), np.zeros(ntrips, np.int64))
        self.gen = np.zeros(1, np.int64)
        self.bufs = [self._buf(), self._buf()]
        self.res = [np.zeros(3, np.int64), np.zeros(3, np.int64)]   # (end, first_dep, nvis) per buffer
        self.cur = 0
        self.express = False
        m = len(a[0]); self.pp = (np.zeros(m + 1, np.int64), np.zeros(1, np.int64))   # no pass-throughs (local rules)

    def _buf(self):
        n = self.n
        return [np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64),
                np.zeros(MAXL, np.int64), np.zeros(MAXL, np.int64), np.zeros((MAXL, n), np.bool_), np.zeros(1, np.int64)]

    def full(self, order, t0):
        """Evaluate and make this the current solution's checkpoint set."""
        b = self.bufs[self.cur]
        end, first, nv = self._full(order, t0, b)
        self.res[self.cur][:] = (end, first, nv)
        return self._score(end, first, nv)

    def _full(self, order, t0, b):
        return replay_cp(order, t0, 0, *self.tt, *self.ws, self.gen, *b)

    def _score(self, end, first, nv):
        return INF if (end >= INF or nv < self.n) else end - first

    def leg_for_pos(self, p):
        """Last leg whose checkpoint position is < p (safe resume point)."""
        b = self.bufs[self.cur]; nl = int(b[7][0]); pos = b[0][:nl]
        k = int(np.searchsorted(pos, p, side="right")) - 1
        return max(k, 0)

    def try_(self, order, t0, p, q=None):
        """Evaluate candidate with changes at positions >= p (and, if q is given, only at positions
        < q, so it can stop once it rejoins the current solution). Writes to the spare buffer."""
        k = self.leg_for_pos(p) if p > 0 else 0
        src, dst = self.bufs[self.cur], self.bufs[1 - self.cur]
        if k > 0:
            for i in range(7):
                dst[i][:k + 1] = src[i][:k + 1]
        if q is None:   # no rejoin shortcut (e.g. the order changed beyond the move)
            q = order.shape[0] + 1
        end, first, nv = replay_rj(order, t0, k, q, self.express, *self.pp, *self.tt, *self.ws, self.gen, *dst,
                                   *src, self.res[self.cur], self.res[1 - self.cur])
        return self._score(end, first, nv)

    def accept(self):
        self.cur = 1 - self.cur
