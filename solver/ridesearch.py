"""Ride-level search: anneal a route as a list of rides instead of a station order.

    python3 ridesearch.py <route.json> <out.json> [--minutes M] [--seed S] [--thi T] [--tlo T] [--express]

Run from the model directory the route was solved on (cwd holds model.json/.npz; model_pass.npz
for --express). The route JSON needs "rides" ([line, board, alight, dep, arr]), as export.py and
tidy.py write.

The order-based annealer (anneal.py) moves stations in a priority list; a replay turns the list into
rides, so whole pieces of the day (a branch done out and back, a line ridden the other way, a leg
done in the afternoon instead of the morning) are out of reach of single moves. Here the state is
the rides themselves, (line, board, alight), and moves act on them:

  move     a block of 1-8 consecutive rides to another point in the day
  flip     a block ridden the other way: rides in reverse order, each from its alighting station
           back to its boarding station on the same line
  swap     two blocks
  reverse  one ride's direction
  drop     a ride (kept only if every station is still visited)
  merge    two consecutive rides on the same line into one (b of the first -> e of the second)
  start    shift the start time by up to +-30 min

A replay takes, for each ride, the first train of its line from the boarding station that gets to
the alighting station (staying on the same train when it can). Between rides that don't meet it
walks when a street link exists, else takes the fastest trains there (any line); those connecting
trains count for coverage too. A state is valid if every station is visited; its cost is the time
the last new station is reached minus the first departure. Rides after that are dropped.

Writes the best route (export.py format, with "rides") to out.json.
"""
import sys, json, bisect, collections, math, random, time
import numpy as np
from engine import _leg, INF

args = sys.argv[1:]
def opt(name, default, cast=str):
    if name in args:
        i = args.index(name); v = cast(args[i + 1]); del args[i:i + 2]; return v
    return default
EXPRESS = "--express" in args
if EXPRESS: args.remove("--express")
MINUTES = opt("--minutes", 20.0, float); SEED = opt("--seed", 0, int)
T_HI = opt("--thi", 120.0, float); T_LO = opt("--tlo", 5.0, float)
SRC, OUT = args[0], args[1]

meta = json.load(open("model.json")); m = np.load("model.npz")
st = meta["stations"]; names = meta["names"]; T = meta["T"]; trip_route = meta["trip_route"]
sid = {s: i for i, s in enumerate(st)}; n = len(st)
dep_t, arr_t, dep_s, arr_s, trip, nxt, chg = (m[k] for k in ("dep_t", "arr_t", "dep_s", "arr_s", "trip", "nxt", "chg"))
fp_ptr, fp_to, fp_t = m["fp_ptr"], m["fp_to"], m["fp_t"]
if EXPRESS:
    P = np.load("model_pass.npz"); pptr, plst = P["ptr"], P["lst"]
base = lambda r: r[:-1] if len(r) == 2 and r.endswith("X") else r
line_of = lambda c: base(trip_route[int(trip[c]) % T])

bys = collections.defaultdict(list)
for c in np.argsort(dep_t, kind="stable"):
    bys[int(dep_s[c])].append(int(c))
byt = {s: np.array([int(dep_t[c]) for c in v]) for s, v in bys.items()}
bys = {s: np.array(v) for s, v in bys.items()}
foot = {}
for a in range(n):
    for k in range(fp_ptr[a], fp_ptr[a + 1]):
        foot[(a, int(fp_to[k]))] = int(fp_t[k])
nt = int(trip.max()) + 1
ws = [np.zeros(n, np.int64) for _ in range(7)] + [np.zeros(nt, np.int64), np.zeros(nt, np.int64)]
ob, oe, ow = (np.zeros(64, np.int64) for _ in range(3))
GEN = [0]


def cover(c, seen, when, tt):
    for s in (int(dep_s[c]), int(arr_s[c])):
        if s not in seen: seen.add(s); when.append(tt if s == int(dep_s[c]) else int(arr_t[c]))
    if EXPRESS:
        for x in plst[pptr[c]:pptr[c + 1]]:
            x = int(x)
            if x not in seen: seen.add(x); when.append(int(dep_t[c]))


_ride_cache = {}
def ride(line, b, e, ready, cur_trip):
    """first train of `line` from b reaching e, boarding at/after ready (or staying on cur_trip)."""
    key = (line, b, e, ready, cur_trip)
    if key in _ride_cache: return _ride_cache[key]
    res = None
    if b in bys:
        lst, tl = bys[b], byt[b]
        i = int(np.searchsorted(tl, ready - 7200 if cur_trip >= 0 else ready))
        lim = ready + 4 * 3600
        for c in lst[i:]:
            c = int(c)
            if dep_t[c] > lim: break
            if dep_t[c] < ready and int(trip[c]) != cur_trip: continue
            if line_of(c) != line: continue
            chain = []; k = c
            while k >= 0 and len(chain) < 150:
                chain.append(k)
                if arr_s[k] == e:
                    res = (int(arr_t[k]), int(trip[k]), chain); break
                k = int(nxt[k])
            if res: break
    if len(_ride_cache) > 2_000_000: _ride_cache.clear()
    _ride_cache[key] = res
    return res


