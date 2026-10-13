"""Embed map data, the best routes and every logged solver run into the viewer as a standalone page.

usage: python3 viewer/build.py <data.json from prep.py> <local route.json> <out.html> [<express route.json>]
"""
import json, sys, os

HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
        'body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>'
        '</head><body>')
data_path, route_path, out = sys.argv[1:4]
d = json.load(open(data_path)); d.pop("sample", None)
d["solutions"] = {"local": json.load(open(route_path))}
if len(sys.argv) > 4:
    d["solutions"]["express"] = json.load(open(sys.argv[4]))
# every logged solver run (results/runs), for the run picker
runs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "runs")
if os.path.exists(os.path.join(runs_dir, "index.json")):
    d["runs"] = [dict(r, route=json.load(open(os.path.join(runs_dir, r["file"]))))
                 for r in json.load(open(os.path.join(runs_dir, "index.json")))]
tpl = open(os.path.join(os.path.dirname(__file__), "template.html")).read()
page = tpl.replace("__DATA__", json.dumps(d, separators=(",", ":")).replace("</", "<\\/"))
open(out, "w").write(HEAD + page + "</body></html>")
print("wrote", out)
