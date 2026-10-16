"""Realistic transfer, walking/running and robustness assumptions (used by model.py, passes.py, robust.py).

All times are seconds. These are estimates of what a fit, experienced rider actually needs, platform to
platform at a brisk walk with fair crowding, not measurements. Sources: station layouts (levels,
island vs side platforms, passageway lengths) as published in MTA station diagrams and the station
articles on Wikipedia, cross-checked against the MTA's own `min_transfer_time` in transfers.txt (a
trip-planner allowance, usually 3 min). Where nothing better is known, the MTA figure is used.
See docs/realistic-model.md for the reasoning behind each number.
"""

# ---------------------------------------------------------------------------------------------
# Changing trains inside one GTFS station (same parent stop id). One value per station: the time
# for the slowest change a route is likely to make there (e.g. a reversal that needs the stairs, or
# express <-> local on a different level). Same-train continuations cost nothing.
SAME_DEFAULT = 120        # through station: reversing usually means stairs or a crossunder
SAME_TERMINAL = 60        # every train starts/ends here: arrivals and departures share an island
SAME = {
    # Broadway-7 Av (1/2/3): two islands, local/express cross-platform, reversal via mezzanine
    "120": 120, "123": 120, "127": 120, "132": 120, "137": 120,
    "128": 150,           # 34 St-Penn: 1 on side platforms, 2/3 on an island
    # Eastern Pkwy / Nostrand (2/3/4/5)
    "234": 120, "235": 150, "239": 120, "250": 150,
    "222": 120,           # 149 St-Grand Concourse 2/5
    # Lexington (4/5/6): two-level stations are slower
    "621": 150, "626": 150, "629": 150, "631": 120, "635": 150, "640": 150,
    # 8 Av / Fulton (A/C/E)
    "A09": 120, "A12": 150, "A15": 120, "A24": 150, "A27": 120, "A28": 150, "A31": 120, "A32": 120,
    "A34": 120, "A41": 120, "A42": 120, "A48": 120, "A51": 120, "A55": 90,
    # Concourse / 6 Av / Brighton (B/D/F/M/Q)
    "D03": 120, "D04": 120, "D05": 120, "D07": 120, "D13": 120, "D14": 150, "D15": 150, "D16": 120,
    "D17": 120, "D20": 120, "D21": 120, "D26": 150, "D28": 120, "D31": 120, "D35": 120, "D39": 120,
    "D40": 150, "D43": 180,
    # Queens Blvd / Culver / Archer
    "F06": 120, "F14": 150, "F24": 120, "F27": 120, "G08": 120, "G14": 120, "G21": 150,
    "G05": 180, "G06": 180,
    # Jamaica / Myrtle (J/M/Z)
    "J27": 90, "M11": 150, "M16": 90, "M18": 120,
    # Broadway / 4 Av / 63 St (N/Q/R/W)
    "R03": 120, "R11": 120, "R14": 120, "R16": 120, "R17": 120, "R20": 120, "R30": 120, "R31": 120,
    "R36": 120, "R41": 120, "B08": 150, "B12": 120, "B16": 120, "B21": 120, "Q03": 120, "Q04": 120, "Q05": 120,
    # 7 / 6 express-local pairs on one structure
    "707": 90, "712": 90, "718": 90, "608": 90, "613": 90, "619": 90,
}

