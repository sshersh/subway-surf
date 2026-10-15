"""Express-rules leg search (see expr.py), in its own module so fast.py can use it too."""
import numpy as np
from numba import njit
from engine import INF


@njit(cache=True)
def _legx(src, t, cur_trip, target, pp_ptr, pp_lst, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t,
         ar, ready, kind, jin, jout, jfp, stamp, tb, tbstamp, gen, out_b, out_e, out_w):
    """Earliest time a train you ride stops at OR passes through target (ends at that hop's arrival). Fills out_b/out_e (ride board/exit conn) and
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
            if a < best_t:
                hit = s2 == target
                if not hit:
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
