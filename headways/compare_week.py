"""Compare last week's actual subway headways (subwaydata.nyc, built from the MTA GTFS-realtime
feeds) with the scheduled ones from the static GTFS. Runs in GitHub Actions (needs internet).

    python3 headways/compare_week.py --days 7 --out headways/results

Writes to --out:
  scheduled_hourly.json   scheduled headways  {"line|dir|station|day_type|hour": {n, mean, wait}}
  observed_hourly.json    observed headways, same keys, pooled over the days
  by_line.json, by_station.json   summaries (see headways.summarize)
  report.md               readable summary
"""
import argparse, io, json, os, sys, tarfile, urllib.request, zipfile, collections, statistics
sys.path.insert(0, os.path.dirname(__file__))
from headways import scheduled_headways, observed_headways, to_json, compare, summarize

META = "https://data.subwaydata.nyc/subwaydatanyc_metadata.json"
GTFS = "https://rrgtfsfeeds.s3.amazonaws.com/gtfs_subway.zip"
UA = {"User-Agent": "subway-surf-headways/1.0"}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()

ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=7); ap.add_argument("--out", default="headways/results")
ap.add_argument("--gtfs-dir", default="_gtfs")
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)

# static GTFS (CSV)
if not os.path.exists(os.path.join(a.gtfs_dir, "stop_times.txt")):
    zipfile.ZipFile(io.BytesIO(get(GTFS))).extractall(a.gtfs_dir)
names = {}
for r in __import__("csv").DictReader(open(os.path.join(a.gtfs_dir, "stops.txt"), encoding="utf-8-sig")):
    names[r["stop_id"]] = r["stop_name"]

# last N processed days
meta = json.loads(get(META))
days = sorted(meta["ProcessedDays"], key=lambda d: d["Day"])[-a.days:]
obs = {}
used = []
for d in days:
    path = d.get("Csv", {}).get("Path") or f"subwaydatanyc_{d['Day']}_csv.tar.xz"
    for url in (f"https://data.subwaydata.nyc/{path}", f"https://subwaydata.nyc/data/{os.path.basename(path)}"):
        try:
            blob = get(url); break
        except Exception as e:
            print("  failed", url, e); blob = None
    if blob is None: continue
    tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:xz")
    files = {os.path.basename(m.name): m for m in tf.getmembers() if m.isfile()}
    trips = next(v for k, v in files.items() if k.endswith("trips.csv"))
    st = next(v for k, v in files.items() if k.endswith("stop_times.csv"))
    observed_headways(tf.extractfile(st).read().decode(), tf.extractfile(trips).read().decode(), obs)
    used.append(d["Day"]); print("processed", d["Day"], len(blob) // 1_000_000, "MB", flush=True)

sched = {}
for dt in sorted({k[3] for k in obs}):
    scheduled_headways(a.gtfs_dir, dt, sched)

rows = compare(sched, obs)
by_line = summarize(rows, "line"); by_station = summarize(rows, "station")
for k, v in by_station.items(): v["name"] = names.get(k, k)
json.dump(to_json(sched), open(os.path.join(a.out, "scheduled_hourly.json"), "w"), separators=(",", ":"))
json.dump(to_json(obs), open(os.path.join(a.out, "observed_hourly.json"), "w"), separators=(",", ":"))
json.dump(by_line, open(os.path.join(a.out, "by_line.json"), "w"), indent=1)
json.dump(by_station, open(os.path.join(a.out, "by_station.json"), "w"), indent=1)

# report
tot = len(rows)
allr = sorted(r["obs_mean"] / r["sched_mean"] for r in rows)
L = [f"# Scheduled vs actual headways", "",
     f"Days: {', '.join(used)} (subwaydata.nyc, from the MTA GTFS-realtime feeds). Schedule: current static GTFS.", "",
     f"Compared {tot:,} line × direction × station × hour buckets with at least 4 observed gaps.", "",
     f"- Median actual/scheduled headway: **{allr[len(allr)//2]:.2f}**",
     f"- Within ±20% of schedule: **{sum(1 for x in allr if 0.8 <= x <= 1.2)/tot:.0%}** of buckets",
     f"- Average expected wait: scheduled ½ headway {statistics.mean(r['sched_mean']/2 for r in rows):.1f} min, "
     f"actual {statistics.mean(r['obs_wait'] for r in rows):.1f} min (actual wait includes uneven spacing)", "",
     "## By line", "", "| Line | Buckets | Median ratio | Within ±20% | ½ sched headway | Actual wait | Extra wait |", "|---|---|---|---|---|---|---|"]
for k, v in sorted(by_line.items(), key=lambda kv: -kv[1]["extra_wait_min"]):
    L.append(f"| {k} | {v['station_hours']} | {v['median_ratio']:.2f} | {v['within_20pct']:.0%} | {v['sched_half_hw_min']:.1f} | {v['obs_wait_min']:.1f} | {v['extra_wait_min']:+.1f} |")
L += ["", "## Stations with the most extra wait (≥ 30 buckets)", "", "| Station | Buckets | Median ratio | Within ±20% | Extra wait |", "|---|---|---|---|---|"]
for k, v in sorted(((k, v) for k, v in by_station.items() if v["station_hours"] >= 30), key=lambda kv: -kv[1]["extra_wait_min"])[:20]:
    L.append(f"| {v['name']} ({k}) | {v['station_hours']} | {v['median_ratio']:.2f} | {v['within_20pct']:.0%} | {v['extra_wait_min']:+.1f} |")
L += ["", "## By hour (all lines)", "", "| Hour | Buckets | Median ratio | ½ sched headway | Actual wait |", "|---|---|---|---|---|"]
byh = collections.defaultdict(list)
for r in rows: byh[r["hour"]].append(r)
for h in sorted(byh):
    v = byh[h]; rr = sorted(r["obs_mean"] / r["sched_mean"] for r in v)
    L.append(f"| {h:02d}:00 | {len(v)} | {rr[len(rr)//2]:.2f} | {statistics.mean(r['sched_mean']/2 for r in v):.1f} | {statistics.mean(r['obs_wait'] for r in v):.1f} |")
open(os.path.join(a.out, "report.md"), "w").write("\n".join(L) + "\n")
print("\n".join(L[:12]))