# Linked stations (different GTFS parents, joined by a passageway or a short street walk):
# platform to platform, both directions. Pairs not listed fall back to the MTA min_transfer_time.
LINK = {
    ("112", "A09"): 300,  # 168 St: the 1 is elevator-only, very deep
    ("125", "A24"): 180,  # 59 St-Columbus Circle 1 <-> A/B/C/D
    ("127", "725"): 240, ("127", "902"): 180, ("127", "A27"): 360, ("127", "R16"): 180,   # Times Sq
    ("725", "902"): 240, ("725", "A27"): 300, ("725", "R16"): 240, ("902", "A27"): 360, ("902", "R16"): 180,
    ("A27", "R16"): 360,
    ("132", "D19"): 300, ("132", "L02"): 240, ("D19", "L02"): 120,   # 14 St / 6 Av passage
    ("A31", "L01"): 180,  # 14 St A/C/E <-> 8 Av L (MTA 90 s is optimistic)
    ("222", "415"): 180, ("414", "D11"): 180,  # 149 St-GC, 161 St
    ("228", "A36"): 180, ("228", "E01"): 240, ("228", "R25"): 360,   # Park Place / WTC / Cortlandt
    ("A36", "E01"): 180, ("A36", "R25"): 360, ("E01", "R25"): 300,
    ("229", "418"): 180, ("229", "A38"): 240, ("229", "M22"): 240,   # Fulton St (model had J<->A/C at 1:19)
    ("418", "A38"): 240, ("418", "M22"): 180, ("A38", "M22"): 240,
    ("232", "423"): 150, ("232", "R28"): 240, ("423", "R28"): 240,   # Borough Hall / Court St
    ("235", "D24"): 240, ("235", "R31"): 240, ("D24", "R31"): 240,   # Atlantic Av-Barclays
    ("239", "S04"): 150, ("A45", "S01"): 180,  # Franklin Av shuttle links
    ("254", "L26"): 300,  # Junius St <-> Livonia Av (street)
    ("629", "R11"): 180, ("629", "B08"): 300, ("B08", "R11"): 300,   # Lexington Av/59-63
    ("630", "F11"): 300,  # 51 St <-> Lexington Av/53 St: E/M platforms are very deep
    ("631", "723"): 240, ("631", "901"): 240, ("723", "901"): 300,   # Grand Central
    ("635", "L03"): 180, ("635", "R20"): 180, ("L03", "R20"): 180,   # Union Sq
    ("637", "D21"): 180,  # Bleecker St <-> Broadway-Lafayette
    ("639", "M20"): 180, ("639", "Q01"): 180, ("639", "R23"): 180,   # Canal St
    ("M20", "Q01"): 150, ("M20", "R23"): 240, ("Q01", "R23"): 180,
    ("640", "M21"): 180,  # Brooklyn Bridge <-> Chambers St (J/Z)
    ("710", "G14"): 180,  # 74 St <-> Jackson Hts-Roosevelt Av
    ("718", "R09"): 90,   # Queensboro Plaza: cross-platform one way, stairs the other
    ("719", "F09"): 300, ("719", "G22"): 240, ("F09", "G22"): 300,   # Court Sq (long passage)
    ("724", "D16"): 240,  # 5 Av (7, deep) <-> 42 St-Bryant Pk
    ("A12", "D13"): 150, ("A32", "D20"): 150,   # 145 St, W 4 St: two levels
    ("A41", "R29"): 150,  # Jay St-MetroTech
    ("A51", "J27"): 300, ("A51", "L22"): 300, ("J27", "L22"): 180,   # Broadway Junction
    ("B16", "N04"): 180, ("D17", "R17"): 150, ("F15", "M18"): 150, ("F23", "R33"): 240,
    ("G29", "L10"): 180, ("L17", "M08"): 180,
}
LINK_FLOOR = (60, 1.2)    # never below 60 s + straight-line metres / 1.2 m/s

# ---------------------------------------------------------------------------------------------
# Walking and running between stations over the street (not in-complex links above).
WALK_SPEED = 1.4          # m/s, brisk walk
RUN_SPEED = 2.5           # m/s effective jog including waits at crossings
RUN_FROM = 300            # m straight-line: shorter hops are walked; beyond this the rest is run
DETOUR = 1.3              # street-grid factor over straight line
WALK_MAX = 2000           # m straight-line cap for generated walking/running links
WALK_OVERHEAD = 120       # s to exit one station and enter the other


def street_time(d):
    """Seconds for a street walk/run of d metres straight-line, station to station (platform to platform).
    The first RUN_FROM metres are walked (getting out, crossing); the rest is run. Continuous in d."""
    w = min(d, RUN_FROM) * DETOUR / WALK_SPEED
    r = max(0.0, d - RUN_FROM) * DETOUR / RUN_SPEED
    return int(WALK_OVERHEAD + w + r)


# ---------------------------------------------------------------------------------------------
# Robustness: minimum slack to require at a boarding (hard rule), and the miss model.
NIGHT = (23 * 3600, 6 * 3600)   # 23:00-06:00: headways 20 min, planned work, slower trains


def is_night(t):
    s = t % 86400
    return s >= NIGHT[0] or s < NIGHT[1]


def board_buffer(hw, night):
    """Minimum slack (s) required beyond the realistic transfer time, given the headway hw (s) to the
    next equivalent train. A miss of a frequent train costs little, so no buffer there."""
    if hw >= 900: b = 180
    elif hw >= 600: b = 120
    elif hw >= 360: b = 60
    else: b = 0
    if night and hw >= 600: b += 60
    return b


