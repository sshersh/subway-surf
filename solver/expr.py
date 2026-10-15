"""Express rules: a station counts when a train you ride stops at it OR passes through it.

Same incremental replay as fast.py, plus per-connection pass-through lists from passes.py
(model_pass.npz). A leg can end by passing its target; you are then at that hop's next stop."""
import numpy as np
from numba import njit
from engine import INF
from fast import Fast, MAXL
from expr_leg import _legx


@njit(cache=True)
def replay_cpx(order, t0, start_leg, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t,
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
        a, m = _legx(cur, t, cur_trip, tgt, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
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
                for k in range(pp_ptr[c], pp_ptr[c + 1]):
                    if not visited[pp_lst[k]]:
                        visited[pp_lst[k]] = True; nvis += 1
                s2 = arr_s[c]
                if not visited[s2]:
                    visited[s2] = True; nvis += 1
                if c == oe[q]:
                    break
                c = nxt[c]
        cur_trip = trip[oe[0]]; cur = arr_s[oe[0]]; t = a
        leg += 1
        if pos < n:
            pos += 1
    if leg < MAXL:   # final state, for callers that add a last leg (e.g. a fixed finish)
        cp_cur[leg] = cur; cp_t[leg] = t; cp_trip[leg] = cur_trip
    gen_box[0] = gen; nlegs_box[0] = leg
    return t, first_dep, nvis



class FastX(Fast):
    def __init__(self, path="model"):
        super().__init__(path)
        p = np.load(path + "_pass.npz"); self.pp = (p["ptr"].astype(np.int64), p["lst"].astype(np.int64))
        self.express = True

    def _full(self, order, t0, b):
        return replay_cpx(order, t0, 0, *self.pp, *self.tt, *self.ws, self.gen, *b)


def recordx(F, order, t0):
    """Python mirror of replay_cpx returning ride legs (board, exit, walk-from)."""
    dep_t, arr_t, dep_s, arr_s, trip, nxt, chg, fp_ptr, fp_to, fp_t = F.tt; n = F.n; pp_ptr, pp_lst = F.pp
    ob = np.zeros(64, np.int64); oe = np.zeros(64, np.int64); ow = np.zeros(64, np.int64)
    visited = np.zeros(n, bool); cur = int(order[0]); t = t0; cur_trip = -1; first = -1; pos = 1; legs = []
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
        a, mm = _legx(cur, t, cur_trip, tgt, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
                      *F.ws, gen, ob, oe, ow)
        if a >= INF: return None
        for q in range(mm - 1, -1, -1):
            c = int(ob[q])
            if first < 0: first = int(dep_t[c])
            visited[dep_s[c]] = True
            while True:
                visited[pp_lst[pp_ptr[c]:pp_ptr[c + 1]]] = True
                visited[arr_s[c]] = True
                if c == oe[q]: break
                c = int(nxt[c])
            legs.append((int(ob[q]), int(oe[q]), int(ow[q])))
        cur_trip = int(trip[oe[0]]); cur = int(arr_s[oe[0]]); t = int(a)
        if pos < n: pos += 1
    F.gen[0] = gen
    return t, first, int(visited.sum()), legs
