"""Apply service changes (from status/alerts.py) to weekday trips.

A trip is a list of stop times (seq, station, arr, dep, platform) in order, with times in seconds
after the service day's midnight. For one service day:
  skip  drops the stop: the train runs straight from the stop before to the stop after
  cut   drops the stop and splits the trip there: you can't ride through
Used by model.py (to build the timetable the solver plans on) and verify.py (to check a route
against the same timetable), so both always agree on what runs.
"""
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ALIAS = {"6X": "6", "7X": "7", "FX": "F", "5X": "5", "SS": "SI"}


def line_of(route_id):
    r = (route_id or "").strip().upper()
    return ALIAS.get(r, r)


class Changes:
    def __init__(self, path):
        d = json.load(open(path)) if isinstance(path, str) else path
        self.raw = d
        y, m, dd = map(int, d["run_date"].split("-"))
        self.days = [datetime(y, m, dd, tzinfo=ET) + timedelta(days=k) for k in (0, 1)]
        self.items = [(c["effect"], set(c["lines"]), set(c["stops"]), c["when"]) for c in d["changes"]]
        self.lines = set().union(*(l for _, l, _, _ in self.items)) if self.items else set()
        self.all_lines = any(not l for _, l, _, _ in self.items)

    def __bool__(self):
        return bool(self.items)

    def effect(self, line, station, platform, t, day):
        """'cut', 'skip' or None for a train on `line` at `station` t seconds into service day `day`."""
        best = None
        for eff, lines, stops, when in self.items:
            if lines and line not in lines: continue
            if station not in stops and platform not in stops: continue
            if when != "always":
                w = (self.days[day] + timedelta(seconds=t)).timestamp()
                if not any(s <= w < e for s, e in when): continue
            if eff == "cut": return "cut"
            best = eff
        return best

    def apply(self, stops, route_id, day):
        """Return the trip as a list of runnable pieces (each with at least two stops), plus counts."""
        line = line_of(route_id)
        if not self.all_lines and line not in self.lines:
            return [stops], 0, 0
        pieces, cur, nskip, ncut = [], [], 0, 0
        for st in stops:
            _, station, arr, dep, platform = st
            eff = self.effect(line, station, platform, arr, day)
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
