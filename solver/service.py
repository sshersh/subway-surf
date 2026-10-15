"""Apply service changes (from status/alerts.py) to weekday trips.

A trip is a list of stop times (seq, station, arr, dep, platform) in order, with times in seconds
after the service day's midnight. For one service day:
  skip  drops the stop: the train runs straight from the stop before to the stop after
  cut   drops the stop and splits the trip there: you can't ride through
Used by model.py (to build the timetable the solver plans on) and verify.py (to check a route
against the same timetable), so both always agree on what runs.
"""
import json, math, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BOROUGH = {"manhattan": (40.754, -73.984), "brooklyn": (40.650, -73.950), "queens": (40.730, -73.820),
           "bronx": (40.850, -73.870), "the bronx": (40.850, -73.870)}
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
        self.items = [(c["effect"], set(c["lines"]), set(c["stops"]), c["when"], {}) for c in d["changes"]]
        self.texts = [c.get("text", "") for c in d["changes"]]
        self.lines = set().union(*(l for _, l, _, _, _ in self.items)) if self.items else set()
        self.all_lines = any(not l for _, l, _, _, _ in self.items)

    def resolve_directions(self, patterns, coords, names):
        """Alerts usually name parent stations and give the direction only in words ("Woodlawn-bound [4]
        skips Burnside Av"). Work out which platform direction (N/S suffix) each line's change applies to,
        so the other direction keeps stopping. patterns: {(line, 'N'|'S'): [station lists of trips]};
        coords: station -> (lat, lon); names: station -> name. Returns [(text, line, suffix)] resolved."""
        out = []
        for i, (eff, lines, stops, when, dirs) in enumerate(self.items):
            text = re.sub(r"\[([A-Z0-9]+)\]", r"\1", self.texts[i] or "")
            if re.search(r"both directions", text, re.I): continue
            m = re.search(r"([A-Za-z0-9 .'/]+?)-bound", text) or re.search(r"\b(uptown|downtown|northbound|southbound)\b", text, re.I)
            if not m: continue
            phrase = m.group(1).strip().lower()
            for line in lines:
                score = {}
                for d in "NS":
                    trips = [v for v in patterns.get((line, d), []) if stops & set(v)]
                    if not trips: continue
                    v = max(trips, key=len); k = max(j for j, x in enumerate(v) if x in stops)
                    down = v[k + 1:] or v[-1:]
                    if phrase in BOROUGH:
                        la, lo = BOROUGH[phrase]; t = coords[v[-1]]
                        score[d] = -math.hypot(t[0] - la, (t[1] - lo) * 0.76)
                    elif phrase in ("uptown", "northbound"): score[d] = coords[down[-1]][0] - coords[v[k]][0]
                    elif phrase in ("downtown", "southbound"): score[d] = coords[v[k]][0] - coords[down[-1]][0]
                    else: score[d] = 1 if any(phrase in names[x].lower() for x in down) else 0
                if len(score) == 2 and score["N"] != score["S"]:
                    dirs[line] = max(score, key=score.get); out.append((text[:80], line, dirs[line]))
        return out

    def __bool__(self):
        return bool(self.items)

    def effect(self, line, station, platform, t, day):
        """'cut', 'skip' or None for a train on `line` at `station` t seconds into service day `day`."""
        best = None
        for eff, lines, stops, when, dirs in self.items:
            if lines and line not in lines: continue
            if station not in stops and platform not in stops: continue
            if line in dirs and not platform.endswith(dirs[line]): continue   # the other direction runs normally
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


def resolve(changes, seqs, route_of, stops):
    """Resolve worded directions for a Changes object from the weekday trips.
    seqs: trip -> [(seq, station, arr, dep, platform)], route_of: trip -> route id, stops: GTFS stops."""
    import collections
    pats = collections.defaultdict(set)
    for t, v in seqs.items():
        d = v[0][4][-1:]
        if d in "NS": pats[(line_of(route_of[t]), d)].add(tuple(x[1] for x in v))
    pats = {k: [list(x) for x in v] for k, v in pats.items()}
    xy = {s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"])) for s in stops}
    nm = {s["stop_id"]: s["stop_name"] for s in stops}
    return changes.resolve_directions(pats, xy, nm)

