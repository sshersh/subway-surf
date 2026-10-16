"""Simulated annealing on the robust objective (robust.py): plan time + weight x expected miss cost,
with the hard minimum-slack rule at boardings. Same arguments as sa2.py/sax.py (see anneal.py), plus
    --local        local rules (default: express rules, passing through counts)
    --weight W     weight of the expected miss cost (default 1.0; 0 = plan time only)
    --soft         no hard minimum slack (penalty only)
    --model PATH   model prefix (default: model)
"""
import sys
from functools import partial
from robust import FastR
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
main(partial(FastR, model, express=not local, weight=weight, hard=not soft))
