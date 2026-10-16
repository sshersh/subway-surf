"""Simulated annealing on the robust objective (robust.py): plan time + weight x expected miss cost,
with the hard minimum-slack rule at boardings. Same arguments as sa2.py/sax.py (see anneal.py), plus
    --local        local rules (default: express rules, passing through counts)
    --weight W     weight of the expected miss cost (default 1.0; 0 = plan time only)
    --soft         no hard minimum slack (penalty only)
    --model PATH   model prefix (default: model)
    --tmin H --tmax H   allowed start-time window (hours)
    --night-pen S  extra cost (s) per boarding departing 00:00-05:30
"""
import sys
from functools import partial
from robust import FastR
import anneal
from anneal import main


def _opt(name, default, cast=str):
    if name in sys.argv:
        i = sys.argv.index(name); v = cast(sys.argv[i + 1]); del sys.argv[i:i + 2]; return v
    return default


def _flag(name):
    if name in sys.argv:
        sys.argv.remove(name); return True
    return False


local = _flag("--local"); soft = _flag("--soft")
weight = _opt("--weight", 1.0, float); model = _opt("--model", "model")
tmin = _opt("--tmin", None, float); tmax = _opt("--tmax", None, float); npen = _opt("--night-pen", 0.0, float)
if tmin is not None or tmax is not None:
    anneal.T_RANGE = (int((tmin or 0) * 3600), int((tmax if tmax is not None else 20) * 3600))
main(partial(FastR, model, express=not local, weight=weight, hard=not soft, night_pen=npen))
