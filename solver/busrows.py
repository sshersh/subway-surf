"""Viewer rows and itinerary entries for bus legs (export.py, tidy.py).

A bus leg is a model connection with nxt == -2 whose times include the walk to the bus stop and from the
alighting stop. It is written like a walk in `rows` (route "", so the viewer draws a walk-like segment and
verify.py doesn't treat it as a train hop), tagged with "bus": the bus route, plus what verify.py needs to
check it against the bus schedule. It never makes the station it arrives at "visited".
"""


def is_bus(nxt, c):
    return nxt[c] == -2


def bus_info(meta, trip):
    """(bus route, bus trip id, day offset s, link dict) of a bus trip number"""
    i = int(trip) - meta["bus0"]
    tid, day, li = meta["bus_trip"][i]
    return meta["bus_route"][i], tid, day * 86400, meta["bus_links"][li]


def bus_leg(meta, hms, names, st, trip, dep_t, arr_t, a, b):
    """-> (row, itin entry) for the bus connection (trip, dep_t/arr_t include the walks) from station index a to b"""
    route, tid, off, L = bus_info(meta, trip)
    bd, ba = int(dep_t) + L["walk_in"], int(arr_t) - L["walk_out"]    # the bus's own departure and arrival
    row = {"stop_id": st[b], "time": hms(int(arr_t)), "route": "", "bus": route, "bus_trip": tid, "bus_day": off // 86400,
           "bus_from": L["stopA"], "bus_to": L["stopB"], "bus_dep": hms(bd), "bus_arr": hms(ba), "from_stop": st[a]}
    it = {"kind": "bus", "route": route, "from": names[a], "to": names[b], "t0": hms(int(dep_t)), "t1": hms(int(arr_t)),
          "bus_dep": hms(bd), "bus_arr": hms(ba), "stops": 0, "new": 0, "min": round((int(arr_t) - int(dep_t)) / 60)}
    return row, it
