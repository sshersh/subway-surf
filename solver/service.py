"""Apply service changes (from status/alerts.py) to weekday trips.

A trip is a list of stop times (seq, station, arr, dep, platform) in order, with times in seconds
after the service day's midnight. For one service day:
  skip  drops the stop: the train runs straight from the stop before to the stop after
  cut   drops the stop and splits the trip there: you can't ride through
A change targets (line, station, direction) triples; direction None means both. A "between A and B"
cut only applies to stations the trip passes between A and B. Used by model.py (to build the
timetable the solver plans on) and verify.py (to check a route against the same timetable), so both
always agree on what runs.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ALIAS = {"6X": "6", "7X": "7", "FX": "F", "5X": "5", "SS": "SI"}


def line_of(route_id):
    r = (route_id or "").strip().upper()
    return ALIAS.get(r, r)


def complexes(stops, transfers):
    """Stations that are one complex under two GTFS IDs (same name, linked by a transfer), e.g.
    Delancey St-Essex St: F15 for the F, M18 for the J/M/Z. Alerts may use either ID for any line."""
    parent = {s["stop_id"]: (s["parent_station"] or s["stop_id"]) for s in stops}
    name = {s["stop_id"]: s["stop_name"] for s in stops}
    same = {}
    for t in transfers:
        a, b = parent.get(t["from_stop_id"]), parent.get(t["to_stop_id"])
        if a and b and a != b and name.get(a) == name.get(b):
            g = same.get(a, {a}) | same.get(b, {b})
            for x in g: same[x] = g
    return same


class Changes:
    def __init__(self, path):
        d = json.load(open(path)) if isinstance(path, str) else path
        self.raw = d
        y, m, dd = map(int, d["run_date"].split("-"))
        self.days = [datetime(y, m, dd, tzinfo=ET) + timedelta(days=k) for k in (0, 1)]
        self.items = []
        for c in d["changes"]:
            tg = {}
            for ln, st, di in c["targets"]:
                tg.setdefault((ln, st), set()).add(di)
            ends = [set(c["ends"][0]), set(c["ends"][1])] if c.get("ends") else None
            self.items.append([c["effect"], tg, {ln for ln, _ in tg}, ends, c["when"], None])
        self.lines = set().union(*(it[2] for it in self.items)) if self.items else set()

    def link(self, same):
        """Let every station ID in a complex stand for the others (see complexes())."""
        ex = lambda ids: set().union(*(same.get(x, {x}) for x in ids)) if ids else set()
        for it in self.items:
            tg = {}
            for (ln, st), dirs in it[1].items():
                for x in same.get(st, {st}): tg.setdefault((ln, x), set()).update(dirs)
            it[1] = tg
            if it[3]: it[3] = [ex(it[3][0]), ex(it[3][1])]

    def learn(self, trips):
        """trips: (route_id, [station, ...]) for every trip. For each "between A and B" change, collect
        the stations trips pass between A and B, for trips that don't reach both ends themselves."""
        trips = list(trips)
        for it in self.items:
            if not it[3]: continue
            span = set()
            for route_id, stations in trips:
                ln = line_of(route_id)
                if ln not in it[2] and None not in it[2]: continue
                pa = [i for i, s in enumerate(stations) if s in it[3][0]]
                pb = [i for i, s in enumerate(stations) if s in it[3][1]]
                if pa and pb:
                    lo, hi = sorted((pa[0], pb[0])); span.update(stations[lo + 1:hi])
            it[5] = span or None

    def __bool__(self):
        return bool(self.items)

    def _active(self, when, t, day):
        if when == "always": return True
        w = (self.days[day] + timedelta(seconds=t)).timestamp()
        return any(s <= w < e for s, e in when)

    def apply(self, stops, route_id, direction, day):
        """Return the trip as a list of runnable pieces (each with at least two stops), plus counts."""
        line, direction = line_of(route_id), int(direction)
        if line not in self.lines and None not in self.lines:
            return [stops], 0, 0
        stations = [s[1] for s in stops]
        rules = []
        for eff, tg, ls, ends, when, span in self.items:
            if line not in ls and None not in ls: continue
            hit = {st for (ln, st), dirs in tg.items() if ln in (line, None) and (None in dirs or direction in dirs)}
            if not hit: continue
            if ends:   # only stations this trip passes strictly between the two ends
                pa = [i for i, s in enumerate(stations) if s in ends[0]]
                pb = [i for i, s in enumerate(stations) if s in ends[1]]
                if pa and pb:
                    lo, hi = sorted((pa[0], pb[0]))
                    hit &= set(stations[lo + 1:hi])
                elif span is not None:   # e.g. a short-turn trip: use the stretch other trips show
                    hit &= span
            if hit: rules.append((eff, hit, when))
        if not rules:
            return [stops], 0, 0
        pieces, cur, nskip, ncut = [], [], 0, 0
        for st in stops:
            eff = None
            for e, hit, when in rules:
                if st[1] in hit and self._active(when, st[2], day):
                    eff = e
                    if e == "cut": break
            if eff == "cut":
                ncut += 1
                if len(cur) >= 2: pieces.append(cur)
                cur = []
            elif eff == "skip":
                nskip += 1
            else:
                cur.append(st)
        if len(cur) >= 2: pieces.append(cur)
        return pieces, nskip, ncut
