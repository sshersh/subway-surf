"""Static seed: shortest ride/walk times between all stations, then an open-path TSP via LKH."""
import sys, collections
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import elkai
from engine import load

BOARD = 300  # s, average wait + change when switching lines mid-leg


def matrix(path):
    m, meta = load(path)
    n = len(meta["stations"]); routes = meta["trip_route"]; T = meta["T"]
    run = collections.defaultdict(list)
    for d, a, s1, s2, tr in zip(m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"]):
        if tr < T and 6 * 3600 <= d <= 20 * 3600:
            run[(routes[tr], s1, s2)].append(a - d)
    # node ids: origin O_s = s, street S_s = n + s, route nodes after
    rnode = {}
    def rn(r, s):
        k = (r, s)
        if k not in rnode: rnode[k] = 2 * n + len(rnode)
        return rnode[k]
    E = []
    for (r, s1, s2), v in run.items():
        E.append((rn(r, s1), rn(r, s2), float(np.median(v))))
    for (r, s) in list(rnode):
        E.append((s, rnode[(r, s)], 0.0))           # origin: already on any line
        E.append((n + s, rnode[(r, s)], BOARD))       # street -> board
        E.append((rnode[(r, s)], n + s, 0.0))         # alight
    for s in range(n):
        E.append((s, n + s, 0.0))
        for k in range(m["fp_ptr"][s], m["fp_ptr"][s + 1]):
            E.append((n + s, n + int(m["fp_to"][k]), float(m["fp_t"][k])))
    N = 2 * n + len(rnode)
    r, c, w = zip(*E)
    G = csr_matrix((np.array(w) + 1e-3, (r, c)), shape=(N, N))
    D = dijkstra(G, directed=True, indices=list(range(n)))[:, n:2 * n]
    return D


def tsp(D, seed_runs=1):
    n = len(D)
    M = np.zeros((n + 1, n + 1))
    M[:n, :n] = D
    M = np.round(M).astype(int).tolist()   # node n is a dummy: free start and end => open path
    best = None
    for _ in range(seed_runs):
        tour = elkai.DistanceMatrix(M).solve_tsp(runs=10)
        tour = tour[:-1] if tour[0] == tour[-1] else tour
        i = tour.index(n); path = tour[i + 1:] + tour[:i]
        cost = sum(D[a][b] for a, b in zip(path, path[1:]))
        if best is None or cost < best[0]:
            best = (cost, path)
    return best


if __name__ == "__main__":
    D = matrix(sys.argv[1])
    np.save(sys.argv[2] + "_D.npy", D)
    cost, path = tsp(D)
    print("static open-path cost h", cost / 3600, "len", len(path))
    np.save(sys.argv[2] + "_seed.npy", np.array(path))
    # also the reverse direction
    np.save(sys.argv[2] + "_seed_rev.npy", np.array(path[::-1]))
