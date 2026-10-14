"""Hourly average headways for every line, direction and station, from three sources:

  scheduled_headways(gtfs_dir, day_type)       the static GTFS timetable (CSV .txt or JSON export)
  observed_headways(stop_times_csv, trips_csv)  subwaydata.nyc daily files (actual arrivals, built
                                                from the MTA GTFS-realtime feeds)
  live_headways(feed_bytes)                     one GTFS-realtime TripUpdates snapshot (predicted
                                                arrivals in the next hour or so)

All return HeadwayTable: {(line, direction, station, day_type, hour): Stat}, where Stat holds the
gaps (minutes) between consecutive trains whose earlier train leaves in that clock hour.
  mean  = average headway          -> what a "1/2 headway" model uses
  wait  = sum(g^2) / (2 sum(g))     -> expected wait for someone arriving at random; equals mean/2
                                       only when trains are perfectly even
line: route id with express variants folded (6X->6, 7X->7, FX->F). direction: 'N' or 'S' (the GTFS
stop-id suffix). station: GTFS parent station id. day_type: 'weekday', 'saturday' or 'sunday'.
"""
import csv, io, json, os, math, collections
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MAX_GAP_MIN = 90          # ignore gaps longer than this (service ended, data holes)
FOLD = {"6X": "6", "7X": "7", "FX": "F", "5X": "5"}


def line_of(route_id): return FOLD.get(route_id, route_id)


def day_type_of(date):
    return "saturday" if date.weekday() == 5 else "sunday" if date.weekday() == 6 else "weekday"


class Stat:
    __slots__ = ("gaps",)
    def __init__(self): self.gaps = []
    @property
    def n(self): return len(self.gaps)
    @property
    def mean(self): return sum(self.gaps) / len(self.gaps) if self.gaps else None
    @property
    def wait(self):
        s = sum(self.gaps); return sum(g * g for g in self.gaps) / (2 * s) if s else None
    def to_json(self):
        return {"n": self.n, "mean": round(self.mean, 2), "wait": round(self.wait, 2)} if self.gaps else None


def _add_gaps(table, key_base, times_sec, day_type, to_hour):
    """times_sec: sorted departure times (seconds); to_hour maps a time to its clock hour."""
    for a, b in zip(times_sec, times_sec[1:]):
        g = (b - a) / 60.0
        if 0 < g <= MAX_GAP_MIN:
            k = key_base + (day_type, to_hour(a))
            table.setdefault(k, Stat()).gaps.append(g)


