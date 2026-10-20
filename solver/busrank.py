"""Rank scheduled-bus links between subway stations (see busdata.py).

    MERGE_472=1 python3 busrank.py <gtfs_json_root> <model_prefix> <out_dir> [--cache f.pkl] [--top N]

<gtfs_json_root> holds subway/ and bus_*/; <model_prefix> is a subway model built like the planner's
(model.py --mta-transfers --walk-max 2500) so the "existing path" uses the same walking/running links
and transfer times. Writes <out_dir>/links.json (all kept links, with their trips) and ranking.md.

For every directed station pair (A, B) and bus route+direction that has a stop within REACH of A followed
later on the same trip by a stop within REACH of B, per hour band (early 4-6, AM 6-10, midday 10-15,
PM 15-19, evening 19-23, night 23-4):
  headway   mean gap between scheduled departures at the boarding stop (None: under 2 departures, or over 90 min)
  ride      median scheduled in-vehicle time
  door      walk to the stop + half the headway + ride + walk from the stop      (expected, in minutes)
  existing  mean over 3 start times in the band of the fastest subway/walk path A -> B in the planner's model
  saving    existing - door
Reliability proxy (schedule-based; no real-time data available), R in (0, 1]:
  type        SBS 1.0 (bus lanes, off-board fare, signal priority), limited 0.92, local 0.85, express 0.9
  stops       1 - min(0.30, 0.008 x stops ridden)         dwell / bunching exposure on the ride
  regularity  1 / (1 + 0.5 x CV)                          CV of the scheduled gaps in the bands that count
  speed       0.75 .. 1.0 from the scheduled mph (5 .. 10) a slow schedule means a congested corridor
  route len   1 - min(0.20, 0.001 x stops on the pattern) long routes bunch more
Score = R x time-weighted mean over the day of max(0, saving) (bands with no service count as 0).
"""
import sys, os, json, math, pickle, statistics, collections
import numpy as np
from numba import njit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import busdata as B
from stations472 import alias

ROOT, MODEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
CACHE = sys.argv[sys.argv.index("--cache") + 1] if "--cache" in sys.argv else None
TOPN = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 300
os.makedirs(OUT, exist_ok=True)

meta = json.load(open(MODEL + ".json")); z = np.load(MODEL + ".npz")
ST = meta["stations"]; NAMES = meta["names"]; N = len(ST)
LAT, LON = z["lat"], z["lon"]
COORD = [(float(LAT[i]), float(LON[i])) for i in range(N)]
BANDS = [("early", 4, 6), ("am", 6, 10), ("midday", 10, 15), ("pm", 15, 19), ("evening", 19, 23), ("night", 23, 28)]


def band_of(sod):
    h = sod / 3600.0
    if h < 4: h += 24
    for k, (_, a, b) in enumerate(BANDS):
        if a <= h < b: return k
    return 5


