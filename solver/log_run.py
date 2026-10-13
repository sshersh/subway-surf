"""Add a solved route to the run log (results/runs/).

    python3 log_run.py <route.json> --label "Time-aware planner, round 2" --method "..." \
        [--transfers "1 min"] [--start-fixed "Nostrand Av"] [--created 2026-10-12T20:40:00-07:00]

Each run is stored as results/runs/<id>.json (the exported route) and listed in
results/runs/index.json, newest last. The viewer embeds every logged run for comparison.
"""
import argparse, json, os, re
from datetime import datetime, timezone

ap = argparse.ArgumentParser()
ap.add_argument("route"); ap.add_argument("--label", required=True); ap.add_argument("--method", default="")
ap.add_argument("--transfers", default="1 min"); ap.add_argument("--start-fixed", default="")
ap.add_argument("--created", default=None)
ap.add_argument("--runs", default=os.path.join(os.path.dirname(__file__), "..", "results", "runs"))
a = ap.parse_args()
route = json.load(open(a.route)); s = route["stats"]
created = a.created or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
rules = s.get("rules", "local")
os.makedirs(a.runs, exist_ok=True)
idx_path = os.path.join(a.runs, "index.json")
index = json.load(open(idx_path)) if os.path.exists(idx_path) else []
rid = re.sub(r"[^0-9]", "", created[:16]) + "-" + rules
n = sum(1 for r in index if r["id"].startswith(rid))
if n: rid += f"-{n + 1}"
json.dump(route, open(os.path.join(a.runs, rid + ".json"), "w"), separators=(",", ":"))
entry = {"id": rid, "created": created, "rules": rules, "label": a.label, "method": a.method,
         "transfers": a.transfers, "start_fixed": a.start_fixed, "total_s": s["total_s"],
         "start": s["start"], "end": s["end"], "start_station": s["start_station"], "end_station": s["end_station"],
         "rides": s["rides"], "walks": s["walks"], "passed_only": s.get("passed_only", 0), "file": rid + ".json"}
index.append(entry)
json.dump(index, open(idx_path, "w"), indent=1)
h, m = divmod(s["total_s"] // 60, 60)
print(f"logged {rid}: {rules} {h}:{m:02d} — {a.label}")
