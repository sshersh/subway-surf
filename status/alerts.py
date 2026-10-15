"""Turn MTA subway alerts into service changes the solver can plan around.

    python3 status/alerts.py --out changes.json                    # fetch the live feed
    python3 status/alerts.py --feed alerts.json --now 1791847300   # offline / testing

Alerts of these types become changes, each a set of (line, station, direction) targets:
  skip  Stops Skipped, Local to Express: trains run but don't stop there
  cut   Suspended, Part Suspended, Station Closed: trains don't run through there at all;
        a trip is split where it is cut
Each alert lists the whole stretch it touches, including stations still served at either end, so the
headline picks the targets: "skips X, Y and Z" -> X, Y, Z; "runs express from A to B" and
"no [M] between A and B" -> the listed stations except A and B; "no [7] at S" -> S; anything else
("[C] service ends early") -> every listed station. Express-to-local changes add stops, which the
model can't do, so they're ignored; they only help.

When a change applies, on the run day (the next weekday after today, New York time):
  unplanned alerts active now   all day: the plan assumes current disruptions last the whole run
  everything else               only during the alert's active periods
Alerts that name no stations, reroutes and delays can't be modeled; they're listed under
"not_modeled" so the banner can still show them.

"hash" covers only what changes the timetable (run day, effect, lines, stops, times), so reworded
or re-issued alerts don't trigger a new solve.
"""
import argparse, hashlib, json, os, re, sys, time, urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_status import FEED, ET, classify, line_of, text_of

# alert types (without "Planned - ") that change which stops trains make, and how
SKIP_TYPES = ("stops skipped", "local to express")
CUT_TYPES = ("part suspended", "suspended", "no scheduled service", "station closed")
BOROUGH = re.compile(r",\s*(upper |lower )?(manhattan|bronx|brooklyn|queens|staten island)\b.*$", re.I)


def norm(name):
    n = re.sub(r"[\u2013\u2014/()\-]", " ", name.lower())
    return " ".join(n.replace("'", "").split())


def find(phrase, cands):
    """Stations among cands (id -> name) that a headline phrase names: exact, else prefix either way."""
    h = norm(BOROUGH.sub("", phrase.strip(" .")))
    if not h: return set()
    exact = {s for s, n in cands.items() if norm(n) == h}
    if exact: return exact
    pre = {s for s, n in cands.items() if norm(n).startswith(h + " ") or h.startswith(norm(n) + " ")}
    if len(pre) == 1: return pre
    if "/" in phrase:   # "Utica Av/New Lots Av": either branch end
        return set().union(*(find(x, cands) for x in phrase.split("/")))
    return set()


def names_in(text, cands):
    out = set()
    for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", text):
        out |= find(part, cands)
    return out


def raw_text(ts):
    """English header text with its line breaks (check_status.text_of collapses them)."""
    tr = (ts or {}).get("translation", []) if isinstance(ts, dict) else []
    for t in tr:
        if (t.get("language") or "en").lower() == "en": return (t.get("text") or "").strip()
    return text_of(ts)


def between(lines, ends, order):
    """Stations trains on these lines pass strictly between the two ends (results/line_order.json),
    or None if no stop pattern runs through both."""
    same = order.get("complexes", {})
    ex = lambda ids: set().union(*(set(same.get(x, [x])) for x in ids))
    ea, eb, span = ex(ends[0]), ex(ends[1]), set()
    for ln in lines:
        for p in order.get("lines", {}).get(ln, []):
            pa = [i for i, s in enumerate(p) if s in ea]; pb = [i for i, s in enumerate(p) if s in eb]
            if pa and pb:
                lo, hi = sorted((pa[0], pb[0])); span.update(p[lo + 1:hi])
    return ex(span) if span else None


def affected(alert_type, header, entities, names, lines=(), line_stations=None, order=None):
    """(effect, ends, [(line, station, direction or None)]) for one alert, or (None, None, why).
    ends: for "between A and B", the station IDs named as each end. service.py then cuts only the
    stations a trip passes between them (alert lists aren't reliably in line order).

    entities: (line, station, direction) triples from informed_entity. They cover the whole affected
    stretch, including stations still served at either end, so the headline decides which of them are
    skipped or cut."""
    base = (alert_type or "").lower().replace("planned - ", "").strip()
    first = (header or "").split("\n")[0]
    whole_line = not entities
    if whole_line and lines and line_stations:
        # the alert names its lines only: look for the headline's stations on those lines, both directions
        entities = [(ln, st, None) for ln in lines for st in line_stations.get(ln, ())]
    cands = {st: names.get(st, st) for _, st, _ in entities}
    ends = None
    m_exp = re.search(r"express from (.+?) to (.+?)(?:$| and | - |\.)", first, re.I)
    if base in SKIP_TYPES:
        if m_exp:   # the listed stations are the ones skipped, plus the two ends
            hit = set() if whole_line else set(cands) - find(m_exp.group(1), cands) - find(m_exp.group(2), cands)
        else:
            m = re.search(r"\bskips?\b(.*)$", first, re.I)
            hit = names_in(re.split(r"\s+(?:in both directions|- take|and runs|on weekdays)", m.group(1))[0], cands) if m else set()
        eff = "skip"
    elif base in CUT_TYPES:
        m_btw = re.search(r"\bbetween (.+?) and (.+?)$", first, re.I)
        m_at = re.search(r"\bno \[\w+\](?: service)? at (.+?)$", first, re.I)
        if m_btw:
            ea, eb = find(m_btw.group(1), cands), find(m_btw.group(2), cands)
            hit = set(cands) - ea - eb
            if ea and eb:
                ends = [sorted(ea), sorted(eb)]
                span = between({ln for ln, _, _ in entities if ln} or set(lines), ends, order) if order else None
                if span is not None: hit &= span
        elif m_at:
            hit = find(m_at.group(1), cands)
        else:
            hit = set(cands)   # e.g. "[C] service ends early": the whole line for that time
        eff = "cut"
    else:
        return None, None, "type"
    if not hit:
        return None, None, "unmatched"
    return eff, ends, sorted({(ln, st, d) for ln, st, d in entities if st in hit}, key=lambda x: (x[0] or "", x[1], -1 if x[2] is None else x[2]))