def path(here, t, cur_trip, e):
    """fastest way (any trains, walks) from here to arriving at e by train"""
    GEN[0] += 1
    a, k = _leg(here, t, cur_trip, e, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t, *ws, GEN[0], ob, oe, ow)
    if a >= INF: return None
    chains = []
    for q in range(k - 1, -1, -1):
        b, x = int(ob[q]), int(oe[q]); ch = [b]
        while ch[-1] != x: ch.append(int(nxt[ch[-1]]))
        chains.append(ch)
    return int(a), int(trip[oe[0]]), chains


PEN_MISS, PEN_SKIP = 1800, 900
PROGRESS = opt("--progress", 0.05, float)   # search cost of a station not visited / a ride whose line doesn't run then


def replay(rides, t0, detail=False):
    """rides: [(line, b, e)]. Returns (cost, finish, start, used, missing, skipped) or None.
    Rides that can't be made (no train of that line then) are skipped and a station left unvisited costs
    PEN_MISS, so the search can pass through incomplete states; only complete ones count as results."""
    here, t, ct = rides[0][1], t0, -1
    seen = {here}; when = [t0]; used = []; start = None; skipped = 0; last = len(rides)
    for idx, (line, b, e) in enumerate(rides):
        if here != b:
            w = foot.get((here, b))
            p = path(here, t, ct, b) if (w is None or w > 600) else None
            if w is None and p is None: return None
            if p is not None and (w is None or p[0] < t + w):
                t, ct, chains = p
                for ch in chains:
                    if start is None: start = int(dep_t[ch[0]])
                    for c in ch: cover(c, seen, when, int(dep_t[ch[0]]))
                    if detail: used.append((line_of(ch[0]), int(dep_s[ch[0]]), int(arr_s[ch[-1]]), ch))
            else:
                t += w; ct = -1
            here = b
        ready = t + (int(chg[b]) if ct >= 0 else 0)
        r = ride(line, b, e, ready, ct)
        if r is None:
            skipped += 1; continue
        a, ct, ch = r
        if start is None: start = int(dep_t[ch[0]])
        for c in ch: cover(c, seen, when, int(dep_t[ch[0]]))
        if detail: used.append((line, b, e, ch))
        t = a; here = e
        if len(seen) >= n: last = idx + 1; break
    if start is None: return None
    fin = max(when); missing = n - len(seen)
    # the finish alone is flat: an earlier leg that gains time usually just waits longer for the same later
    # train. A small weight on how early stations are reached on average rewards progress, so the search can
    # build up slack until a later leg catches an earlier train.
    prog = PROGRESS * (sum(when) / len(when) - start)
    return fin - start + prog + PEN_MISS * missing + PEN_SKIP * skipped, fin, start, used, missing, skipped, last


# rides to insert: the route's own, and every line's regular end-to-end patterns
heads = set(range(len(dep_t))) - set(int(x) for x in nxt if x >= 0)
pat = collections.Counter()
for c in heads:
    if int(trip[c]) >= T: continue
    k = c
    while int(nxt[k]) >= 0: k = int(nxt[k])
    pat[(line_of(c), int(dep_s[c]), int(arr_s[k]))] += 1
POOL = [p for p, cnt in pat.items() if cnt >= 5]
MOVES = ["move", "flip", "swap", "reverse", "drop", "merge", "insert", "start"]


