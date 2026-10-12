"""Check MTA subway service alerts against the planned Subway Challenge route.

Reads the MTA GTFS-realtime alerts feed (JSON), finds alerts that touch the lines and stations the
route depends on, and writes status.json for the viewer banner.

    python3 status/check_status.py --out viewer/status.json            # fetch the live feed
    python3 status/check_status.py --feed alerts.json --now 1791847300  # offline / testing

What counts:
  blocked   an active suspension, skipped stops, station closure or express run that hits a station
            the route needs on that line (the plan cannot run as scheduled)
  possible  same alert types, but the alert lists no stations, or only a reroute: may break the plan
  delay     delays or reduced service on a line the route uses: the plan assumes on-time trains
Alerts are checked twice: those active right now, and planned work that overlaps each leg's clock
time if the run started at its scheduled time on the next weekday.
"""
import argparse, json, sys, time, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FEED = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/camsys%2Fsubway-alerts.json"
ET = ZoneInfo("America/New_York")
BLOCK = ("suspend", "stops skipped", "stations skipped", "station closed", "skip", "no scheduled service",
         "local to express", "express service", "no trains")
POSSIBLE = ("reroute", "rerouted", "service change", "planned work", "multiple impacts")
DELAY = ("delay", "slow", "reduced service", "severe", "irregular")


def line_of(route_id):
    r = (route_id or "").strip().upper()
    return {"6X": "6", "7X": "7", "FX": "F", "5X": "5", "SS": "SI"}.get(r, r)


def station_of(stop_id, stations):
    s = (stop_id or "").strip().upper()
    if s in stations: return s
    if s[:-1] in stations and s[-1:] in ("N", "S"): return s[:-1]
    return None


def text_of(ts):
    tr = (ts or {}).get("translation", []) if isinstance(ts, dict) else []
    for t in tr:
        if (t.get("language") or "en").lower().startswith("en") and "html" not in (t.get("language") or ""):
            return " ".join((t.get("text") or "").split())
    return " ".join((tr[0].get("text") or "").split()) if tr else ""


def classify(alert_type, header):
    s = f"{alert_type} {header}".lower()
    if any(k in (alert_type or "").lower() for k in BLOCK): return "blocked"
    if any(k in (alert_type or "").lower() for k in DELAY): return "delay"
    if any(k in (alert_type or "").lower() for k in POSSIBLE): return "possible"
    # unplanned alerts without a recognized type: read the headline
    if "no [" in s or "suspend" in s or "skip" in s or "express from" in s or "running express" in s: return "blocked"
    if "delay" in s: return "delay"
    return "info"


def parse_feed(feed, stations):
    out = []
    for e in feed.get("entity", []):
        a = e.get("alert")
        if not a: continue
        merc = a.get("transit_realtime.mercury_alert") or a.get("mercury_alert") or {}
        periods = [(int(p.get("start") or 0), int(p.get("end") or 0)) for p in a.get("active_period", [])] or [(0, 0)]
        lines, stops = set(), set()
        for ie in a.get("informed_entity", []):
            if ie.get("route_id"): lines.add(line_of(ie["route_id"]))
            st = station_of(ie.get("stop_id"), stations)
            if st: stops.add(st)
        lines.discard("SI")
        header = text_of(a.get("header_text"))
        atype = merc.get("alert_type", "")
        out.append({"id": e.get("id"), "type": atype, "kind": classify(atype, header), "periods": periods,
                    "lines": sorted(lines), "stops": sorted(stops), "text": header,
                    "planned": str(e.get("id", "")).startswith("lmm:planned") or atype.lower().startswith("planned")})
    return out


def active(periods, t):
    return any(s <= t and (e == 0 or t <= e) for s, e in periods)


def route_needs(rows):
    """(line, station, seconds-into-service-day) for every stop the plan needs a train to make."""
    need = []
    for prev, cur in zip(rows, rows[1:]):
        if not cur["route"]: continue
        t = sum(int(x) * k for x, k in zip(cur["time"].split(":"), (3600, 60, 1)))
        ln = line_of(cur["route"])
        need.append((ln, prev["stop_id"], t))
        need.append((ln, cur["stop_id"], t))
    return need


def next_run_start(rows, now):
    """Next weekday the run could start at its scheduled time (ET)."""
    h, m, s = map(int, rows[0]["time"].split(":"))
    d = datetime.fromtimestamp(now, ET).date()
    for i in range(8):
        day = d + timedelta(days=i)
        if day.weekday() < 5:
            start = datetime(day.year, day.month, day.day, tzinfo=ET) + timedelta(hours=h, minutes=m, seconds=s)
            if start.timestamp() > now: return datetime(day.year, day.month, day.day, tzinfo=ET)
    return None