_ORDER = []
def line_order():
    """results/line_order.json, if present (status/line_order.py writes it)."""
    if not _ORDER:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "line_order.json")
        _ORDER.append(json.load(open(p)) if os.path.exists(p) else None)
    return _ORDER[0]


def entities_of(a, stations):
    out, lines = [], set()
    for ie in a.get("informed_entity", []):
        ln = line_of(ie["route_id"]) if ie.get("route_id") else None
        if ln: lines.add(ln)
        s = (ie.get("stop_id") or "").strip().upper()
        st = s if s in stations else s[:-1] if s[:-1] in stations and s[-1:] in ("N", "S") else None
        if st and ln != "SI":
            d = ie.get("direction_id")
            if d is None and s != st: d = 0 if s.endswith("N") else 1
            out.append((ln, st, None if d is None else int(d)))
    lines.discard("SI")
    return out, lines


def run_day(now):
    """Next weekday after today, New York time: a run can still start at any hour that day."""
    d = datetime.fromtimestamp(now, ET).date()
    for i in range(1, 8):
        day = d + timedelta(days=i)
        if day.weekday() < 5: return day
    return None


def changes_from(feed, stations, now, line_stations=None):
    """stations: {station id: name}; line_stations: {line: [station ids]}."""
    day = run_day(now)
    day0 = datetime(day.year, day.month, day.day, tzinfo=ET)
    lo, hi = day0.timestamp(), (day0 + timedelta(days=2)).timestamp()   # the model covers two service days
    out, skipped = [], []
    for e in feed.get("entity", []):
        a = e.get("alert")
        if not a: continue
        merc = a.get("transit_realtime.mercury_alert") or a.get("mercury_alert") or {}
        atype, header = merc.get("alert_type", ""), raw_text(a.get("header_text"))
        periods = [(int(p.get("start") or 0), int(p.get("end") or 0)) for p in a.get("active_period", [])] or [(0, 0)]
        ents, lines = entities_of(a, stations)
        planned = str(e.get("id", "")).startswith("lmm:planned") or atype.lower().startswith("planned")
        active_now = any(s <= now and (x == 0 or now <= x) for s, x in periods)
        overlaps = [[max(s, int(lo)), min(x, int(hi)) if x else int(hi)] for s, x in periods if s < hi and (x == 0 or x > lo)]
        if not (active_now and not planned) and not overlaps: continue   # not in force during the run
        eff, ends, hit = affected(atype, header, ents, stations, sorted(lines), line_stations, line_order())
        if not eff:
            kind = classify(atype, header)
            if lines and kind != "info":
                skipped.append({"id": e.get("id"), "kind": kind, "lines": sorted(lines), "text": header[:280], "type": atype})
            continue
        when = "always" if active_now and not planned else sorted(overlaps)
        out.append({"id": e.get("id"), "effect": eff, "lines": sorted({l for l, _, _ in hit if l}), "stops": sorted({s for _, s, _ in hit}),
                    "targets": [list(t) for t in hit], "ends": ends, "when": when, "planned": planned, "type": atype, "text": header[:280]})
    out.sort(key=lambda c: (c["effect"], c["lines"], c["stops"], str(c["when"])))
    key = json.dumps([str(day)] + [[c["effect"], c["targets"], c["ends"], c["when"]] for c in out], sort_keys=True)
    return {"run_date": str(day), "generated_at": int(now), "feed_timestamp": int(feed.get("header", {}).get("timestamp") or 0),
            "hash": hashlib.sha256(key.encode()).hexdigest()[:16], "changes": out, "not_modeled": skipped}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", help="alerts JSON file (default: fetch live)")
    ap.add_argument("--out", default="changes.json")
    ap.add_argument("--now", type=int, default=None)
    a = ap.parse_args()
    if a.feed:
        feed = json.load(open(a.feed))
    else:
        req = urllib.request.Request(FEED, headers={"User-Agent": "subway-surf-status/1.0"})
        feed = json.load(urllib.request.urlopen(req, timeout=60))
    st = json.load(open(os.path.join(os.path.dirname(__file__), "..", "results", "stations.json")))
    by_line = {}
    for k, v in st.items():
        for r in v["r"]: by_line.setdefault(line_of(r), []).append(k)
    ch = changes_from(feed, {k: v["n"] for k, v in st.items()}, a.now or time.time(), by_line)
    json.dump(ch, open(a.out, "w"), indent=1)
    print(f"run day {ch['run_date']}: {len(ch['changes'])} modeled changes, {len(ch['not_modeled'])} not modeled, hash {ch['hash']}")


if __name__ == "__main__":
    main()
