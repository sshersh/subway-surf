"""Calibrate the robust planner's boarding-loss table on real train movements.

For a sample of scheduled boardings (line L from station A at scheduled time d, riding to station B,
scheduled arrival a), and a rider ready at A at d - s (s = planned slack), find the real arrival at B on
the first real train of line L leaving A at or after d - s that reaches B. The loss is
    real arrival - scheduled arrival
(negative when an earlier real train gets there sooner). The expected loss by slack, headway to the next
scheduled equivalent train, and day/night is written to solver/loss_table.json for solver/robust.py.

    python3 headways/calibrate.py --model <model prefix> --data <subwaydatanyc dir> [--n 40000]
"""
import argparse, json, os, sys, collections
from datetime import date
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "solver"))
import adaptive as A
import realistic as R

SLACK = [0, 30, 60, 90, 120, 180, 240, 300, 420, 600, 900]
HW = [0, 300, 450, 600, 900, 1500, 99999]     # headway buckets (s): <5, 5-7.5, 7.5-10, 10-15, 15-25, 25+ min


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--n", type=int, default=40000); ap.add_argument("--out", default=os.path.join(HERE, "..", "solver", "loss_table.json"))
    a = ap.parse_args()
    P = A.Planner(a.model, express=True); hp = A.hop_table(P)
    dep_t, arr_t, dep_s, arr_s, trip, nxt = P.tt[:6]; hw = P.rob[1]
    T = P.meta["T"]; rt = P.meta["trip_route"]
    rng = np.random.default_rng(1)
    days = [("2026-10-07", "2026-10-08", 0), ("2026-10-08", "2026-10-07", 86400)]
    acc = collections.defaultdict(list); samples = []
    for d, nd, sh in days:
        f = [A.day_files(a.data, d) + (0,), A.day_files(a.data, nd) + (sh,)]
        net = A.Real(P, hp, f, date.fromisoformat(d))
        nreal = net.nreal   # only real movements count, not timetable trips filling feed holes
        # sample scheduled boardings on the run day 05:00-29:00 (first service day only)
        cand = np.nonzero((dep_t >= 5 * 3600) & (dep_t < 29 * 3600) & (trip < T))[0]
        pick = rng.choice(cand, size=a.n, replace=False)
        for c in pick:
            c = int(c)
            # ride 1-8 hops on this trip
            k = int(rng.integers(1, 9)); e = c
            for _ in range(k - 1):
                if nxt[e] < 0: break
                e = int(nxt[e])
            sb, se, d0, a0 = int(dep_s[c]), int(arr_s[e]), int(dep_t[c]), int(arr_t[e])
            line = A.base(rt[int(trip[c]) % T]); rc = net.rcode.get(line)
            if rc is None: continue
            if any((rc, (d0 + dt) // 1800) in net.holes for dt in (-1800, 0, 1800, 3600)): continue   # feed hole nearby
            h = int(max(hw[c], hw[e])); night = R.is_night(d0)
            idx = net.at[sb]
            for s in SLACK:
                t = d0 - s
                i0 = int(np.searchsorted(net.dep_t[idx], t)); best = None
                for x in idx[i0:i0 + 300]:
                    x = int(x); dd = int(net.dep_t[x])
                    if best is not None and dd >= best: break
                    if dd > t + 3 * 3600: break
                    if net.route[x] != rc or net.trip[x] >= nreal: continue
                    y = x; hops = 0
                    while y >= 0 and hops < 60:
                        if net.arr_s[y] == se:
                            if best is None or net.arr_t[y] < best: best = int(net.arr_t[y])
                            break
                        y = int(net.nxt[y]); hops += 1
                if best is None: continue
                hb = int(np.searchsorted(HW, h, side="right")) - 1
                acc[(s, hb, int(night))].append(best - a0)
                samples.append((line, int(night), s, hb, best - a0))
        print(d, "done", flush=True)
    table = {}
    for (s, hb, nt), v in sorted(acc.items()):
        v = np.array(v)
        v = np.clip(v, -1800, 3600)
        table[f"{s}|{hb}|{nt}"] = {"n": int(len(v)), "mean": float(v.mean()), "p_late60": float((v > 60).mean()),
                                   "p50": float(np.median(v)), "p90": float(np.percentile(v, 90))}
    out = {"slack": SLACK, "hw": HW, "table": table,
           "note": "loss = real arrival at the alighting stop - scheduled arrival, rider ready `slack` s before the "
                   "scheduled departure, first real train of the same line that gets there; sampled scheduled "
                   "boardings 05:00-29:00 on 2026-10-07 and 2026-10-08 (subwaydata.nyc). Clipped to [-30, +60] min."}
    # per-line adjustment: mean residual against the table, by line and day/night, shrunk toward 0
    # (n / (n + 200)) so thinly sampled lines stay near the pooled value
    res = collections.defaultdict(list)
    for line, nt, s_, hb, v in samples:
        x = table.get(f"{s_}|{hb}|{nt}")
        if x: res[(line, nt)].append(min(max(v, -1800), 3600) - x["mean"])
    out["line_adj"] = {f"{l}|{nt}": round(float(np.mean(v)) * len(v) / (len(v) + 200), 1) for (l, nt), v in sorted(res.items())}
    json.dump(out, open(a.out, "w"), indent=1)
    for nt in (0, 1):
        print("line adjustment (min),", "night" if nt else "day", {k.split("|")[0]: round(v / 60, 1) for k, v in out["line_adj"].items() if k.endswith(f"|{nt}")})
    for nt in (0, 1):
        print("night" if nt else "day")
        print("slack  " + " ".join(f"{'hw<' + str(HW[i + 1] // 60) + 'm':>9s}" for i in range(len(HW) - 1)))
        for s in SLACK:
            row = []
            for hb in range(len(HW) - 1):
                x = table.get(f"{s}|{hb}|{nt}")
                row.append(f"{x['mean'] / 60:6.1f}/{x['n']:<4d}" if x and x["n"] >= 30 else "    -    ")
            print(f"{s:5d}  " + " ".join(f"{r:>9s}" for r in row))


if __name__ == "__main__":
    main()