# ---------------------------------------------------------------- phase 1: candidate bus segments
def extract():
    recs = collections.defaultdict(list)    # (route, dir, A, B, stopA, stopB) -> [(dep, arr, trip_id, nstops, patlen, path_m)]
    rinfo = {}
    stopxy = {}
    for fd in B.FEEDS:
        d = f"{ROOT}/{fd}"
        if not os.path.isdir(d): continue
        stops = {s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"]), s["stop_name"]) for s in json.load(open(f"{d}/stops.json"))}
        near = {}
        for sid_, (la, lo, nm) in stops.items():
            c = [(i, B.dist_m((la, lo), COORD[i])) for i in range(N) if abs(COORD[i][0] - la) < 0.0045]
            c = [(i, dd) for i, dd in c if dd <= B.REACH]
            if c: near[sid_] = c
        trips = B.feed_trips(d); ri = B.routes_info(d)
        print(fd, "trips", len(trips), "stops near a station", len(near), flush=True)
        pat_cache = {}
        seen_trip = set()

        def finish(tid, rows):
            if tid in seen_trip: raise SystemExit("stop_times not contiguous per trip: " + tid)
            seen_trip.add(tid)
            rows.sort()
            key = tuple((r[4], r[5], r[6]) for r in rows)
            ent = pat_cache.get(key)
            if ent is None:
                cum = [0.0]
                for a, b in zip(rows, rows[1:]):
                    cum.append(cum[-1] + B.dist_m(stops[a[4]][:2], stops[b[4]][:2]))
                best = {}
                idx = [i for i, r in enumerate(rows) if r[4] in near and r[5] != "1"]
                jdx = [j for j, r in enumerate(rows) if r[4] in near and r[6] != "1"]
                for i in idx:
                    for sa, da in near[rows[i][4]]:
                        for j in jdx:
                            if j <= i: continue
                            for sb, db in near[rows[j][4]]:
                                if sa == sb: continue
                                w = B.walk_s(da) + B.walk_s(db)
                                k = (sa, sb)
                                if k not in best or w < best[k][0]: best[k] = (w, i, j, rows[i][4], rows[j][4], cum[j] - cum[i])
                ent = (len(rows), list(best.items()))
                pat_cache[key] = ent
            n_, cands = ent
            tr = trips[tid]
            for (sa, sb), (w, i, j, stA, stB, pm) in cands:
                recs[(tr["route_id"], tr["direction_id"], sa, sb, stA, stB)].append((rows[i][3], rows[j][2], tid, j - i, n_, int(pm)))

        cur, rows = None, []
        for tid, seq, arr, dep, stop, pu, do in B.read_stop_times(f"{d}/stop_times.json", trips):
            if tid != cur:
                if cur is not None: finish(cur, rows)
                cur, rows = tid, []
            rows.append((seq, 0, arr, dep, stop, pu, do))
        if cur is not None: finish(cur, rows)
        for rid in {k[0] for k in recs}: rinfo.setdefault(rid, ri.get(rid))
        for s_, v in stops.items(): stopxy[s_] = v
        print("  segments so far", len(recs), flush=True)
    rinfo = {k: {"short": v["route_short_name"], "long": v["route_long_name"], "class": B.route_class(v)} for k, v in rinfo.items() if v}
    return dict(recs), rinfo, stopxy


if CACHE and os.path.exists(CACHE):
    recs, rinfo, stopxy = pickle.load(open(CACHE, "rb"))
else:
    recs, rinfo, stopxy = extract()
    if CACHE: pickle.dump((recs, rinfo, stopxy), open(CACHE, "wb"))
print("segments", len(recs), flush=True)

# ---------------------------------------------------------------- existing subway/walk path (CSA from a platform)
dep_t, arr_t, dep_s, arr_s, trip, chg = (z[k] for k in ("dep_t", "arr_t", "dep_s", "arr_s", "trip", "chg"))
fp_ptr, fp_to, fp_t = z["fp_ptr"], z["fp_to"], z["fp_t"]
NT = int(trip.max()) + 1
INF = 1 << 40


@njit(cache=True)
def scan(src, t, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t, n, nt, horizon):
    """earliest platform-ready arrival at every station from src at time t (trains and walks); ready = arrival + change time"""
    ar = np.full(n, INF, np.int64); ready = np.full(n, INF, np.int64); tb = np.zeros(nt, np.bool_)
    ar[src] = t; ready[src] = t
    for k in range(fp_ptr[src], fp_ptr[src + 1]):
        j = fp_to[k]; w = t + fp_t[k]
        if w < ar[j]: ar[j] = w; ready[j] = w
    lo, hi = 0, dep_t.shape[0]
    while lo < hi:
        mid = (lo + hi) // 2
        if dep_t[mid] < t: lo = mid + 1
        else: hi = mid
    for c in range(lo, dep_t.shape[0]):
        d = dep_t[c]
        if d > t + horizon: break
        tr = trip[c]
        if not tb[tr] and ready[dep_s[c]] <= d: tb[tr] = True
        if tb[tr]:
            a = arr_t[c]; s2 = arr_s[c]
            if a < ar[s2]:
                ar[s2] = a; ready[s2] = a + chg[s2]
                for k in range(fp_ptr[s2], fp_ptr[s2 + 1]):
                    j = fp_to[k]; w = a + fp_t[k]
                    if w < ar[j]: ar[j] = w; ready[j] = w
    return ar


def existing(src):
    """seconds src -> every station, per band (mean over 3 start times), shape (6, N)"""
    out = np.zeros((6, N))
    for k, (_, a, b) in enumerate(BANDS):
        acc = []
        for f in (0.1, 0.5, 0.9):
            t = int((a + (b - a) * f) * 3600)
            ar = scan(src, t, dep_t, arr_t, dep_s, arr_s, trip, chg, fp_ptr, fp_to, fp_t, N, NT, 8 * 3600)
            acc.append(np.where(ar >= INF, 8 * 3600, ar - t))
        out[k] = np.mean(acc, axis=0)
    return out


# ---------------------------------------------------------------- phase 2: per-link metrics
TYPE_F = {"sbs": 1.0, "limited": 0.92, "express": 0.9, "local": 0.85}
by_pair = collections.defaultdict(list)
for key, v in recs.items():
    by_pair[(key[0], key[1], key[2], key[3])].append((key, v))
links = []
for (rid, dr, a, b), alts in by_pair.items():
    key, v = max(alts, key=lambda kv: (len(kv[1]), -B.walk_s(0)))   # the stop pair most trips use
    if len(alts) > 1:   # several stop pairs: prefer the one with the least walking among those with >= half the trips
        top = max(len(x[1]) for x in alts)
        key, v = min((x for x in alts if len(x[1]) * 2 >= top),
                     key=lambda x: B.dist_m(stopxy[x[0][4]][:2], COORD[a]) + B.dist_m(stopxy[x[0][5]][:2], COORD[b]))
    stA, stB = key[4], key[5]
    da = B.dist_m(stopxy[stA][:2], COORD[a]); db = B.dist_m(stopxy[stB][:2], COORD[b])
    wi, wo = B.walk_s(da), B.walk_s(db)
    v = sorted(v)
    sod = np.array([x[0] % 86400 for x in v]); ride = np.array([x[1] - x[0] for x in v]); bd = np.array([band_of(s) for s in sod])
    order = np.argsort(sod); ss = sod[order]
    gaps = np.diff(np.append(ss, ss[0] + 86400)); gb = np.array([band_of(s) for s in ss])
    bands = []
    for k in range(6):
        g = gaps[gb == k]; r = ride[bd == k]
        if len(g) >= 2 and g.mean() <= 90 * 60:
            hw = float(g.mean()); cv = float(g.std() / g.mean())
            rd = float(np.median(r)); door = wi + 0.5 * hw + rd + wo
            bands.append({"n": int((bd == k).sum()), "hw_min": round(hw / 60, 1), "cv": round(cv, 2), "ride_min": round(rd / 60, 1), "door_min": round(door / 60, 1)})
        else:
            bands.append(None)
    if not any(bands): continue
    cls = rinfo.get(rid, {}).get("class", "local")
    mph = (v[0][5] / 1609.0) / (float(np.median(ride)) / 3600.0) if np.median(ride) > 0 else 0
    links.append({"route": rid, "short": rinfo.get(rid, {}).get("short", rid), "dir": dr, "class": cls,
                  "A": ST[a], "B": ST[b], "a": a, "b": b, "nameA": NAMES[a], "nameB": NAMES[b],
                  "stopA": stA, "stopB": stB, "stopA_name": stopxy[stA][2], "stopB_name": stopxy[stB][2],
                  "walk_in_s": wi, "walk_out_s": wo, "dist_in_m": int(da), "dist_out_m": int(db),
                  "stops_ridden": int(np.median([x[3] for x in v])), "pattern_stops": int(np.median([x[4] for x in v])),
                  "mph": round(mph, 1), "first": int(ss[0] if ss[0] < 4 * 3600 else ss[0]), "bands": bands, "trips": [[x[2], x[0], x[1]] for x in v]})
print("links", len(links), flush=True)

# subway/walk alternative: one scan set per distinct source
srcs = sorted({l["a"] for l in links}); EX = {}
for i, s in enumerate(srcs):
    EX[s] = existing(s)
print("scanned", len(srcs), "sources", flush=True)
W = np.array([(b - a) for _, a, b in BANDS], float); W /= W.sum()
keep = []
for l in links:
    ex = EX[l["a"]][:, l["b"]] / 60.0
    sv = []
    for k, bd_ in enumerate(l["bands"]):
        if bd_: bd_["existing_min"] = round(float(ex[k]), 1); bd_["saving_min"] = round(float(ex[k]) - bd_["door_min"], 1)
        sv.append(max(0.0, bd_["saving_min"]) if bd_ else 0.0)
    avg = float(np.dot(W, sv))
    if avg <= 0: continue
    use = [bd_ for k, bd_ in enumerate(l["bands"]) if bd_ and bd_["saving_min"] > 0]
    cv = float(np.mean([x["cv"] for x in use]))
    f_type = TYPE_F[l["class"]]; f_stops = 1 - min(0.30, 0.008 * l["stops_ridden"])
    f_reg = 1 / (1 + 0.5 * cv); f_speed = 0.75 + 0.25 * min(1.0, max(0.0, (l["mph"] - 5) / 5)); f_len = 1 - min(0.20, 0.001 * l["pattern_stops"])
    R_ = f_type * f_stops * f_reg * f_speed * f_len
    l.update({"avg_saving_min": round(avg, 2), "best_saving_min": round(max(sv), 1), "reliability": round(R_, 3),
              "rel_parts": {"type": f_type, "stops": round(f_stops, 2), "regularity": round(f_reg, 2), "speed": round(f_speed, 2), "route_len": round(f_len, 2)},
              "score": round(R_ * avg, 3), "hours_with_saving": [BANDS[k][0] for k, bd_ in enumerate(l["bands"]) if bd_ and bd_["saving_min"] > 0]})
    keep.append(l)
keep.sort(key=lambda l: -l["score"])
# keep the best route per directed station pair as the link; the others are listed as alternatives
best = {}; alts = collections.defaultdict(list)
for l in keep:
    k = (l["a"], l["b"])
    if k not in best: best[k] = l
    else: alts[k].append(l["short"])
ranked = sorted(best.values(), key=lambda l: -l["score"])
for l in ranked: l["alt_routes"] = alts[(l["a"], l["b"])]
for i, l in enumerate(ranked): l["rank"] = i + 1
ranked = ranked[:TOPN]
json.dump({"date": B.DAY_DATE, "model": meta.get("params"), "bands": [b[0] for b in BANDS], "links": ranked}, open(f"{OUT}/links.json", "w"), separators=(",", ":"))
print("kept", len(ranked), "links; json", os.path.getsize(f"{OUT}/links.json") // 1024, "KB", flush=True)


def cell(b, key):
    return "-" if not b else f"{b[key]:g}"


H = ["# Bus links between subway stations, ranked", "",
     f"Weekday bus schedule of {B.DAY_DATE} (MTA bus GTFS, feeds {', '.join(B.FEEDS)}); subway/walk alternatives from the planner's model "
     "(MTA transfer times, walk/run links to 2.5 km, 472-station count). **No real-time data is available**: reliability below is a schedule-based proxy, "
     "not a measurement. Arriving or passing a station by bus does not count as visiting it; a link is only a way to get from A to B.", "",
     "Definitions: `door` = walk to stop + half the average headway + scheduled ride + walk from stop (platform to platform, expected). "
     "`existing` = fastest subway/walk path A to B in the model (mean of 3 start times in the band). `saving` = existing - door. "
     "Score = reliability x time-weighted mean over the day of max(0, saving); bands without service count as 0.", "",
     "Reliability proxy R = type x stops x regularity x speed x route length (SBS 1.0 / limited 0.92 / express 0.90 / local 0.85; "
     "1 - 0.8% per stop ridden, max 30%; 1/(1+0.5 CV of scheduled gaps); scheduled mph 5..10 maps to 0.75..1.0, slow = congested corridor; "
     "1 - 0.1% per stop on the route pattern, max 20%). Share of the trip on busy corridors can't be told from the schedule; scheduled speed stands in for it.", "",
     "Bands: early 4-6, AM 6-10, midday 10-15, PM 15-19, evening 19-23, night 23-4. Cells show headway min / saving min (`-` = no service or under 2 per band).", "",
     "| # | From -> To | Route (class) | Walk in/out m | Ride min | " + " | ".join(b[0] for b in BANDS) + " | Avg saving | R | Score |",
     "|---|---|---|---|---|" + "---|" * 6 + "---|---|---|"]
for l in ranked[:60]:
    rd = [x["ride_min"] for x in l["bands"] if x]
    cells = [("-" if not x else f"{x['hw_min']:g} / {x['saving_min']:+g}") for x in l["bands"]]
    H.append(f"| {l['rank']} | {l['nameA']} -> {l['nameB']} | {l['short']} ({l['class']}) | {l['dist_in_m']}/{l['dist_out_m']} | {statistics.median(rd):g} | "
             + " | ".join(cells) + f" | {l['avg_saving_min']:g} | {l['reliability']:g} | {l['score']:g} |")
H += ["", f"{len(ranked)} links are in links.json (best route per directed station pair; each has its trips with trip ids, so the planner needs no bus feed). "
      "Rows beyond 60 are in the JSON only."]
open(f"{OUT}/ranking.md", "w").write("\n".join(H) + "\n")
