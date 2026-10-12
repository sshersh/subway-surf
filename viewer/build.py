"""Embed map data + a solved route into the viewer template.

usage: python3 viewer/build.py <data.json from prep.py> <route.json from solver/export.py> <out.html>
"""
import json, sys, os
data_path, route_path, out = sys.argv[1:4]
d = json.load(open(data_path)); d.pop("sample", None)
d["solution"] = json.load(open(route_path))
tpl = open(os.path.join(os.path.dirname(__file__), "template.html")).read()
open(out, "w").write(tpl.replace("__DATA__", json.dumps(d, separators=(",", ":")).replace("</", "<\\/")))
print("wrote", out)