def neighbour(rides, t0, rng):
    R = list(rides); L = len(R); nt0 = t0
    r = rng.random()
    if r < 0.27:       # move a block
        k = rng.randint(1, min(8, L - 1)); i = rng.randrange(0, L - k + 1); blk = R[i:i + k]; rest = R[:i] + R[i + k:]
        j = rng.randrange(0, len(rest) + 1); R = rest[:j] + blk + rest[j:]
    elif r < 0.45:     # flip a block: other order, other direction
        k = rng.randint(1, min(8, L)); i = rng.randrange(0, L - k + 1)
        R[i:i + k] = [(ln, e, b) for ln, b, e in reversed(R[i:i + k])]
    elif r < 0.58:     # swap two blocks
        k = rng.randint(1, min(4, L // 2)); i = rng.randrange(0, L - 2 * k + 1); j = rng.randrange(i + k, L - k + 1)
        R = R[:i] + R[j:j + k] + R[i + k:j] + R[i:i + k] + R[j + k:]
    elif r < 0.66:     # reverse one ride
        i = rng.randrange(L); ln, b, e = R[i]; R[i] = (ln, e, b)
    elif r < 0.76:     # drop a ride
        if L < 3: return None
        del R[rng.randrange(L)]
    elif r < 0.84:     # merge two consecutive rides on one line
        cand = [i for i in range(L - 1) if R[i][0] == R[i + 1][0] and R[i][2] == R[i + 1][1]]
        if not cand: return None
        i = rng.choice(cand); R[i:i + 2] = [(R[i][0], R[i][1], R[i + 1][2])]
    elif r < 0.96:     # insert a ride from the pool (a line end to end, or one of the route's own rides)
        src = POOL if rng.random() < 0.5 else rides
        R.insert(rng.randrange(L + 1), src[rng.randrange(len(src))])
    else:              # start time
        nt0 = t0 + rng.randint(-1800, 1800)
    return R, nt0


route = json.load(open(SRC))
rides = [(base(x[0]), sid[x[1]], sid[x[2]]) for x in route["rides"] if x[1] in sid and x[2] in sid]
t0 = int(route["rides"][0][3]) - 60
first = replay(rides, t0)
if first is None or first[4] or first[5]: raise SystemExit("the route's rides don't replay completely on this model")
cur = best = first[0]; cur_r = best_r = rides; cur_t0 = best_t0 = t0
print(f"start {cur/3600:.3f} h, {len(rides)} rides", flush=True)
rng = random.Random(SEED); t_end = time.time() + MINUTES * 60; t_start = time.time(); it = 0; acc = 0
while True:
    now = time.time()
    if now > t_end: break
    frac = (now - t_start) / (MINUTES * 60); Tm = T_HI * (T_LO / T_HI) ** frac
    nb = neighbour(cur_r, cur_t0, rng); it += 1
    if nb is None: continue
    R, nt0 = nb
    res = replay(R, nt0)
    if res is None: continue
    c = res[0]
    if c <= cur or rng.random() < math.exp((cur - c) / Tm):
        cur, cur_r, cur_t0 = c, R[:res[6]], nt0; acc += 1   # rides after the last new station are dropped
        if c < best and res[4] == 0 and res[5] == 0:
            best, best_r, best_t0 = c, cur_r, nt0
            print(f"{(now - t_start)/60:5.1f} min it {it}: best plan {(res[1]-res[2])/3600:.3f} h, objective {best/3600:.3f} ({len(best_r)} rides)", flush=True)
    if it % 20000 == 0:
        print(f"{(now - t_start)/60:5.1f} min it {it} acc {acc} T {Tm:.0f} cur {cur/3600:.3f} best {best/3600:.3f}", flush=True)

# write out
cost, fin, s0, used, _, _, _ = replay(best_r, best_t0, detail=True)
hms = lambda s: f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"
rows = []; itin = []; seen = set(); prev_e = None; prev_a = None; walk_s = 0; out_rides = []
for line, b, e, ch in used:
    d, a = int(dep_t[ch[0]]), int(arr_t[ch[-1]])
    if prev_e is None:
        rows.append({"stop_id": st[b], "time": hms(d), "route": ""}); seen.add(b)
    elif b != prev_e:
        w = foot.get((prev_e, b), 0); walk_s += w
        itin.append({"kind": "walk", "from": names[prev_e], "to": names[b], "t0": hms(prev_a), "t1": hms(prev_a + w), "min": round(w / 60)})
        rows.append({"stop_id": st[b], "time": hms(prev_a + w), "route": ""})
    rl = trip_route[int(trip[ch[0]]) % T]; new0 = len(seen)
    for c in ch:
        if EXPRESS:
            for x in plst[pptr[c]:pptr[c + 1]]:
                rows.append({"stop_id": st[int(x)], "time": hms(int(dep_t[c])), "route": rl, "pass": True}); seen.add(int(x))
        rows.append({"stop_id": st[int(arr_s[c])], "time": hms(int(arr_t[c])), "route": rl}); seen.add(int(arr_s[c]))
    itin.append({"kind": "ride", "route": rl, "from": names[b], "to": names[e], "t0": hms(d), "t1": hms(a), "stops": len(ch), "new": len(seen) - new0})
    out_rides.append([rl, st[b], st[e], d, a]); prev_e = e; prev_a = a
    if len(seen) >= n: break
stats = dict(route.get("stats", {}))
stats.update({"total_s": fin - s0, "start": hms(s0), "end": hms(fin), "rides": len(out_rides), "walks": sum(1 for x in itin if x["kind"] == "walk"),
              "walk_s": walk_s, "start_station": names[sid[out_rides[0][1]]], "end_station": names[sid[out_rides[-1][2]]], "ride_search": True})
order = list(dict.fromkeys([sid[r[1]] for r in out_rides[:1]] + [sid[r[2]] for r in out_rides])); order += [i for i in range(n) if i not in set(order)]
json.dump({"rows": rows, "itin": itin, "stats": stats, "order": [st[i] for i in order], "t0": best_t0, "rides": out_rides}, open(OUT, "w"))
print(f"done it {it}: plan {(first[1]-first[2])/3600:.3f} -> {(fin - s0)/3600:.3f} h ({((first[1]-first[2]) - (fin - s0))/60:.1f} min), {len(out_rides)} rides", flush=True)
