"""Simplified, Trail-of-Bits-style planning model with time-of-day headways, solved with Christofides.

Cost of a route = ride time + transfer time + 1/2 the average headway of each line you board,
where the headway is the hourly average for that line, direction and station at the hour you'd be
there (headways.py: scheduled or observed). No timetable: this is an expected-time model.

    python3 headways/simple_model.py --model solver/model --gtfs <gtfs_json_dir> \
        [--express solver/model_pass.npz] [--undirected] [--headways observed_hourly.json] \
        [--start-hours 4 5 6 7 8] [--iters 5] --out headways/results/christofides.json
"""
import argparse, json, sys, os, time, collections
import numpy as np
import networkx as nx
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

sys.path.insert(0, os.path.dirname(__file__))
from headways import scheduled_headways, to_json, half_headway, line_of

DAY = 86400; WIN = 45 * 60


def load(model):
    z = np.load(model + ".npz"); meta = json.load(open(model + ".json"))
    return {k: z[k] for k in z.files}, meta


class Simple:
    def __init__(self, model, hw, express=None, undirected=False):
        self.m, self.meta = load(model); m, meta = self.m, self.meta
        self.n = len(meta["stations"]); self.T = meta["T"]; self.hw = hw; self.undirected = undirected
        st = meta["stations"]; self.st = st
        # direction of each trip from its id (NYCT trip ids carry ..N / ..S)
        tdir = [("N" if "..N" in t else "S") for t in meta["trip_ids"]]
        self.tkey = [(meta["trip_route"][i], "*" if undirected else tdir[i]) for i in range(self.T)]
        self.runs = collections.defaultdict(list); self.deps = collections.defaultdict(list)
        for d, a, s1, s2, tr in zip(m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"]):
            if tr >= self.T: continue
            k = self.tkey[tr]
            self.runs[(k, int(s1), int(s2))].append((int(d) % DAY, int(a - d)))
        self.passes = {}
        if express:
            p = np.load(express); pp, pl = p["ptr"], p["lst"]
            pc = collections.defaultdict(collections.Counter)
            for c in np.nonzero(np.diff(pp))[0]:
                tr = int(m["trip"][c])
                if tr < self.T:
                    pc[(self.tkey[tr], int(m["dep_s"][c]), int(m["arr_s"][c]))][tuple(int(x) for x in pl[pp[c]:pp[c + 1]])] += 1
            self.passes = {k: list(v.most_common(1)[0][0]) for k, v in pc.items()}

    def half_hw(self, k, s, hour):
        line = line_of(k[0])
        if k[1] == "*":
            return (half_headway(self.hw, line, "N", self.st[s], "weekday", hour) +
                    half_headway(self.hw, line, "S", self.st[s], "weekday", hour)) / 2
        return half_headway(self.hw, line, k[1], self.st[s], "weekday", hour)

    def build(self, hours):
        """hours[s]: expected clock time (seconds of day) at station s."""
        n = self.n; state = {}
        def sn(k, s):
            if (k, s) not in state: state[(k, s)] = n + len(state)
            return state[(k, s)]
        E = []
        for (k, s1, s2), v in self.runs.items():
            h = hours[s1]
            near = [r for d, r in v if min(abs(d - h) % DAY, DAY - abs(d - h) % DAY) <= WIN]
            w = float(np.median(near)) if near else float(np.median([r for _, r in v])) + 1800
            plist = self.passes.get((k, s1, s2))
            chain = [sn(k, s1)] + ([sn((k[0], k[1], "pass"), p) for p in plist] if plist else []) + [sn(k, s2)]
            for u, x in zip(chain, chain[1:]):
                E.append((u, x, w / (len(chain) - 1)))
                if self.undirected: E.append((x, u, w / (len(chain) - 1)))
        chg = self.m["chg"]
        for (k, s), node in list(state.items()):
            if len(k) == 3: continue                      # pass-through: no boarding
            board = float(chg[s]) + 60 * self.half_hw(k, s, int(hours[s] // 3600) % 24)
            E.append((s, node, board)); E.append((node, s, 0.0))
        fp_ptr, fp_to, fp_t = self.m["fp_ptr"], self.m["fp_to"], self.m["fp_t"]
        for s in range(n):
            for q in range(fp_ptr[s], fp_ptr[s + 1]): E.append((s, int(fp_to[q]), float(fp_t[q])))
        N = n + len(state)
        best = {}
        for u, x, wt in E:   # keep the cheapest of any parallel edges (csr_matrix would sum them)
            if wt < best.get((u, x), 1e18): best[(u, x)] = wt
        r, c = zip(*best); w = list(best.values())
        G = csr_matrix((np.array(w) + 1e-3, (r, c)), shape=(N, N))
        nodes = sorted(state.values()); key = {v: k for k, v in state.items()}
        Ds = dijkstra(G, directed=True, indices=nodes)[:, nodes]          # state -> state, already riding
        cl = np.array([key[v][1] for v in nodes])
        return Ds, cl

    @staticmethod
    def station_matrix(Ds, cl, n):
        D = np.full((n, n), np.inf)
        for s in range(n):
            rs = np.where(cl == s)[0]; best_from = Ds[rs].min(axis=0)
            np.minimum.at(D[s], cl, best_from)
        np.fill_diagonal(D, 0); return D

    @staticmethod
    def expected(order, Ds, cl):
        """Expected time along a station order, tracking which train you're on (Viterbi over states).
        Returns total seconds and the expected arrival offset at each station in the order."""
        idx = {s: np.where(cl == s)[0] for s in set(order)}
        acc = np.zeros(len(idx[order[0]])); prev = idx[order[0]]; t = [0.0]
        for s in order[1:]:
            cur = idx[s]; cost = acc[:, None] + Ds[np.ix_(prev, cur)]
            acc = cost.min(axis=0); prev = cur; t.append(float(acc.min()))
        return float(acc.min()), t


def christofides_path(D):
    n = len(D); S = (D + D.T) / 2; S[~np.isfinite(S)] = 1e7
    G = nx.Graph(); G.add_weighted_edges_from((i, j, float(S[i, j])) for i in range(n) for j in range(i + 1, n))
    cyc = nx.approximation.christofides(G, weight="weight")[:-1]
    k = max(range(len(cyc)), key=lambda i: S[cyc[i]][cyc[(i + 1) % len(cyc)]])   # open the loop at its longest leg
    return cyc[k + 1:] + cyc[:k + 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="solver/model"); ap.add_argument("--gtfs", required=True)
    ap.add_argument("--express"); ap.add_argument("--undirected", action="store_true")
    ap.add_argument("--headways"); ap.add_argument("--start-hours", type=float, nargs="+", default=[4, 5, 6, 7, 8])
    ap.add_argument("--iters", type=int, default=5); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    hw = json.load(open(a.headways)) if a.headways else to_json(scheduled_headways(a.gtfs, "weekday"))
    M = Simple(a.model, hw, a.express, a.undirected); n = M.n
    best = None; log = []
    for h0 in a.start_hours:
        hours = np.full(n, h0 * 3600.0)
        order = None
        for it in range(a.iters):
            t = time.time(); Ds, cl = M.build(hours); D = M.station_matrix(Ds, cl, n)
            cand = christofides_path(D)
            # Christofides gives a loop opened at its longest leg; try both directions
            evals = [(M.expected(o, Ds, cl), o) for o in (cand, cand[::-1])]
            (tot, ts), o = min(evals, key=lambda x: x[0][0])
            if order is None or tot < best_iter[0]: best_iter = (tot, o, ts)
            order = o
            hours = np.zeros(n)
            for s, dt in zip(o, ts): hours[s] = (h0 * 3600 + dt) % DAY
            log.append({"start_hour": h0, "iter": it, "expected_h": round(tot / 3600, 3), "secs": round(time.time() - t, 1)})
            print(f"start {h0:4.1f}h iter {it}: expected {tot/3600:6.2f} h ({time.time()-t:.1f}s)", flush=True)
        if best is None or best_iter[0] < best[0]: best = best_iter + (h0,)
    tot, order, ts, h0 = best
    json.dump({"expected_s": int(tot), "start_hour": h0, "order": [int(s) for s in order],
               "stations": [M.st[s] for s in order], "offsets_s": [int(x) for x in ts],
               "settings": {"express": bool(a.express), "undirected": a.undirected,
                            "headways": a.headways or "scheduled (static GTFS)"}, "log": log},
              open(a.out, "w"), indent=1)
    print(f"best expected {tot/3600:.2f} h starting {h0}h -> {a.out}")


if __name__ == "__main__":
    main()
