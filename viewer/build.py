"""Embed map data, the best routes and every logged solver run into the viewer as a standalone page.

usage: python3 viewer/build.py <data.json from prep.py> <local route.json> <out.html> [<express route.json>] [--plan plan.json]

With --plan (from solver/plan.py), the two routes are the plan for current service: they're added to
the run picker as "Current service" and shown first, and the page lists the service changes behind them.
"""
import json, sys, os

HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
        'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>')
args = sys.argv[1:]
plan = None
if "--plan" in args:
    i = args.index("--plan"); plan = json.load(open(args[i + 1])); del args[i:i + 2]
data_path, route_path, out = args[:3]
d = json.load(open(data_path)); d.pop("sample", None)
d["solutions"] = {"local": json.load(open(route_path))}
if len(args) > 3:
    d["solutions"]["express"] = json.load(open(args[3]))
# every logged solver run (results/runs), for the run picker
runs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "runs")
if os.path.exists(os.path.join(runs_dir, "index.json")):
    d["runs"] = [dict(r, route=json.load(open(os.path.join(runs_dir, r["file"]))))
                 for r in json.load(open(os.path.join(runs_dir, "index.json")))]
if plan is not None:
    d["plan"] = plan
    if not plan.get("error"):
        d.setdefault("runs", [])
        for rules, route in d["solutions"].items():
            d["runs"].insert(0, {"id": "current-" + rules, "rules": rules, "current": True, "label": "Current service",
                                 "created": __import__("datetime").datetime.fromtimestamp(plan["solved_at"], __import__("datetime").timezone.utc).isoformat(),
                                 "method": f"Planned on the timetable with {len(plan.get('changes', []))} service changes for {plan['run_date']}",
                                 "transfers": "1 min", "route": route, "total_s": route["stats"]["total_s"]})
tpl = open(os.path.join(os.path.dirname(__file__), "template.html")).read()
page = tpl.replace("__DATA__", json.dumps(d, separators=(",", ":")).replace("</", "<\\/"))
open(out, "w").write(HEAD + page + "</body></html>")
print("wrote", out)
