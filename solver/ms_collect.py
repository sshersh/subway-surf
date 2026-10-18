"""Rank multi-start results and summarise convergence.

    python3 solver/ms_collect.py --in DIR [DIR ...] --rules express|local [--top K --elites OUTDIR] [--md out.md]

Reads every job*.json under the input dirs (rows written by multistart.py), keeps rows for the given
rules, copies the K best solutions to --elites (for stage-2 refinement) and prints/writes a summary:
spread of results, best by seed and by start window, and how fast starts converged.
"""
import sys, os, json, glob, shutil, statistics as S


def opt(name, default, n=1):
    if name in sys.argv:
        i = sys.argv.index(name)
        if n == "*":
            j = i + 1
            while j < len(sys.argv) and not sys.argv[j].startswith("--"): j += 1
            v = sys.argv[i + 1:j]; del sys.argv[i:j]; return v
        v = sys.argv[i + 1]; del sys.argv[i:i + 2]; return v
    return default


dirs = opt("--in", [], "*"); rules = opt("--rules", "express"); top = int(opt("--top", 8))
eo = opt("--elites", None); md = opt("--md", None)
rows = []
for d in dirs:
    for f in glob.glob(f"{d}/**/job*.json", recursive=True):
        for r in json.load(open(f)):
            if r.get("rules") == rules and r.get("best_h"):
                r["path"] = os.path.join(os.path.dirname(f), r["file"]); r["stage"] = "refine" if "refine" in f else "search"
                rows.append(r)
rows.sort(key=lambda r: r["best_h"])
if not rows: raise SystemExit(f"no results for {rules}")
if eo:
    os.makedirs(eo, exist_ok=True)
    for i, r in enumerate(rows[:top]): shutil.copy(r["path"], f"{eo}/elite{i}.npy")


def hm(h): return f"{int(h)}:{round(h % 1 * 60):02d}"


def conv(r):
    """minutes until the start was within 3 min of its final objective"""
    for t, b in r.get("trace", []):
        if b - r["best_h"] <= 0.05: return t
    return None


b = [r["best_h"] for r in rows]
L = [f"## {rules}: {len(rows)} starts", "",
     f"Objective (h): best {hm(b[0])}, 10th pct {hm(b[len(b)//10])}, median {hm(S.median(b))}, worst {hm(b[-1])}.",
     "(express = robust objective: plan time + expected miss cost; local = plan time)", "",
     "| Rank | Stage | Objective | Seed | Kick | Window | Start t0 |", "|---|---|---|---|---|---|---|"]
for i, r in enumerate(rows[:10]):
    L.append(f"| {i+1} | {r['stage']} | {hm(r['best_h'])} | {r['base']} | {r['kick']} | {r['window'][0]}-{r['window'][1]} h | {r['t0_h']:.2f} |")
for key, name in (("base", "seed"), ("window", "start window")):
    g = {}
    for r in rows: g.setdefault(str(r[key]), []).append(r["best_h"])
    L += ["", f"Best by {name}: " + "; ".join(f"{k} {hm(min(v))} (n={len(v)})" for k, v in sorted(g.items(), key=lambda kv: min(kv[1])))]
c = [x for x in map(conv, rows) if x is not None]
if c:
    L += ["", f"Convergence: median start was within 3 min of its final result after {S.median(c):.0f} min "
              f"(90th pct {sorted(c)[int(len(c)*.9)]:.0f} min)."]
txt = "\n".join(L)
print(txt)
if md: open(md, "a").write(txt + "\n\n")
json.dump(rows[0], open(f"best_{rules}.json", "w"))
print("BEST", rows[0]["path"])