# ---------------------------------------------------------------- GTFS schedule
def _read(gtfs_dir, name):
    j = os.path.join(gtfs_dir, name + ".json")
    if os.path.exists(j): return json.load(open(j))
    with open(os.path.join(gtfs_dir, name + ".txt"), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def service_ids(gtfs_dir, day_type):
    col = {"weekday": "monday", "saturday": "saturday", "sunday": "sunday"}[day_type]
    return {c["service_id"] for c in _read(gtfs_dir, "calendar") if c[col] == "1"}


def scheduled_headways(gtfs_dir, day_type="weekday", table=None):
    """Hourly headways from the timetable for one day type (pooling all its service ids)."""
    table = {} if table is None else table
    stops = {s["stop_id"]: s for s in _read(gtfs_dir, "stops")}
    sids = service_ids(gtfs_dir, day_type)
    trips = {t["trip_id"]: t["route_id"] for t in _read(gtfs_dir, "trips") if t["service_id"] in sids}
    deps = collections.defaultdict(list)
    for r in _read(gtfs_dir, "stop_times"):
        rid = trips.get(r["trip_id"])
        if rid is None or rid == "SI": continue
        sid = r["stop_id"]; d = sid[-1] if sid[-1] in "NS" else "?"
        par = stops[sid]["parent_station"] or sid
        h, m, s = map(int, (r["departure_time"] or r["arrival_time"]).split(":"))
        deps[(line_of(rid), d, par)].append(h * 3600 + m * 60 + s)
    for k, v in deps.items():
        v.sort(); _add_gaps(table, k, v, day_type, lambda t: (t // 3600) % 24)
    return table


# ---------------------------------------------------------------- observed (subwaydata.nyc)
def observed_headways(stop_times_csv, trips_csv, table=None):
    """Actual departures from one subwaydata.nyc day (trips.csv + stop_times.csv, as text or path).
    Uses only stops the train was marked as having passed, at their recorded departure (or arrival)
    time. Day type comes from each trip's local start date."""
    table = {} if table is None else table
    def rows(x):
        f = open(x, newline="") if isinstance(x, str) and os.path.exists(x) else io.StringIO(x)
        return csv.DictReader(f)
    trip = {}
    for t in rows(trips_csv):
        if t["route_id"] in ("SI", ""): continue
        start = datetime.fromtimestamp(int(t["start_time"]), ET)
        trip[t["trip_uid"]] = (line_of(t["route_id"]), day_type_of(start.date()), start.date())
    deps = collections.defaultdict(list)
    for r in rows(stop_times_csv):
        tr = trip.get(r["trip_uid"])
        if tr is None or not r["marked_past"]: continue
        ts = r["departure_time"] or r["arrival_time"]
        if not ts: continue
        sid = r["stop_id"]; d = sid[-1] if sid[-1] in "NS" else "?"
        par = sid[:-1] if d != "?" else sid
        deps[(tr[0], d, par, tr[1], tr[2])].append(int(ts))
    for (ln, d, par, dt, date), v in deps.items():
        v = sorted(set(v)); _add_gaps(table, (ln, d, par), v, dt, lambda t: datetime.fromtimestamp(t, ET).hour)
    return table


# ---------------------------------------------------------------- live GTFS-realtime snapshot
def live_headways(feed_bytes, now=None, table=None):
    """Predicted headways from one GTFS-realtime TripUpdates message (protobuf bytes). Needs the
    gtfs-realtime-bindings package. Useful as 'right now' input for the planner."""
    from google.transit import gtfs_realtime_pb2
    table = {} if table is None else table
    msg = gtfs_realtime_pb2.FeedMessage(); msg.ParseFromString(feed_bytes)
    now = now or msg.header.timestamp
    deps = collections.defaultdict(list)
    for e in msg.entity:
        if not e.HasField("trip_update"): continue
        rid = e.trip_update.trip.route_id
        if rid == "SI": continue
        for u in e.trip_update.stop_time_update:
            t = (u.departure.time if u.HasField("departure") else 0) or (u.arrival.time if u.HasField("arrival") else 0)
            if t and t >= now:
                sid = u.stop_id; d = sid[-1] if sid[-1] in "NS" else "?"
                deps[(line_of(rid), d, sid[:-1] if d != "?" else sid)].append(int(t))
    dt = day_type_of(datetime.fromtimestamp(now, ET).date())
    for k, v in deps.items():
        v = sorted(set(v)); _add_gaps(table, k, v, dt, lambda t: datetime.fromtimestamp(t, ET).hour)
    return table


# ---------------------------------------------------------------- planner input + comparison
def to_json(table):
    """{"line|dir|station|day_type|hour": {"n", "mean", "wait"}} for saving / the planner."""
    return {"|".join(map(str, k)): v.to_json() for k, v in table.items() if v.n}


def half_headway(hw_json, line, direction, station, day_type, hour, use="mean", default=10.0):
    """Minutes of expected wait used by the 1/2-headway model: mean/2 (use='mean', Trail of Bits
    style) or the irregularity-aware expected wait (use='wait'). Falls back to neighbouring hours."""
    for dh in (0, -1, 1, -2, 2):
        v = hw_json.get(f"{line}|{direction}|{station}|{day_type}|{(hour + dh) % 24}")
        if v: return v["mean"] / 2 if use == "mean" else v["wait"]
    return default


def compare(sched, obs, min_gaps=4):
    """Per (line, dir, station, day_type, hour) present in both: scheduled vs observed mean headway
    and expected wait. Returns a list of rows."""
    out = []
    for k, s in sched.items():
        o = obs.get(k)
        if not o or o.n < min_gaps or s.n < 2: continue
        out.append({"line": k[0], "dir": k[1], "station": k[2], "day_type": k[3], "hour": k[4],
                    "sched_mean": round(s.mean, 2), "obs_mean": round(o.mean, 2),
                    "sched_wait": round(s.wait, 2), "obs_wait": round(o.wait, 2), "obs_n": o.n})
    return out


def summarize(rows, by):
    """Aggregate compare() rows by 'line' or 'station': median headway ratio, share of station-hours
    within +/-20% of schedule, and average extra wait vs a perfectly kept schedule (minutes)."""
    g = collections.defaultdict(list)
    for r in rows: g[r[by]].append(r)
    res = {}
    for k, v in g.items():
        ratios = sorted(r["obs_mean"] / r["sched_mean"] for r in v)
        res[k] = {"station_hours": len(v), "median_ratio": round(ratios[len(ratios) // 2], 3),
                  "within_20pct": round(sum(1 for x in ratios if 0.8 <= x <= 1.2) / len(v), 3),
                  "extra_wait_min": round(sum(r["obs_wait"] - r["sched_mean"] / 2 for r in v) / len(v), 2),
                  "sched_half_hw_min": round(sum(r["sched_mean"] / 2 for r in v) / len(v), 2),
                  "obs_wait_min": round(sum(r["obs_wait"] for r in v) / len(v), 2)}
    return res
