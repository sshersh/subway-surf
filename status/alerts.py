"""Turn MTA subway alerts into service changes the solver can plan around.

    python3 status/alerts.py --out changes.json                    # fetch the live feed
    python3 status/alerts.py --feed alerts.json --now 1791847300   # offline / testing

Only alerts that name stations become changes, because only those can be modeled exactly:
  skip  trains on the named lines run but don't stop at the named stations
        (skipped stops, express runs, bypassed stations)
  cut   trains on the named lines don't run through the named stations at all
        (suspensions, station closures); a trip is split where it is cut
A station-closure alert with no lines applies to every line at that station. Direction-specific stop
IDs (e.g. A24N) only affect that direction.

When a change applies, on the run day (the next weekday after today, New York time):
  unplanned alerts active now   all day: the plan assumes current disruptions last the whole run
  everything else               only during the alert's active periods
Alerts that name no stations, reroutes and delays can't be modeled; they're listed under
"not_modeled" so the banner can still show them.

"hash" covers only what changes the timetable (run day, effect, lines, stops, times), so reworded
or re-issued alerts don't trigger a new solve.
"""
import argparse, hashlib, json, os, sys, time, urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_status import FEED, ET, classify, line_of, text_of

CUT = ("suspend", "no trains", "no scheduled service", "station closed", "station closure", "closed")
SKIP = ("skip", "bypass", "local to express", "express service", "express from", "running express", "run express")


def effect_of(alert_type, header):
    t, h = (alert_type or "").lower(), (header or "").lower()
    if any(k in t for k in CUT): return "cut"
    if any(k in t for k in SKIP): return "skip"
    if any(k in h for k in SKIP): return "skip"
    if any(k in h for k in CUT) or "no [" in h: return "cut"
    return None


def run_day(now):
    """Next weekday after today, New York time: a run can still start at any hour that day."""
    d = datetime.fromtimestamp(now, ET).date()
    for i in range(1, 8):
        day = d + timedelta(days=i)
        if day.weekday() < 5: return day
    return None


def changes_from(feed, stops, now):
    """stops: set of valid GTFS stop IDs (stations and platforms)."""
    day = run_day(now)
    day0 = datetime(day.year, day.month, day.day, tzinfo=ET)
    lo, hi = day0.timestamp(), (day0 + timedelta(days=2)).timestamp()   # the model covers two service days
    out, skipped = [], []
    for e in feed.get("entity", []):
        a = e.get("alert")
        if not a: continue
        merc = a.get("transit_realtime.mercury_alert") or a.get("mercury_alert") or {}
        atype, header = merc.get("alert_type", ""), text_of(a.get("header_text"))
        periods = [(int(p.get("start") or 0), int(p.get("end") or 0)) for p in a.get("active_period", [])] or [(0, 0)]
        lines, sts = set(), set()
        for ie in a.get("informed_entity", []):
            if ie.get("route_id"): lines.add(line_of(ie["route_id"]))
            s = (ie.get("stop_id") or "").strip().upper()
            if s in stops: sts.add(s)
        lines.discard("SI")
        kind = classify(atype, header)
        if kind == "info": continue
        planned = str(e.get("id", "")).startswith("lmm:planned") or atype.lower().startswith("planned")
        active_now = any(s <= now and (x == 0 or now <= x) for s, x in periods)
        eff = effect_of(atype, header) if kind == "blocked" else None
        if not eff or not sts:
            if lines and (active_now or any(s < hi and (x == 0 or x > lo) for s, x in periods)):
                skipped.append({"id": e.get("id"), "kind": kind, "lines": sorted(lines), "text": header[:280], "type": atype})
            continue
        if active_now and not planned:
            when = "always"
        else:
            when = sorted([max(s, int(lo)), min(x, int(hi)) if x else int(hi)] for s, x in periods if s < hi and (x == 0 or x > lo))
            if not when: continue
        out.append({"id": e.get("id"), "effect": eff, "lines": sorted(lines), "stops": sorted(sts), "when": when,
                    "planned": planned, "type": atype, "text": header[:280]})
    out.sort(key=lambda c: (c["effect"], c["lines"], c["stops"], str(c["when"])))
    key = json.dumps([str(day)] + [[c["effect"], c["lines"], c["stops"], c["when"]] for c in out], sort_keys=True)
    return {"run_date": str(day), "generated_at": int(now), "feed_timestamp": int(feed.get("header", {}).get("timestamp") or 0),
            "hash": hashlib.sha256(key.encode()).hexdigest()[:16], "changes": out, "not_modeled": skipped}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", help="alerts JSON file (default: fetch live)")
    ap.add_argument("--stops", default=None, help="GTFS stops.json (default: results/stations.json, stations only)")
    ap.add_argument("--out", default="changes.json")
    ap.add_argument("--now", type=int, default=None)
    a = ap.parse_args()
    if a.feed:
        feed = json.load(open(a.feed))
    else:
        req = urllib.request.Request(FEED, headers={"User-Agent": "subway-surf-status/1.0"})
        feed = json.load(urllib.request.urlopen(req, timeout=60))
    if a.stops:
        stops = {s["stop_id"] for s in json.load(open(a.stops))}
    else:
        st = json.load(open(os.path.join(os.path.dirname(__file__), "..", "results", "stations.json")))
        stops = set(st) | {s + d for s in st for d in "NS"}
    ch = changes_from(feed, stops, a.now or time.time())
    json.dump(ch, open(a.out, "w"), indent=1)
    print(f"run day {ch['run_date']}: {len(ch['changes'])} modeled changes, {len(ch['not_modeled'])} not modeled, hash {ch['hash']}")


if __name__ == "__main__":
    main()
