"""Summarise where adaptive real-day runs lose time against the plan.

    python3 headways/attribute.py results/adaptive_runs.json [label ...]

Per run, total loss = real finish - plan. Each executed boarding records its new loss against the
rider's current plan: `wait` (left later than max(ready, planned departure) on the planned line: a
later train of the planned line), `run` (real ride time minus planned ride time), `replaced`
(planned line not running / skipped / rerouted: arrival by other trains minus the planned arrival).
Walks are deterministic in the model. The rest is the re-plan residual: after a disruption the
re-planned remainder takes longer than the original remainder (cascade into sparser service, mostly
at night). Prints totals by cause, by night (23:00-06:00) vs day and by line, and the worst boardings.
"""
import json, sys, collections, statistics

d = json.load(open(sys.argv[1]))
labels = sys.argv[2:] or list(d)
hm = lambda s: f"{'-' if s < 0 else ''}{abs(int(s)) // 3600}:{abs(int(s)) % 3600 // 60:02d}"
for lab in labels:
    R = d[lab]; runs = [r for r in R["runs"] if "loss" in r]
    if not runs: continue
    n = len(runs)
    cause = collections.Counter(); night = collections.Counter(); line = collections.Counter(); worst = []
    resid = 0
    for r in runs:
        tot = r["raw_finish_s"] - R["plan_s"]
        s = 0
        for k, ln, nt, x, t, a, b in r["loss"]:
            cause[k] += x; night[("night" if nt else "day", k)] += x; line[ln] += x; s += x
            worst.append((x, k, ln, a, b, t, r["day"], r["offset"]))
        resid += tot - s
    print(f"== {lab}: plan {hm(R['plan_s'])}, mean loss per run {hm(sum(r['raw_finish_s'] - R['plan_s'] for r in runs) / n)} over {n} runs")
    for k in ("wait", "run", "replaced"):
        print(f"   {k:9s} {hm(cause[k] / n)}  (day {hm(night[('day', k)] / n)}, night {hm(night[('night', k)] / n)})")
    print(f"   re-plan residual {hm(resid / n)}")
    print("   by line (wait+run+replaced, per run):", ", ".join(f"{k} {round(v / n / 60)}m" for k, v in line.most_common(10)))
    print("   worst single boardings:")
    for x, k, ln, a, b, t, day, off in sorted(worst, reverse=True)[:5]:
        print(f"     +{round(x / 60)} min {k} {ln} {a} -> {b} at {hm(t)} ({day} {off:+d})")
