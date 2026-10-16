"""Adaptive real-day evaluation: ride a planned route on a day of actual train movements, re-planning
the rest of the route from wherever the rider really is whenever reality departs from the plan.

    python3 headways/adaptive.py --model <model prefix> --data <dir with subwaydatanyc CSVs> \
        --routes label:route.json ... [--offsets -30 -20 -10 0 10 20 30] [--out results/adaptive.json]

Ground truth: actual train movements (subwaydata.nyc, MTA GTFS-realtime) for each day, plus the next
day, as connections; station change times and street walk/run times are the model's (realistic.py).
Stations count when a real train you ride stops there or (express rules) when the real hop is one
the static timetable's pass-through table credits.

Rider policy:
  1. Start with the route's own planned rides (route JSON "rides"), shifted by the start offset.
  2. Execute the next planned ride: walk/run to its boarding station when needed (realistic street
     times), then take the first real train of the planned line that gets to the planned alighting
     station, never boarding before arrival + the realistic change time (staying on the same real
     train is free). If that line has no such train within 3 h, or one leaves 10+ min after the plan
     and another way arrives 5+ min sooner, get there by the earliest real trains of any line.
  3. Re-plan when the rider arrives more than LATE s after the plan, when a ride had to be replaced, or
     when the plan runs out with stations left. The rider compares, on the static timetable, (a) keeping
     the remaining planned rides (next train of each planned line, then the station order for anything
     they miss) with (b) a fresh plan: a short local search on the remaining station order (robust
     objective, from the real position, time and visited set) replayed by the robust planner
     (solver/robust.py: realistic transfers, hard slack). The earlier projected finish wins.
  4. Done when every station served that day has been visited. A run not done 40 h after its start
     is scored 48 h.
Reports per route: median, P80, max finish, share of runs under 22:14 (the record), mean replans.

Day pairs: the CSV for day D holds trips that start on D (observed until ~05:30 the next morning). A
run that starts on D needs D+1's trips too. When D+1's file is missing, the latest available file
for another weekday is used in its place, shifted to D+1 (marked "proxy" in the output).
"""
import argparse, csv, glob, io, json, math, os, sys, collections, statistics, time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "solver"))
from robust import FastR, record, _legr, MAXL
import realistic as R_
from engine import INF

ET = ZoneInfo("America/New_York")
RECORD = 22 * 3600 + 14 * 60
LATE = 180
EARLY = 5 * 3600   # real data before this time on the run day is incomplete; the timetable stands in
CAP = 40 * 3600
FORCE = "--force-replan" in sys.argv
LS_MOVES = int(os.environ.get("LS_MOVES", 800)); LS_H = int(os.environ.get("LS_H", 80))   # rider's re-plan search   # diagnostic: re-plan after every ride     # a run still going after 40 h is scored as failed (48 h)
base = lambda r: r[:-1] if len(r) == 2 and r.endswith("X") else r


