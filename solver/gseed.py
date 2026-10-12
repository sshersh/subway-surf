"""Line-aware seed: generalized TSP over (station, line, direction) states.

Staying on a train costs only run time; boarding costs half the daytime headway plus a change
allowance. Each station is a cluster; the GTSP picks one state per station. Solved as an ATSP via
the Noon-Bean transform with LKH (elkai)."""
import sys, json, time, collections
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import elkai
from engine import load

SRC = sys.argv[1]; OUT = sys.argv[2]
m, meta = load("model")
n = len(meta["stations"]); T = meta["T"]
trips = {t["trip_id"]: t for t in json.load(open(SRC + "/trips.json"))}
tkey = [(meta["trip_route"][i], trips[tid]["direction_id"]) for i, tid in enumerate(meta["trip_ids"])]

DAY0, DAY1 = 7 * 3600, 19 * 3600
BF = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
run = collections.defaultdict(list); run_any = collections.defaultdict(list)
deps = collections.Counter()
for d, a, s1, s2, tr in zip(m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"]):
    if tr >= T: continue
    k = tkey[tr]
    run_any[(k, s1, s2)].append(a - d)
    if DAY0 <= d <= DAY1:
        run[(k, s1, s2)].append(a - d); deps[(k, s1)] += 1

state = {}
def sn(k, s):
    if (k, s) not in state: state[(k, s)] = n + len(state)
    return state[(k, s)]
E = []
for key, v in run_any.items():
    k, s1, s2 = key
    w = float(np.median(run[key])) if key in run else float(np.median(v)) + 600  # off-peak-only edge: penalize
    E.append((sn(k, s1), sn(k, s2), w))
for (k, s), node in list(state.items()):
    c = deps[(k, s)]
    hw = (DAY1 - DAY0) / c if c else 3600
    board = 90 + min(hw * BF, 1800)
    E.append((s, node, board)); E.append((node, s, 0.0))
for s in range(n):
    for q in range(m["fp_ptr"][s], m["fp_ptr"][s + 1]):
        E.append((s, int(m["fp_to"][q]), float(m["fp_t"][q])))
N = n + len(state)
r, c, w = zip(*E)
G = csr_matrix((np.array(w) + 1e-3, (r, c)), shape=(N, N))
nodes = sorted(state.values()); key_of = {v: k for k, v in state.items()}
t = time.time()
D = dijkstra(G, directed=True, indices=nodes)[:, nodes]
print("states", len(nodes), "dijkstra s", round(time.time() - t, 1), "inf", np.isinf(D).sum(), flush=True)

# clusters
cl = collections.defaultdict(list)
for i, v in enumerate(nodes): cl[key_of[v][1]].append(i)
K = len(nodes)
succ = np.zeros(K, dtype=int); cluster = np.zeros(K, dtype=int)
for s, members in cl.items():
    for a, b in zip(members, members[1:] + members[:1]): succ[a] = b
    for a in members: cluster[a] = s
M = 100000; BIG = 10 * M
Dm = np.where(np.isinf(D), 50000, np.round(D)).astype(np.int64)
A = np.full((K + 1, K + 1), BIG, dtype=np.int64)
A[:K, :K] = Dm[succ, :] + M                       # leave via successor's cost
same = cluster[:, None] == cluster[None, :]
A[:K, :K][same] = BIG
for a in range(K):
    if succ[a] != a: A[a, succ[a]] = 0
    else: A[a, a] = 0
A[K, :K] = 0; A[:K, K] = M                          # dummy cluster: open path
np.fill_diagonal(A, 0)
t = time.time()
tour = elkai.DistanceMatrix(A.tolist()).solve_tsp(runs=int(sys.argv[3]) if len(sys.argv) > 3 else 1)
print("lkh s", round(time.time() - t, 1), flush=True)
tour = tour[:-1] if tour[0] == tour[-1] else tour
i = tour.index(K); tour = tour[i + 1:] + tour[:i]
keys = [tuple(k) for k in json.load(open("model_keys.json"))]; kid = {k: i for i, k in enumerate(keys)}
order, okey, seen = [], [], set()
prev = None
for v in tour:
    s = int(cluster[v])
    if s not in seen:
        seen.add(s); order.append(s); okey.append(kid[key_of[nodes[v]][0]])
# contiguity check and static cost along entry states
runs_ = sum(1 for a, b in zip(tour, tour[1:]) if cluster[a] != cluster[b])
print("clusters", len(order), "of", n, "cluster switches", runs_)
entry = []; prev = None
for v in tour:
    if prev is None or cluster[v] != cluster[prev]: entry.append(v)
    prev = v
cost = sum(D[succ_prev, b] for succ_prev, b in zip(entry, entry[1:]))
print("static line-aware cost h", round(cost / 3600, 2))
np.save(OUT + "_gseed.npy", np.array([order, okey]))