def match(alert, need, stations, day0=None):
    """Return the route stops this alert hits. day0 = service-day midnight to test planned periods."""
    hits = []
    for ln, st, t in need:
        if alert["lines"] and ln not in alert["lines"]: continue
        if alert["stops"] and st not in alert["stops"]: continue
        if not alert["lines"] and not alert["stops"]: continue
        if day0 is not None:
            # wall clock for t seconds after service-day midnight (DST-safe)
            when = (day0 + timedelta(seconds=t)).timestamp()
            if not active(alert["periods"], when): continue
        hits.append((st, t))
    return hits


def summarize(alert, hits, stations, kind):
    seen, names = set(), []
    for st, _ in sorted(hits, key=lambda x: x[1]):
        if st not in seen: seen.add(st); names.append(stations[st]["n"])
    ts = sorted({t for _, t in hits})
    if not alert["stops"]:   # alert names a line but no stations: report how much of the plan uses it
        return {"id": alert["id"], "kind": kind, "lines": alert["lines"], "text": alert["text"][:280],
                "type": alert["type"], "stations": [], "line_stops_in_plan": len(names), "more_stations": 0,
                "plan_times": []}
    return {"id": alert["id"], "kind": kind, "lines": alert["lines"], "text": alert["text"][:280],
            "type": alert["type"], "stations": names[:12], "more_stations": max(0, len(names) - 12),
            "plan_times": [f"{t//3600:02d}:{t%3600//60:02d}" for t in ts[:1]] + ([f"{ts[-1]//3600:02d}:{ts[-1]%3600//60:02d}"] if len(ts) > 1 else [])}


def check(feed, rows, stations, now):
    alerts = parse_feed(feed, stations)
    need = route_needs(rows)
    used_lines = {ln for ln, _, _ in need}
    now_items, plan_items = [], []
    for a in alerts:
        if a["kind"] == "info": continue
        if active(a["periods"], now):
            if a["kind"] == "delay":
                if set(a["lines"]) & used_lines:
                    now_items.append({"id": a["id"], "kind": "delay", "lines": a["lines"], "text": a["text"][:280], "type": a["type"]})
                continue
            hits = match(a, need, stations)
            if hits:
                kind = "blocked" if (a["kind"] == "blocked" and a["stops"]) else "possible"
                now_items.append(summarize(a, hits, stations, kind))
    day0 = next_run_start(rows, now)
    if day0:
        for a in alerts:
            if a["kind"] in ("info", "delay") or not a["planned"]: continue
            hits = match(a, need, stations, day0)
            if hits:
                kind = "blocked" if (a["kind"] == "blocked" and a["stops"]) else "possible"
                plan_items.append(summarize(a, hits, stations, kind))
    order = {"blocked": 0, "possible": 1, "delay": 2}
    now_items.sort(key=lambda x: order[x["kind"]]); plan_items.sort(key=lambda x: order[x["kind"]])
    kinds = {i["kind"] for i in now_items}
    verdict = "blocked" if "blocked" in kinds else "possible" if "possible" in kinds else "delays" if "delay" in kinds else "ok"
    run_start = (day0 + timedelta(seconds=sum(int(x) * k for x, k in zip(rows[0]["time"].split(":"), (3600, 60, 1))))) if day0 else None
    return {"checked_at": int(now), "feed_timestamp": int(feed.get("header", {}).get("timestamp") or 0),
            "verdict": verdict, "now": now_items, "alerts_in_feed": len(alerts),
            "next_run": {"start": run_start.isoformat() if run_start else None, "issues": plan_items}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", help="alerts JSON file (default: fetch live)")
    ap.add_argument("--route", default="results/best_route.json")
    ap.add_argument("--stations", default="results/stations.json")
    ap.add_argument("--out", default="viewer/status.json")
    ap.add_argument("--now", type=int, default=None)
    a = ap.parse_args()
    if a.feed:
        feed = json.load(open(a.feed))
    else:
        req = urllib.request.Request(FEED, headers={"User-Agent": "subway-surf-status/1.0"})
        feed = json.load(urllib.request.urlopen(req, timeout=60))
    rows = json.load(open(a.route))["rows"]; stations = json.load(open(a.stations))
    status = check(feed, rows, stations, a.now or time.time())
    json.dump(status, open(a.out, "w"), indent=1)
    print(f"{status['verdict']}: {len(status['now'])} current issues, {len(status['next_run']['issues'])} planned during next run "
          f"({status['alerts_in_feed']} alerts in feed)")


if __name__ == "__main__":
    main()