# P(miss | slack): the arriving train's lateness minus the departing train's lateness, plus walking
# noise, modelled as the difference of two Laplace variables with scale B (from headways/results/
# adherence.json: |deviation| has a median of 1-1.7 min and 82-96% are within 5 min, i.e. a Laplace
# scale of ~2 min per train; two trains on one corridor are partly correlated, so 1.6 min is used).
# P = 0.5 (1 + x/2) exp(-x), x = slack / B. Walks between stations add noise: B x WALK_NOISE.
B_DAY, B_NIGHT, WALK_NOISE = 96.0, 132.0, 1.25
MISS_CAP = 1800           # s: a miss costs at most this (the rider can re-plan)


# ---------------------------------------------------------------------------------------------
# Pass-through policy (express rules). A station counts as passed only if the express track runs
# through the station box itself, alongside the platforms (centre express tracks between side
# platforms, or tracks next to an island platform). Stations where the express runs on a separate
# level, in a separate tunnel, or on bypass tracks are denied for every line. When unsure: deny.
# passes.py still requires the geometric test (station between the hop's stops on another trip and
# within 120 m of this trip's shape); this list removes the cases that test gets wrong.
# Allowed (kept by the geometric test, layouts with express tracks between/along the platforms):
#   7 Av IRT 86/79/66/59/50, 28/23/18, Christopher/Houston/Canal/Franklin (centre express, side platforms)
#   Lexington 33/28/23 St, Astor Pl, Bleecker, Spring, Canal (south of 42 St, single level)
#   Eastern Pkwy-Brooklyn Museum, Nostrand Av, Kingston Av; White Plains Rd and Pelham 3-track els;
#   Flushing 3-track el (7X); CPW 135..72 St, 8 Av 23 St and Spring St; Fulton St A express stops;
#   Concourse 182-183/174-175/170/167 St; Brighton local stops; 4 Av local stops; Broadway BMT
#   49/28/23 St, 8 St, Prince St; Queens Blvd 67 Av..Elmhurst, 65 St, Northern Blvd, 36 St, 75 Av,
#   169 St, Sutphin Blvd; Jamaica J/Z skip-stop (same track, past the platform); Broadway el centre
#   express (Flushing Av, Lorimer, Hewes); West End 3-track el.
PASS_DENY = {
    "236": "Bergen St (IRT Eastern Pkwy): two-level; 4/5 express on the lower level",
    "237": "Grand Army Plaza: two-level; 4/5 express on the lower level",
    "A25": "50 St (8 Av): two-level station; express tracks not along both platforms (unsure: deny)",
    "D11": "161 St-Yankee Stadium (Concourse): two-level, express track layout unclear (deny)",
    "D12": "155 St (Concourse): two-level, express track layout unclear (deny)",
    "R30": "DeKalb Av: D/N use the Manhattan Bridge bypass tracks, not the platform tracks",
    "D18": "23 St (6 Av): B/D express tracks run deep below the PATH tubes, not through the station",
    "D19": "14 St (6 Av): as 23 St, B/D express is on a separate deep level",
    "630": "51 St (Lexington): north of 42 St the 4/5 express tracks run on a lower level under the local station",
    "628": "68 St-Hunter College: 4/5 express on the lower level (two-level Lexington section, 42-116 St)",
    "627": "77 St (Lexington): 4/5 express on the lower level",
    "625": "96 St (Lexington): 4/5 express on the lower level",
    "624": "103 St (Lexington): 4/5 express on the lower level",
    "623": "110 St (Lexington): 4/5 express on the lower level",
    "622": "116 St (Lexington): 4/5 express on the lower level / ramping to the 125 St split levels",
    "A10": "163 St-Amsterdam Av: Washington Hts section, express track arrangement not verified (deny)",
    "A11": "155 St (8 Av): express track arrangement not verified (deny)",
    "416": "138 St-Grand Concourse: 4 express track arrangement not verified (deny)",
    "F05": "Briarwood: E/F express track arrangement with the Archer Av split (unsure: deny)",
    "G18": "46 St (Queens Blvd): express tracks run in a separate tunnel under Northern Blvd",
    "G19": "Steinway St: as 46 St, express tracks in a separate tunnel",
    "F20": "Bergen St (Culver): two-level; F express on the lower level",
    "F21": "Carroll St (Culver): F express layout not verified (deny)",
    "F22": "Smith-9 Sts: F express layout not verified (deny)",
    "F23": "4 Av-9 St (Culver): F express layout not verified (deny)",
    "F26": "Fort Hamilton Pkwy (Culver): express tracks on a lower level",
}
