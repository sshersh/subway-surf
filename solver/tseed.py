"""Line-aware seed: generalized TSP over (station, line, direction) states.

With --times (a JSON {station_index: seconds into the service day}, e.g. from a previous solution)
the costs become time-of-day aware: each boarding costs the change time plus half the gap between
trains on that line at that station around the hour the plan expects to be there (or the wait for
the next train if none run then), and each ride segment uses run times from that hour. Segments a
line only serves at other hours (an express making local stops at night) are penalized then.

Staying on a train costs only run time; boarding costs half the daytime headway plus a change
allowance. Each station is a cluster; the GTSP picks one state per station. Solved as an ATSP via
the Noon-Bean transform with LKH (elkai)."""
import sys, json, time, collections
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
import elkai
from engine import load

TIMES = None
if "--times" in sys.argv:
    i = sys.argv.index("--times"); TIMES = {int(k): v for k, v in json.load(open(sys.argv[i + 1])).items()}
    del sys.argv[i:i + 2]
WIN = 45 * 60   # +/- window around the expected time
SRC = sys.argv[1]; OUT = sys.argv[2]
m, meta = load("model")
n = len(meta["stations"]); T = meta["T"]
trips = {t["trip_id"]: t for t in json.load(open(SRC + "/trips.json"))}
tkey = [(meta["trip_route"][i], trips[tid]["direction_id"]) for i, tid in enumerate(meta["trip_ids"])]

DAY0, DAY1 = 7 * 3600, 19 * 3600
BF = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
DAY = 86400
def circ(a, b):  # circular distance in seconds of day
    d = abs((a - b) % DAY); return min(d, DAY - d)
runs = collections.defaultdict(list)       # (k, s1, s2) -> [(dep mod day, run)]
deps = collections.defaultdict(list)       # (k, s1) -> [dep mod day]
for d, a, s1, s2, tr in zip(m["dep_t"], m["arr_t"], m["dep_s"], m["arr_s"], m["trip"]):
    if tr >= T: continue
    k = tkey[tr]
    runs[(k, s1, s2)].append((int(d) % DAY, int(a - d))); deps[(k, s1)].append(int(d) % DAY)
for v in deps.values(): v.sort()
state = {}
def sn(k, s):
    if (k, s) not in state: state[(k, s)] = n + len(state)
    return state[(k, s)]
def expected(s):
    return None if TIMES is None or s not in TIMES else TIMES[s] % DAY
E = []
for (k, s1, s2), v in runs.items():
    h = expected(s1)
    if h is None:
        day = [r for d, r in v if DAY0 <= d <= DAY1]
        w = float(np.median(day)) if day else float(np.median([r for _, r in v])) + 600
    else:
        near = [r for d, r in v if circ(d, h) <= WIN]
        w = float(np.median(near)) if near else float(np.median([r for _, r in v])) + 1800
    E.append((sn(k, s1), sn(k, s2), w))
chg = m["chg"]
for (k, s), node in list(state.items()):
    dl = deps.get((k, s), [])
    h = expected(s)
    if h is None or not dl:
        c = sum(1 for d in dl if DAY0 <= d <= DAY1)
        wait = min(((DAY1 - DAY0) / c) * BF, 1800) if c else 3600
    else:
        c = sum(1 for d in dl if circ(d, h) <= WIN)
        if c >= 2: wait = min((2 * WIN / c) * BF, 2400)
        else:      # at most one train near then: wait for the next one
            nxt = min(((d - (h - WIN)) % DAY) for d in dl); wait = min(max(nxt - WIN, 0) + 600, 3 * 3600)
    E.append((s, node, float(chg[s]) + wait)); E.append((node, s, 0.0))
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
