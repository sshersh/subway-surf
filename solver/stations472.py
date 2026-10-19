"""The official 472-station count (Guinness / MTA), as opposed to GTFS's 475 parent stations.

GTFS gives three single stations one parent per line, at identical coordinates:
Queensboro Plaza (7 / N W), 145 St (A C / B D) and W 4 St-Wash Sq (A C E / B D F M).
The MTA's 472 counts each as one station, so the challenge needs only one stop there.
Set MERGE_472=1 in the environment to merge them (model.py, passes.py, verify.py read it), so a
change between the two lines there is a same-station change.
"""
import os
MERGE = {"R09": "718", "D13": "A12", "D20": "A32"}
ON = os.environ.get("MERGE_472") == "1"


def alias(p):
    return MERGE.get(p, p) if ON else p
