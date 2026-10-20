"""Scheduled-bus data shared by busrank.py (ranking), model.py (--bus-links) and verify.py.

Bus GTFS (MTA bus feeds, JSON export next to the subway one: bus_bk, bus_bx, bus_m, bus_qns, bus_si, bus_busco).
A "link" is a directed pair of subway stations (A -> B) joined by one bus route and direction:
board at a bus stop within REACH metres of A, ride, alight at a stop within REACH metres of B.
Buses never count as visiting a station (Guinness: only the subway counts): a bus connection is
only a way to get from A to B.

Walk to/from the bus stop: leave the station (60 s) + the street walk, running beyond 300 m as the
repo's street model does (realistic.py). The clock is stopped nowhere: the rider is at the stop for the
scheduled departure, no buffer.
"""
import json, math, os, glob, datetime, collections
import realistic as R

REACH = 400.0            # m straight-line between a station and its bus stop
EXIT_S = 60              # s from the platform to the street (or street to platform)
FEEDS = ["bus_bk", "bus_bx", "bus_m", "bus_qns", "bus_si", "bus_busco"]
DAY_DATE = "20261027"    # a Tuesday inside the subway feed's validity; picks the weekday service set
DAY = 86400


def walk_s(d):
    """seconds from the platform to a stop (or back) d metres away straight-line: exit + street walk, running beyond RUN_FROM"""
    w = min(d, R.RUN_FROM) * R.DETOUR / R.WALK_SPEED
    r = max(0.0, d - R.RUN_FROM) * R.DETOUR / R.RUN_SPEED
    return int(EXIT_S + w + r)


def dist_m(a, b):
    return math.hypot((a[0] - b[0]) * 111_000, (a[1] - b[1]) * 111_000 * math.cos(math.radians(40.72)))


def tsec(t):
    h, m, s = t.split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def active_services(feed_dir, date=DAY_DATE):
    cal = json.load(open(f"{feed_dir}/calendar.json")); cd = json.load(open(f"{feed_dir}/calendar_dates.json"))
    wd = datetime.datetime.strptime(date, "%Y%m%d").weekday()
    col = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][wd]
    act = {c["service_id"] for c in cal if c["start_date"] <= date <= c["end_date"] and c[col] == "1"}
    for x in cd:
        if x["date"] == date:
            (act.add if x["exception_type"] == "1" else act.discard)(x["service_id"])
    return act


def read_stop_times(path, want):
    """stream stop_times.json (one JSON object per line); yield (trip_id, seq, arr, dep, stop_id, pickup, dropoff) for trips in `want`"""
    with open(path) as f:
        for line in f:
            if len(line) < 20 or line[0] != "{": continue
            p = line.split('"')
            tid = p[3]
            if tid in want:
                yield tid, int(p[19]), tsec(p[7]), tsec(p[11]), p[15], p[23], p[27]


def feed_trips(feed_dir, date=DAY_DATE):
    act = active_services(feed_dir, date)
    return {t["trip_id"]: t for t in json.load(open(f"{feed_dir}/trips.json")) if t["service_id"] in act}


def routes_info(feed_dir):
    return {r["route_id"]: r for r in json.load(open(f"{feed_dir}/routes.json"))}


def route_class(r):
    """sbs / limited / express / local from the route record"""
    n = (r.get("route_short_name") or "") + " " + (r.get("route_long_name") or "")
    rid = r["route_id"]
    if "SBS" in n.upper() or rid.endswith("+"): return "sbs"
    if "LTD" in n.upper() or "LIMITED" in n.upper(): return "limited"
    if rid.upper().startswith(("BXM", "BM", "QM", "SIM")) or "EXPRESS" in n.upper(): return "express"
    return "local"