# --------------------------------------------------------------------------------------------- data
class Real:
    """Actual connections for one run day (and the next), in the static model's station numbering."""
    def __init__(self, F, hop_pass, files, day, static=False):
        sid = {s: i for i, s in enumerate(F.meta["stations"])}; n = F.n
        mid = datetime(day.year, day.month, day.day, tzinfo=ET).timestamp()
        conns = []; tix = 0; self.rcode = {}
        for trips_csv, st_csv, shift in files:
            route = {}
            for t in csv.DictReader(open(trips_csv)):
                if t["route_id"] and t["route_id"] not in ("SI", "SS"): route[t["trip_uid"]] = base(t["route_id"])
            seq = collections.defaultdict(list)
            for r in csv.DictReader(open(st_csv)):
                rid = route.get(r["trip_uid"])
                if rid is None or not r["marked_past"]: continue
                a = r["arrival_time"] or r["departure_time"]; d = r["departure_time"] or r["arrival_time"]
                if not a: continue
                p = r["stop_id"]; p = p[:-1] if p[-1:] in "NS" else p
                s = sid.get(p)
                if s is not None: seq[r["trip_uid"]].append((int(a) + shift - mid, int(d) + shift - mid, s))
            for uid, v in seq.items():
                v.sort(); rid = route[uid]; rc = self.rcode.setdefault(rid, len(self.rcode))
                for (a1, d1, s1), (a2, d2, s2) in zip(v, v[1:]):
                    if s1 != s2 and a2 >= d1 and a2 - d1 < 3 * 3600:
                        conns.append((int(d1), int(a2), s1, s2, tix, rc, hop_pass.get((rid, s1, s2), -1)))
                tix += 1
        # Feed holes: a line with (almost) no observed movements (<= 20%) in a 30-min window where the
        # timetable has trains is missing data, not missing service (e.g. the 42 St shuttle 17:00-18:00 on
        # 10-07). Before EARLY on the run day, real trips are in the previous service day's file, which the
        # sample doesn't have, so the whole window counts as a hole. Holes are filled with whole scheduled
        # trips (every trip whose first departure falls in a hole), and real trips starting before EARLY
        # are dropped so the two don't overlap.
        W = 1800; T = F.meta["T"]; rt = F.meta["trip_route"]
        sdep, sarr, sds, sas, strip = F.tt[0], F.tt[1], F.tt[2], F.tt[3], F.tt[4]
        trc = np.array([self.rcode.setdefault(base(rt[int(x) % T]), len(self.rcode)) for x in range(int(strip.max()) + 1)])
        srt = trc[strip]
        first_real = {}
        for c in conns: first_real[c[4]] = min(first_real.get(c[4], 1 << 40), c[0])
        conns = [c for c in conns if first_real[c[4]] >= EARLY]
        obs = collections.Counter((c[5], c[0] // W) for c in conns)
        sch = collections.Counter(zip(srt.tolist(), (sdep // W).tolist()))
        hole = {k for k, v in sch.items() if v >= 8 and obs.get(k, 0) <= 0.2 * v and k[1] * W < 54 * 3600}
        hole |= {k for k in sch if k[1] * W < EARLY}
        if static: hole = set(sch); conns = []   # validation: the timetable itself as the "real day"
        self.nreal = tix   # trip ids >= nreal are timetable trips filling feed holes
        first_s = np.full(len(trc), 1 << 40, np.int64); np.minimum.at(first_s, strip, sdep)
        take = np.array([(int(trc[x]), int(first_s[x]) // W) in hole for x in range(len(trc))])
        inv = {v: k for k, v in self.rcode.items()}
        self.holes = hole   # (route code, 30-min window) filled from the timetable
        self.filled = collections.Counter()
        for i in np.nonzero(take[strip])[0]:
            r = inv[int(srt[i])]
            conns.append((int(sdep[i]), int(sarr[i]), int(sds[i]), int(sas[i]), tix + int(strip[i]), int(srt[i]),
                          hop_pass.get((r, int(sds[i]), int(sas[i])), -1)))
            self.filled[f"{r}@{int(first_s[strip[i]]) // 3600:02d}h"] += 1
        conns.sort()
        C = np.array(conns, dtype=np.int64)
        self.dep_t, self.arr_t, self.dep_s, self.arr_s, self.trip, self.route, hop = (C[:, i].copy() for i in range(7))
        self.nxt = np.full(len(C), -1, np.int64)
        o = np.lexsort((self.dep_t, self.trip)); same = self.trip[o[:-1]] == self.trip[o[1:]]
        self.nxt[o[:-1][same]] = o[1:][same]
        oo = np.argsort(self.dep_s, kind="stable"); cut = np.searchsorted(self.dep_s[oo], np.arange(n + 1))
        self.at = [oo[cut[i]:cut[i + 1]] for i in range(n)]
        lst, ptr = [], [0]
        plists = hop_pass["_lists"]
        for h in hop:
            lst.extend(plists[h] if h >= 0 else []); ptr.append(len(lst))
        self.pp_ptr = np.array(ptr, np.int64); self.pp_lst = np.array(lst, np.int64)
        served = np.zeros(n, bool); served[self.dep_s] = True; served[self.arr_s] = True
        if len(self.pp_lst): served[self.pp_lst] = True
        self.served = served; self.ntrips = int(self.trip.max()) + 1


def hop_table(F):
    """(route, s1, s2) -> index of the most common pass-through list of that static hop."""
    T = F.meta["T"]; rt = F.meta["trip_route"]; ptr, lst = F.pp
    dep_s, arr_s, trip = F.tt[2], F.tt[3], F.tt[4]
    hp = collections.defaultdict(collections.Counter)
    for c in np.nonzero(np.diff(ptr))[0]:
        hp[(base(rt[int(trip[c]) % T]), int(dep_s[c]), int(arr_s[c]))][tuple(lst[ptr[c]:ptr[c + 1]].tolist())] += 1
    out = {"_lists": []}
    for k, v in hp.items(): out[k] = len(out["_lists"]); out["_lists"].append(list(v.most_common(1)[0][0]))
    return out


# ------------------------------------------------------------------------------------------ planner
class Planner(FastR):
    """FastR that replays an order from a given mid-route state (station, time, visited set): the
    state is written as leg 1's checkpoint and every replay resumes from leg >= 1."""
    def index(self):
        """Per-station static departures (by time) and route codes, for projecting planned rides."""
        if hasattr(self, "at"): return
        dep_s = self.tt[2]; n = self.n
        o = np.argsort(dep_s, kind="stable"); cut = np.searchsorted(dep_s[o], np.arange(n + 1))
        self.at = [o[cut[i]:cut[i + 1]] for i in range(n)]
        T = self.meta["T"]; rt = self.meta["trip_route"]
        self.rname = np.array([base(rt[int(x) % T]) for x in range(int(self.tt[4].max()) + 1)])[self.tt[4]]

    def follow(self, rides, here, t, walked, visited, fp, ctrip=-1):
        """Project the planned rides on the static timetable from this state: for each ride, the first
        train of that line from its boarding station that gets to its alighting station, never before
        ready + the robust buffer. Returns (time, station, visited) after the last ride that went
        through, and how many rides went through."""
        self.index()
        dep_t, arr_t, dep_s, arr_s, trip, nxt, chg = self.tt[:7]; buf = self.rob[0]; ptr, lst = self.pp
        vis = visited.copy(); k = 0
        for rname, sb, se, pdep, parr in rides:
            if here != sb:
                w = fp.get((here, sb))
                if w is None: break
                t += w; here = sb; walked = True; ctrip = -1
            ready = t + (0 if walked else int(chg[sb]))
            idx = self.at[sb]; best = None
            i0 = int(np.searchsorted(dep_t[idx], t))
            for c in idx[i0:i0 + 400]:
                c = int(c); d = int(dep_t[c])
                if best is not None and d >= best[0]: break
                if self.rname[c] != rname or (d < ready + int(buf[c]) and int(trip[c]) != ctrip): continue
                x = c; hops = 0
                while x >= 0 and hops < 80:
                    if arr_s[x] == se:
                        if best is None or arr_t[x] < best[0]: best = (int(arr_t[x]), c, x)
                        break
                    x = int(nxt[x]); hops += 1
            if best is None: break
            c = best[1]; vis[dep_s[c]] = True
            while True:
                if self.express: vis[lst[ptr[c]:ptr[c + 1]]] = True
                vis[arr_s[c]] = True
                if c == best[2]: break
                c = int(nxt[c])
            t, here, walked = best[0], se, False; k += 1; ctrip = int(trip[best[2]])
        return t, here, vis, k
    def set_state(self, cur, t, visited, cur_trip=-2):
        self.state = (int(cur), int(t), int(cur_trip), visited.copy())

    def _seed(self, b):
        cur, t, ct, vis = self.state
        b[0][1] = 0; b[1][1] = cur; b[2][1] = t; b[3][1] = ct; b[4][1] = t; b[5][1] = int(vis.sum())
        b[6][1, :] = vis; b[7][1] = 0

    def full(self, order, t0=0):
        b = self.bufs[self.cur]; self._seed(b)
        r = self._run(order, 0, 1, order.shape[0] + 1, b, self.bufs[1 - self.cur], self.res[1 - self.cur], self.res[self.cur])
        return self._score(r)

    def try_(self, order, t0, p, q=None):
        k = max(self.leg_for_pos(p), 1)
        src, dst = self.bufs[self.cur], self.bufs[1 - self.cur]
        for i in range(8):
            dst[i][:k + 1] = src[i][:k + 1]
        if q is None: q = order.shape[0] + 1
        r = self._run(order, 0, k, q, dst, src, self.res[self.cur], self.res[1 - self.cur])
        return self._score(r)


def local_search(P, order, rng, moves=LS_MOVES, horizon=LS_H, T=60.0):
    """Short annealing on the next `horizon` order positions (segment relocate / reverse / swap)."""
    cur = P.full(order); best, best_o = cur, order.copy(); n = len(order)
    if n < 4: return order
    H = min(horizon, n)
    for it in range(moves):
        r = rng.random()
        if r < 0.45:
            L = int(rng.integers(1, min(12, H))); i = int(rng.integers(0, H - L + 1))
            seg = order[i:i + L]
            if rng.random() < 0.3: seg = seg[::-1]
            rest = np.concatenate([order[:i], order[i + L:]]); j = int(rng.integers(0, min(len(rest), H + 20) + 1))
            o = np.concatenate([rest[:j], seg, rest[j:]]); p = min(i, j); q = max(i, j) + L
        elif r < 0.85:
            i = int(rng.integers(0, H - 1)); j = min(n, i + int(rng.integers(2, 30)))
            o = order.copy(); o[i:j] = o[i:j][::-1]; p, q = i, j
        else:
            i, j = sorted(rng.integers(0, H, 2)); o = order.copy(); o[i], o[j] = o[j], o[i]; p, q = int(i), int(j) + 1
        c = P.try_(o, 0, p, q)
        tt = T * (1 - it / moves) + 1
        if c < INF and (c <= cur or rng.random() < math.exp((cur - c) / tt)):
            P.accept(); order, cur = o, c
            if c < best: best, best_o = c, o.copy()
    return best_o


def plan_from(P, order, cur, t, visited, cur_trip, walked=False):
    """Remaining order (unvisited stations, plan order) and the plan's next ride from this state:
    the robust planner's leg to the first unvisited station in the order (what a full replay would
    do first). Returns (rem, [(board, exit, walk_from)] or None)."""
    rem = np.array([s for s in order if not visited[s] and s != cur], dtype=np.int64)
    if len(rem) == 0: return rem, [], 0
    ob = np.zeros(64, np.int64); oe = np.zeros(64, np.int64); ow = np.zeros(64, np.int64); pen = np.zeros(1)
    # the static model holds two service days; past 30:00 plan on the first day's copy of the timetable
    shift = 86400 if t >= 30 * 3600 else 0
    P.gen[0] += 1
    a, k = _legr(int(cur), int(t - shift), -1 if walked else int(cur_trip), int(rem[0]), P.express, *P.pp, *P.tt[:5], *P.tt[6:], *P.rob,
                 *P.ws, int(P.gen[0]), ob, oe, ow, pen)
    if a >= INF: return rem, None, shift
    return rem, [(int(ob[k - 1]), int(oe[k - 1]), int(ow[k - 1]))], shift


# --------------------------------------------------------------------------------------------- ride
class Rider:
    def __init__(self, P, net, express, rng, search=True):
        self.P, self.net, self.X, self.rng, self.search = P, net, express, rng, search
        n = P.n; self.n = n
        self.visited = ~net.served.copy()      # stations with no real service that day aren't required
        self.ws = (np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(n, np.int64), np.zeros(n, np.int64), np.zeros(n, np.int64),
                   np.zeros(net.ntrips, np.int64), np.zeros(net.ntrips, np.int64))
        self.gen = 0; self.first = -1; self.last_new = -1
        self.fp = {}
        m = P.m
        for a in range(n):
            for k in range(m["fp_ptr"][a], m["fp_ptr"][a + 1]): self.fp[(a, int(m["fp_to"][k]))] = int(m["fp_t"][k])
        self.rc = {r: i for r, i in net.rcode.items()}
        self.rname_of = {i: r for r, i in net.rcode.items()}
        self.last_c = -1

    def mark(self, b, e):
        net = self.net; c = b
        if self.first < 0: self.first = int(net.dep_t[b])
        def hit(s, t):
            if not self.visited[s]: self.visited[s] = True; self.last_new = max(self.last_new, t)
        hit(int(net.dep_s[c]), int(net.dep_t[c]))
        while True:
            if self.X:
                for s in net.pp_lst[net.pp_ptr[c]:net.pp_ptr[c + 1]]: hit(int(s), int(net.arr_t[c]))
            hit(int(net.arr_s[c]), int(net.arr_t[c]))
            if c == e: break
            c = int(net.nxt[c])

    def any_train(self, here, t, trip, tgt, commit=True):
        """Earliest real arrival at tgt on any trains (no buffer). Returns (arr, trip, station) or None;
        commit=False only looks (nothing is marked visited)."""
        net, m = self.net, self.P.m
        ob = np.zeros(64, np.int64); oe = np.zeros(64, np.int64); ow = np.zeros(64, np.int64); pen = np.zeros(1)
        if not hasattr(net, "_z"):
            net._z = np.zeros(len(net.dep_t), np.int64); net._f = np.zeros(len(net.dep_t))
        z, zf = net._z, net._f; rp = np.array([0.0, 1800.0, 0.0])
        lt = np.zeros((1, 2)); sl = np.array([0.0, 1.0])
        self.gen += 1
        a, k = _legr(here, t, trip, tgt, self.X, net.pp_ptr, net.pp_lst, net.dep_t, net.arr_t, net.dep_s, net.arr_s, net.trip,
                     m["chg"], m["fp_ptr"], m["fp_to"], m["fp_t"], z, z, z, lt, sl, zf, rp, *self.ws, self.gen, ob, oe, ow, pen)
        if a >= INF: return None
        if commit:
            for q in range(k - 1, -1, -1): self.mark(int(ob[q]), int(oe[q]))
            self.last_c = int(oe[0])
        return int(a), int(net.trip[oe[0]]), int(net.arr_s[oe[0]])

    def static_trip(self, here, t):
        """The static trip that stands for the real train the rider is on: same line, leaving `here`
        for the real train's next station at or after t (within 30 min). -2 if none (then the planner
        charges a change at `here`). Lets the planner and projections stay on the train for free."""
        c0 = getattr(self, "last_c", -1)
        if c0 < 0: return -2
        net, P = self.net, self.P; P.index()
        nx = int(net.nxt[c0])
        if nx < 0: return -2
        ns = int(net.arr_s[nx]); line = self.rname_of[int(net.route[c0])]
        dep_t, arr_s, trip = P.tt[0], P.tt[3], P.tt[4]
        idx = P.at[here]; i0 = int(np.searchsorted(dep_t[idx], t))
        for c in idx[i0:i0 + 300]:
            c = int(c)
            if dep_t[c] > t + 1800: break
            if arr_s[c] == ns and P.rname[c] == line: return int(trip[c])
        return -2

    def log(self, *a):
        if getattr(self, "trace", None) is not None: self.trace.append(a)

    def finish(self, order, here, t, st_trip, vis):
        """Static-timetable finish time replaying the order from this state (robust planner), or INF."""
        P = self.P
        rem = np.array([x for x in order if not vis[x] and x != here], dtype=np.int64)
        if len(rem) == 0: return t
        P.set_state(here, t, vis, st_trip)
        c = P.full(rem)
        return INF if c >= INF else int(P.res[P.cur][0])

    def proj(self, order, here, t, st_trip, plan=None, walked=False):
        """Projected finish on the static timetable from this state: ride the remaining planned rides
        (next train of each planned line), then finish the remaining order with the robust planner."""
        shift = 86400 if t >= 40 * 3600 else 0
        tt = t - shift; vis = self.visited
        if plan:
            sp = [(r, a, b, d - shift, e - shift) for r, a, b, d, e in plan]
            t1, h1, v1, k = self.P.follow(sp, here, tt, walked, vis, self.fp, st_trip)
            if k == len(sp):
                rem = np.array([x for x in order if not v1[x] and x != h1], dtype=np.int64)
                f = self.finish(rem, h1, t1, -2, v1)
                return None if f >= INF else f + shift
        f = self.finish(order, here, tt, st_trip, vis)
        return None if f >= INF else f + shift

    def charge(self, kind, line, t, F_new):
        """Attribute the change in projected finish since the last step to (kind, line, night/day)."""
        if F_new is None or self.F is None:
            self.F = F_new if F_new is not None else self.F; return
        d = F_new - self.F; self.F = F_new
        self.loss.append((kind, line, int(R_.is_night(t)), int(d), int(t)))

    def replan(self, order, plan, here, t, st_trip, walked, search):
        """A rational rider's choice after a disruption, judged on the static timetable:
          keep  - keep riding the remaining planned rides (next train of each planned line), then
                  finish whatever they miss by the station order;
          fresh - re-plan from here by the station order (with a short local search when search).
        Returns (order, rides, choice). The model holds two service days, so planning past 40:00
        uses the first day's copy shifted by 24 h."""
        P = self.P
        shift = 86400 if t >= 40 * 3600 else 0
        tt = t - shift
        rem = np.array([s for s in order if not self.visited[s] and s != here], dtype=np.int64)
        if len(rem) == 0: return rem, [], "done"
        best = (INF, None, None, "none")
        if plan:
            sp = [(r, a, b, d - shift, e - shift) for r, a, b, d, e in plan]
            t1, h1, v1, k = P.follow(sp, here, tt, walked, self.visited, self.fp, st_trip)
            # keep the rides that still work (all, or the prefix up to the first one that can't be
            # followed), then finish by the station order from there
            if k > 0:
                rem1 = np.array([x for x in rem if not v1[x] and x != h1], dtype=np.int64)
                fk = self.finish(rem1, h1, t1, -2, v1)
                if fk < best[0]: best = (fk, rem, list(plan[:k]), "keep" if k == len(sp) else "keep-prefix")
        if search:
            P.set_state(here, tt, self.visited, st_trip)
            cand = local_search(P, rem, self.rng)
        else:
            cand = rem
        f = self.finish(cand, here, tt, st_trip, self.visited)
        self.log("proj", "keep", best[0] if best[0] < INF else -1, "fresh", f if f < INF else -1)
        if f < best[0]:
            P.set_state(here, tt, self.visited, st_trip)
            r = record(P, cand, 0, (int(here), int(tt), int(st_trip), self.visited), partial=True)
            if r is not None:
                dep_t, arr_t, dep_s, arr_s, trip = P.tt[0], P.tt[1], P.tt[2], P.tt[3], P.tt[4]
                T = P.meta["T"]; rt = P.meta["trip_route"]
                rides = [(base(rt[int(trip[b]) % T]), int(dep_s[b]), int(arr_s[e]), int(dep_t[b]) + shift, int(arr_t[e]) + shift)
                         for b, e, w, *_ in r[3]]
                best = (f, cand, rides, "fresh")
        if best[1] is None:   # nothing projects to a finish: re-plan anyway (partial)
            P.set_state(here, tt, self.visited, st_trip)
            r = record(P, rem, 0, (int(here), int(tt), int(st_trip), self.visited), partial=True)
            if r is None: return rem, None, "none"
            dep_t, arr_t, dep_s, arr_s, trip = P.tt[0], P.tt[1], P.tt[2], P.tt[3], P.tt[4]
            T = P.meta["T"]; rt = P.meta["trip_route"]
            return rem, [(base(rt[int(trip[b]) % T]), int(dep_s[b]), int(arr_s[e]), int(dep_t[b]) + shift, int(arr_t[e]) + shift)
                         for b, e, w, *_ in r[3]], "partial"
        return best[1], best[2], best[3]

    def run(self, order, t0, rides):
        """rides: the route's own plan [(route, board, alight, planned dep, planned arr)] for the
        unshifted start; times move with the start offset."""
        P, net, m = self.P, self.net, self.P.m
        here, t, rtrip = int(order[0]), int(t0), -1      # rtrip: real trip being ridden, -1 at start
        replans = searches = replaced = missing = keeps = 0
        order = np.array(order, dtype=np.int64)
        plan = list(rides); walked = True; need = False
        steps = 0; wall = time.time(); last_state = None; stuck = 0
        self.loss = []
        while not self.visited.all():
            steps += 1
            if t > t0 + CAP or steps > 4000 or time.time() - wall > 1500: break
            if rtrip == -1 or walked: st_trip = -1
            else: st_trip = self.static_trip(here, t - (86400 if t >= 40 * 3600 else 0))
            if need or not plan:
                state = (here, t, int(self.visited.sum()))
                stuck = stuck + 1 if state == last_state else 0; last_state = state
                if stuck >= 3:   # re-planning makes no progress from here: give up the next station
                    left = [s_ for s_ in order if not self.visited[s_]]
                    if left: self.visited[int(left[0])] = True; missing += 1
                    stuck = 0; need = False; plan = []; continue
                order, plan, how = self.replan(order, plan, here, t, st_trip, walked, self.search and need and stuck == 0)
                self.log("replan", P.meta["names"][here], t, how, len(plan or []))
                replans += 1; searches += int(need and self.search); keeps += how == "keep"; need = False
                if not plan:   # the static plan can't finish from here: next station in the order on any trains
                    left = [s for s in order if not self.visited[s]] or list(np.nonzero(~self.visited)[0])
                    tgt = int(left[0])
                    r = self.any_train(here, t, -1 if walked else rtrip, tgt)
                    self.log("noplan", P.meta["names"][here], P.meta["names"][tgt], t, r)
                    if r is None: self.visited[tgt] = True; missing += 1; continue
                    t, rtrip, here = r; replaced += 1; walked = False; plan = []
                    continue
            rname, sb, se, pdep, parr = plan.pop(0)
            if here != sb:
                w = self.fp.get((here, sb))
                if w is not None:           # walk/run to the boarding station
                    self.log("walk", P.meta["names"][here], P.meta["names"][sb], t, w)
                    t += w; here = sb; rtrip = -2; walked = True
                else:
                    r = self.any_train(here, t, -1 if walked else rtrip, sb)
                    self.log("to-board", P.meta["names"][here], P.meta["names"][sb], t, r)
                    if r is None:
                        if not self.visited[sb]: self.visited[sb] = True; missing += 1
                        need = True; continue
                    t, rtrip, here = r; walked = False; need = True
                    continue
            ready = t + (int(m["chg"][sb]) if not walked else 0); rtrip_prev = rtrip
            rc = self.rc.get(rname, -99); idx = net.at[sb]; best = None
            i0 = int(np.searchsorted(net.dep_t[idx], t))
            for c in idx[i0:]:
                c = int(c); d = int(net.dep_t[c])
                if best is not None and d >= best[0]: break
                if d > t + 3 * 3600: break
                if net.route[c] != rc or (d < ready and int(net.trip[c]) != rtrip): continue
                x = c; hops = 0
                while x >= 0 and hops < 80:
                    if net.arr_s[x] == se:
                        if best is None or net.arr_t[x] < best[0]: best = (int(net.arr_t[x]), c, x)
                        break
                    x = int(net.nxt[x]); hops += 1
            if best and int(net.dep_t[best[1]]) > max(ready, pdep) + 600:   # planned line 10+ min late: is another way much sooner?
                alt = self.any_train(here, t, -1 if walked else rtrip, se, commit=False)
                if alt is not None and alt[0] < best[0] - 300: best = None
            if best:
                self.mark(best[1], best[2]); t, here, rtrip = best[0], se, int(net.trip[best[2]]); self.last_c = int(best[2])
                self.log("ride", rname, P.meta["names"][sb], P.meta["names"][se], int(net.dep_t[best[1]]), t, pdep, parr)
                if t - parr > LATE or FORCE: need = True
                # this boarding's new loss against the current plan: extra wait for the planned line
                # (beyond max(ready, planned departure)) and extra running time
                d_real = int(net.dep_t[best[1]])
                same = int(net.trip[best[1]]) == rtrip_prev
                wait = 0 if same else d_real - max(ready, pdep)
                run = (t - d_real) - (parr - pdep)
                self.loss.append(("wait", rname, int(R_.is_night(d_real)), int(wait), int(d_real), P.meta["names"][sb], P.meta["names"][se]))
                self.loss.append(("run", rname, int(R_.is_night(d_real)), int(run), int(d_real), P.meta["names"][sb], P.meta["names"][se]))
            else:
                r = self.any_train(here, t, -1 if walked else rtrip, se); replaced += 1
                self.log("replace", rname, P.meta["names"][sb], P.meta["names"][se], t, r)
                need = True
                if r is not None:
                    self.loss.append(("replaced", rname, int(R_.is_night(t)), int(r[0] - parr), int(t), P.meta["names"][sb], P.meta["names"][se]))
                    t, rtrip, here = r
                else:   # nothing real gets there any more (service over): leave that station out
                    if not self.visited[se]: self.visited[se] = True; missing += 1
            walked = False
        missing += int((~self.visited).sum())
        fin = int(self.last_new - self.first)
        self.steps = steps
        return {"finish_s": fin if not missing else 48 * 3600, "raw_finish_s": fin, "start": int(self.first), "replans": replans,
                "searches": searches, "kept": keeps, "replaced": replaced, "unreached": missing, "loss": self.loss}


# --------------------------------------------------------------------------------------------- main
def day_files(data, d):
    tr = glob.glob(os.path.join(data, "**", f"*{d}_trips.csv"), recursive=True)
    st = glob.glob(os.path.join(data, "**", f"*{d}_stop_times.csv"), recursive=True)
    return (tr[0], st[0]) if tr and st else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--routes", nargs="+", required=True, help="label:route.json[:weight]")
    ap.add_argument("--days", nargs="+", default=["2026-10-07", "2026-10-08"])
    ap.add_argument("--offsets", type=int, nargs="+", default=[-30, -20, -10, 0, 10, 20, 30])
    ap.add_argument("--no-search", action="store_true"); ap.add_argument("--out", default=None)
    ap.add_argument("--force-replan", action="store_true", help="diagnostic: re-plan after every ride")
    ap.add_argument("--static", action="store_true", help="validation: replay on the static timetable instead of real movements")
    a = ap.parse_args()
    probe = FastR(a.model, express=True, weight=1.0)
    hp = hop_table(probe)
    sid = {s: i for i, s in enumerate(probe.meta["stations"])}
    have = sorted(d for d in a.days if day_files(a.data, d))
    nets = {}
    for d in have:
        D = date.fromisoformat(d); nxt = (D + timedelta(days=1)).isoformat()
        files = [day_files(a.data, d) + (0,)]
        if day_files(a.data, nxt): files.append(day_files(a.data, nxt) + (0,)); proxy = None
        else:
            # stand-in for the next day: another weekday's file, shifted to D+1
            alt = [x for x in sorted(glob.glob(os.path.join(a.data, "**", "*_trips.csv"), recursive=True)) if d not in x and nxt not in x]
            if not alt: raise SystemExit(f"no data for the day after {d}")
            ad = os.path.basename(alt[-1]).split("_")[1]
            shift = int((datetime.fromisoformat(nxt).replace(tzinfo=ET) - datetime.fromisoformat(ad).replace(tzinfo=ET)).total_seconds())
            files.append(day_files(a.data, ad) + (shift,)); proxy = ad
        t = time.time(); nets[d] = (Real(probe, hp, files, D, static=a.static), proxy)
        print(f"{d}: {len(nets[d][0].dep_t):,} real connections, {int(nets[d][0].served.sum())} stations served,"
              f" feed holes filled from the timetable: {dict(nets[d][0].filled)}"
              + (f", next day = {proxy} (proxy)" if proxy else "") + f" [{time.time()-t:.0f} s]", flush=True)
    out = {}
    for spec in a.routes:
        parts = spec.split(":"); label, path = parts[0], parts[1]; w = float(parts[2]) if len(parts) > 2 else 1.0
        r = json.load(open(path)); X = r["stats"].get("rules") == "express"
        if not r.get("order") or not r.get("rides"):
            raise SystemExit(f"{path}: route has no 'order'/'rides' (re-export it with solver/export.py)")
        order = [sid[s] for s in r["order"] if s in sid]; t0 = int(r["t0"])
        rides = [(base(x[0]), sid[x[1]], sid[x[2]], int(x[3]), int(x[4])) for x in r["rides"]]
        P = Planner(a.model, express=X, weight=w)
        runs = []
        for d, (net, proxy) in nets.items():
            for off in a.offsets:
                t = time.time()
                R_ = Rider(P, net, X, np.random.default_rng(abs(hash((d, off))) % 2**32), search=not a.no_search)
                res = R_.run(order, t0 + 60 * off, [(a_, b_, c_, d_ + 60 * off, e_ + 60 * off) for a_, b_, c_, d_, e_ in rides])
                res.update(day=d, offset=off, proxy=proxy)
                runs.append(res)
                print(f"  {label} {d} {off:+d}: {res['finish_s']/3600:.2f} h  replans {res['replans']} searches {res['searches']}"
                      f" replaced {res['replaced']} [{time.time()-t:.0f} s]", flush=True)
        v = sorted(x["finish_s"] for x in runs); k = len(v)
        pct = lambda p: v[min(k - 1, int(math.ceil(p / 100 * k)) - 1)]
        out[label] = {"path": path, "plan_s": r["stats"]["total_s"], "rules": "express" if X else "local",
                      "median_s": int(statistics.median(v)), "p80_s": int(pct(80)), "max_s": int(v[-1]), "min_s": int(v[0]),
                      "under_record": round(sum(x < RECORD for x in v) / k, 3), "runs": runs}
        hm = lambda s: f"{s // 3600}:{s % 3600 // 60:02d}"
        o = out[label]
        print(f"{label}: plan {hm(o['plan_s'])} | median {hm(o['median_s'])} P80 {hm(o['p80_s'])} max {hm(o['max_s'])}"
              f" | under 22:14: {o['under_record']:.0%}", flush=True)
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
