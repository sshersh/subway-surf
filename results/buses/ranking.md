# Bus links between subway stations, ranked

Weekday bus schedule of 20261027 (MTA bus GTFS, feeds bus_bk, bus_bx, bus_m, bus_qns, bus_si, bus_busco); subway/walk alternatives from the planner's model (MTA transfer times, walk/run links to 2.5 km, 472-station count). **No real-time data is available**: reliability below is a schedule-based proxy, not a measurement. Arriving or passing a station by bus does not count as visiting it; a link is only a way to get from A to B.

Definitions: `door` = walk to stop + half the average headway + scheduled ride + walk from stop (platform to platform, expected). `existing` = fastest subway/walk path A to B in the model (mean of 3 start times in the band). `saving` = existing - door. Score = reliability x time-weighted mean over the day of max(0, saving); bands without service count as 0.

Reliability proxy R = type x stops x regularity x speed x route length (SBS 1.0 / limited 0.92 / express 0.90 / local 0.85; 1 - 0.8% per stop ridden, max 30%; 1/(1+0.5 CV of scheduled gaps); scheduled mph 5..10 maps to 0.75..1.0, slow = congested corridor; 1 - 0.1% per stop on the route pattern, max 20%). Share of the trip on busy corridors can't be told from the schedule; scheduled speed stands in for it.

Bands: early 4-6, AM 6-10, midday 10-15, PM 15-19, evening 19-23, night 23-4. Cells show headway min / saving min (`-` = no service or under 2 per band).

| # | From -> To | Route (class) | Walk in/out m | Ride min | early | am | midday | pm | evening | night | Avg saving | R | Score |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Pelham Bay Park -> Flushing-Main St | Q50 (limited) | 92/97 | 28 | 21.5 / +44.1 | 16.7 / +28.2 | 22.8 / +35.7 | 16 / +33.1 | 28 / +30.8 | 30 / +51.3 | 37.15 | 0.756 | 28.082 |
| 2 | Flushing-Main St -> Pelham Bay Park | Q50 (limited) | 38/91 | 33 | 26.2 / +42.9 | 15.9 / +30.7 | 24.2 / +24.2 | 15.3 / +26 | 27.2 / +30.2 | 30 / +58.7 | 35.33 | 0.774 | 27.35 |
| 3 | Flatbush Av-Brooklyn College -> Rockaway Park-Beach 116 St | Q35 (local) | 150/129 | 27.6 | 30 / +39.6 | 13.1 / +37.3 | 15 / +31.5 | 12.5 / +31.7 | 20 / +48.6 | 29.5 / +46.7 | 39.19 | 0.677 | 26.523 |
| 4 | Rockaway Park-Beach 116 St -> Flatbush Av-Brooklyn College | Q35 (local) | 154/146 | 32.4 | 26.1 / +37.9 | 11.8 / +39.8 | 14.6 / +34 | 11.8 / +31.1 | 21.3 / +40.3 | 30 / +50.4 | 39.27 | 0.672 | 26.381 |
| 5 | Flatbush Av-Brooklyn College -> Beach 105 St | Q35 (local) | 150/215 | 29 | 30 / +35.7 | 13.1 / +33 | 15 / +27.1 | 12.5 / +27.1 | 20 / +44.4 | 29.5 / +42.8 | 34.95 | 0.664 | 23.221 |
| 6 | Parkchester -> Flushing-Main St | Q44-SBS (sbs) | 84/105 | 36.9 | 11.9 / +36.9 | 6.7 / +18.5 | 7.9 / +24 | 7.3 / +14.1 | 7.7 / +29.5 | 17.1 / +48.5 | 28.53 | 0.787 | 22.463 |
| 7 | Flushing-Main St -> Parkchester | Q44-SBS (sbs) | 140/51 | 35.05 | 7.1 / +40.9 | 7.1 / +20.5 | 7.6 / +16.4 | 7.5 / +12.3 | 9.2 / +24.8 | 18.4 / +51.7 | 27.2 | 0.769 | 20.916 |
| 8 | 63 Dr-Rego Park -> Middle Village-Metropolitan Av | Q38 (local) | 106/106 | 13.2 | 17.5 / +47.9 | 11.8 / +35.3 | 19.7 / +30.2 | 12.4 / +31.7 | 21.5 / +32.8 | - | 26.92 | 0.663 | 17.835 |
| 9 | Beach 105 St -> Woodhaven Blvd | Q53-SBS (sbs) | 208/173 | 45.85 | 18 / +30 | 7.8 / +22.6 | 11 / +13.8 | 10.2 / +19.6 | 14.8 / +34.1 | 42.8 / +22 | 22.68 | 0.765 | 17.338 |
| 10 | Fresh Pond Rd -> Grand Av-Newtown | Q58 (local) | 72/12 | 22.4 | 7.4 / +36.4 | 5.7 / +30.5 | 8.9 / +21.1 | 6.2 / +24.8 | 10.2 / +29.6 | 33.7 / +39.3 | 29.77 | 0.582 | 17.321 |
| 11 | Beach 98 St -> Woodhaven Blvd | Q53-SBS (sbs) | 228/173 | 42.85 | 18.1 / +32.4 | 7.8 / +16.8 | 11 / +16.5 | 10.2 / +22.3 | 14.8 / +25.1 | 42.8 / +24.5 | 21.94 | 0.779 | 17.085 |
| 12 | Rockaway Park-Beach 116 St -> Woodhaven Blvd | Q53-SBS (sbs) | 160/173 | 48.75 | 18 / +28.2 | 7.8 / +25.9 | 11 / +15.3 | 10.2 / +17.5 | 14.8 / +31.9 | 42.9 / +20.1 | 22.27 | 0.757 | 16.851 |
| 13 | Beach 105 St -> Grand Av-Newtown | Q53-SBS (sbs) | 208/87 | 50.3 | 18 / +28.9 | 7.8 / +21.6 | 11 / +11.9 | 10.2 / +17.3 | 14.8 / +32.2 | 42.8 / +21.2 | 21.15 | 0.758 | 16.027 |
| 14 | Beach 98 St -> Grand Av-Newtown | Q53-SBS (sbs) | 228/87 | 47.25 | 18.1 / +31.3 | 7.8 / +15.8 | 11 / +14.6 | 10.2 / +20 | 14.8 / +23.2 | 42.8 / +23.6 | 20.4 | 0.772 | 15.742 |
| 15 | Rockaway Park-Beach 116 St -> Grand Av-Newtown | Q53-SBS (sbs) | 160/87 | 53.2 | 18 / +27.1 | 7.8 / +24.9 | 11 / +13.4 | 10.2 / +15.1 | 14.8 / +30 | 42.9 / +19.3 | 20.74 | 0.749 | 15.543 |
| 16 | West Farms Sq-E Tremont Av -> Flushing-Main St | Q44-SBS (sbs) | 150/105 | 42.35 | 11.4 / +29.8 | 6.6 / +12.3 | 7.8 / +15.2 | 7.3 / +6 | 7.8 / +21.2 | 17.1 / +37.2 | 19.98 | 0.774 | 15.459 |
| 17 | Fresh Pond Rd -> Woodhaven Blvd | Q98 (local) | 72/139 | 20 | 12.5 / +34.1 | 8.9 / +30.2 | 14.5 / +24.4 | 10.3 / +27.1 | 24.3 / +21.8 | 85 / +7.4 | 22.65 | 0.658 | 14.912 |
| 18 | Broad Channel -> Woodhaven Blvd | Q53-SBS (sbs) | 273/173 | 36.8 | 19 / +22.6 | 8 / +20.8 | 11 / +17.4 | 10.1 / +14.9 | 14.6 / +23.4 | 42.7 / +16.4 | 18.77 | 0.791 | 14.85 |
| 19 | St Lawrence Av -> Flushing-Main St | Q44-SBS (sbs) | 379/105 | 38.55 | 11.9 / +31.5 | 6.6 / +10.9 | 7.9 / +18.2 | 7.3 / +5.4 | 7.7 / +20.2 | 17.1 / +29.8 | 18.71 | 0.785 | 14.689 |
| 20 | Middle Village-Metropolitan Av -> 63 Dr-Rego Park | Q38 (local) | 119/65 | 15.8 | - | 11.4 / +35.4 | 20.1 / +30.7 | 11.8 / +35.1 | 18.4 / +35.5 | - | 24.06 | 0.608 | 14.634 |
| 21 | 125 St -> Astoria Blvd | M60-SBS (sbs) | 44/26 | 17.35 | 9.4 / +23.8 | 8.5 / +16 | 9.9 / +15.8 | 8.7 / +10.6 | 11.2 / +15 | 19 / +21.3 | 16.65 | 0.87 | 14.478 |
| 22 | Forest Av -> Grand Av-Newtown | Q58 (local) | 58/12 | 25.4 | 7.2 / +33.6 | 5.8 / +27.6 | 8.9 / +17.9 | 6.3 / +16 | 10.3 / +23.7 | 33.7 / +36.4 | 25.33 | 0.569 | 14.4 |
| 23 | Flushing-Main St -> West Farms Sq-E Tremont Av | Q44-SBS (sbs) | 140/222 | 39.7 | 7.1 / +35.1 | 7.1 / +10 | 7.6 / +8.3 | 7.5 / +6.3 | 9.2 / +17.9 | 18.4 / +37.7 | 18.21 | 0.753 | 13.704 |
| 24 | Grand Av-Newtown -> Beach 98 St | Q53-SBS (sbs) | 43/223 | 51 | 23.6 / +25.3 | 9.6 / +22.8 | 11.8 / +23.2 | 8.6 / +14.1 | 14.6 / +24.1 | 49.5 / +6.1 | 18.38 | 0.742 | 13.642 |
| 25 | Broad Channel -> Grand Av-Newtown | Q53-SBS (sbs) | 273/87 | 41.25 | 19 / +22 | 8 / +19.6 | 11 / +15.5 | 10.1 / +12.8 | 14.6 / +21.5 | 42.7 / +15.5 | 17.27 | 0.784 | 13.542 |
| 26 | Rockaway Blvd -> Woodhaven Blvd | Q53-SBS (sbs) | 52/173 | 20.35 | 20.4 / +21.4 | 8.1 / +15.9 | 11 / +18.3 | 9.9 / +13.2 | 14.4 / +21.9 | 42.6 / +10.8 | 16.35 | 0.823 | 13.45 |
| 27 | Grand Av-Newtown -> Fresh Pond Rd | Q58 (local) | 21/126 | 25.7 | 13.8 / +34.4 | 5.4 / +21 | 8.9 / +19 | 6.1 / +13.6 | 8.1 / +26.2 | 26.5 / +37.2 | 24.71 | 0.542 | 13.399 |
| 28 | Beach 105 St -> Elmhurst Av | Q53-SBS (sbs) | 208/181 | 53.2 | 18 / +25.6 | 7.8 / +18.4 | 11 / +7.8 | 10.2 / +13.2 | 14.8 / +27.9 | 42.8 / +18.9 | 17.61 | 0.751 | 13.22 |
| 29 | Beach 98 St -> Elmhurst Av | Q53-SBS (sbs) | 228/181 | 50.2 | 18.1 / +28 | 7.8 / +13.1 | 11 / +10.5 | 10.2 / +15.9 | 14.8 / +19 | 42.8 / +21.3 | 16.96 | 0.765 | 12.967 |
| 30 | Rockaway Park-Beach 116 St -> Elmhurst Av | Q53-SBS (sbs) | 160/181 | 56.1 | 18 / +23.8 | 7.8 / +21.5 | 11 / +10.2 | 10.2 / +11.1 | 14.8 / +25.8 | 42.9 / +16.9 | 17.36 | 0.742 | 12.891 |
| 31 | Flushing-Main St -> E 180 St | Q44-SBS (sbs) | 140/311 | 40.75 | 7.1 / +34.4 | 7.1 / +9 | 7.6 / +7.3 | 7.5 / +1.6 | 9.2 / +17.3 | 18.4 / +37.1 | 16.77 | 0.746 | 12.505 |
| 32 | Fordham Rd -> Pelham Bay Park | Bx12-SBS (sbs) | 179/145 | 26.55 | - | 4.3 / +25.4 | 5.8 / +23.5 | 5 / +18 | 7.5 / +23 | - | 15.96 | 0.781 | 12.472 |
| 33 | Rockaway Blvd -> Grand Av-Newtown | Q53-SBS (sbs) | 52/87 | 24.8 | 20.4 / +21.2 | 8.1 / +14.9 | 11 / +16.4 | 9.9 / +11.3 | 14.4 / +20 | 42.6 / +10 | 14.97 | 0.816 | 12.211 |
| 34 | Pelham Bay Park -> Fordham Rd | Bx12 (local) | 75/125 | 28.1 | 14.2 / +26 | 10.3 / +15.1 | 10.6 / +17.8 | 9.8 / +13.1 | 14.3 / +21.4 | 30.2 / +27.9 | 19.95 | 0.611 | 12.198 |
| 35 | Grand Av-Newtown -> Beach 105 St | Q53-SBS (sbs) | 43/203 | 54.3 | 23.6 / +24.2 | 9.6 / +20.8 | 11.8 / +21.2 | 8.6 / +12 | 14.6 / +22.1 | 49.5 / +4.9 | 16.6 | 0.729 | 12.1 |
| 36 | Grand Av-Newtown -> Rockaway Park-Beach 116 St | Q53-SBS (sbs) | 43/160 | 56.5 | 23.6 / +24.8 | 9.6 / +20.7 | 11.8 / +21.1 | 8.6 / +12.1 | 14.6 / +22 | 49.5 / +5.5 | 16.74 | 0.722 | 12.087 |
| 37 | Woodhaven Blvd -> Beach 98 St | Q53-SBS (sbs) | 148/223 | 45.9 | 27.5 / +18.8 | 9.5 / +21.8 | 11.8 / +14.1 | 8.6 / +10.3 | 14.3 / +27.7 | 49.3 / +7.6 | 16.05 | 0.753 | 12.085 |
| 38 | Forest Av -> Woodhaven Blvd | Q14 (local) | 97/107 | 24.5 | 24 / +23.4 | 12 / +23.7 | 14.3 / +24 | 9.2 / +18.4 | 14.1 / +21 | 50 / +22.1 | 22.07 | 0.548 | 12.084 |
| 39 | Jamaica-Van Wyck -> Middle Village-Metropolitan Av | Q54 (local) | 95/106 | 28.75 | 15 / +28.7 | 8.9 / +14.1 | 9.7 / +16.7 | 8.3 / +16.2 | 10.2 / +22.7 | 26.7 / +39.4 | 22.91 | 0.527 | 12.083 |
| 40 | Fordham Rd -> Pelham Bay Park | Bx12-SBS (sbs) | 59/145 | 28.15 | - | 4.3 / +22.7 | 5.8 / +23.7 | 5 / +13.2 | 7.6 / +25.5 | - | 15.17 | 0.776 | 11.78 |
| 41 | Pelham Pkwy -> 207 St | Bx12-SBS (sbs) | 192/23 | 21.2 | 7.2 / +37.8 | 4.2 / +25.2 | 5.5 / +25.3 | 5.2 / +20.9 | 25 / +18.7 | - | 19.22 | 0.608 | 11.695 |
| 42 | 125 St -> Astoria Blvd | M60-SBS (sbs) | 57/26 | 12.7 | 10 / +22.7 | 8.5 / +8.9 | 9.9 / +7.6 | 8.6 / +4.2 | 11.1 / +14.7 | 18.8 / +24.5 | 13.21 | 0.88 | 11.63 |
| 43 | Pelham Pkwy -> 207 St | Bx12-SBS (sbs) | 15/23 | 17.9 | 7.5 / +33 | 4.2 / +29 | 5.6 / +23 | 5.2 / +22.2 | 24.3 / +16 | - | 18.74 | 0.605 | 11.346 |
| 44 | Pelham Pkwy -> Inwood-207 St | Bx12-SBS (sbs) | 192/62 | 23.1 | 7.2 / +38.7 | 4.2 / +24.1 | 5.5 / +24.7 | 5.2 / +19.6 | 25 / +19.2 | - | 18.85 | 0.6 | 11.312 |
| 45 | Grand Av-Newtown -> Forest Av | Q58 (local) | 21/128 | 27.3 | 13.8 / +30.1 | 5.4 / +17.9 | 8.9 / +15.9 | 6.1 / +10.3 | 8.1 / +23 | 26.5 / +28.8 | 20.35 | 0.541 | 11.006 |
| 46 | Pelham Pkwy -> Inwood-207 St | Bx12-SBS (sbs) | 15/62 | 19.7 | 7.5 / +32.6 | 4.2 / +28.3 | 5.6 / +22.1 | 5.2 / +20.9 | 24.3 / +16.2 | - | 18.22 | 0.597 | 10.877 |
| 47 | Woodhaven Blvd -> Rockaway Park-Beach 116 St | Q53-SBS (sbs) | 148/160 | 51.5 | 27.5 / +18.3 | 9.5 / +19.7 | 11.8 / +12 | 8.6 / +8.6 | 14.3 / +25.6 | 49.3 / +7.1 | 14.49 | 0.732 | 10.611 |
| 48 | Broad Channel -> Elmhurst Av | Q53-SBS (sbs) | 273/181 | 44.15 | 19 / +19.6 | 8 / +15.7 | 11 / +11.2 | 10.1 / +8.2 | 14.6 / +17.7 | 42.7 / +13.2 | 13.65 | 0.777 | 10.605 |
| 49 | Kings Hwy -> Canarsie-Rockaway Pkwy | B82-SBS (sbs) | 104/133 | 32 | - | 7.7 / +22.6 | 12.1 / +20.1 | 8.3 / +16.2 | 12.3 / +18.4 | - | 13.72 | 0.772 | 10.593 |
| 50 | Woodhaven Blvd -> Beach 105 St | Q53-SBS (sbs) | 148/203 | 49.3 | 27.5 / +17.7 | 9.5 / +19.7 | 11.8 / +12.1 | 8.6 / +8.5 | 14.3 / +25.6 | 49.3 / +6.5 | 14.32 | 0.739 | 10.583 |
| 51 | 125 St -> Astoria Blvd | M60-SBS (sbs) | 345/26 | 24.6 | 9.2 / +23.9 | 8.5 / +7.4 | 9.9 / +9.9 | 8.8 / +2 | 11.3 / +12.9 | 19.1 / +23.4 | 12.65 | 0.827 | 10.453 |
| 52 | Elmhurst Av -> Beach 98 St | Q53-SBS (sbs) | 173/223 | 54.3 | 23.6 / +21.2 | 9.6 / +17.9 | 11.7 / +17.8 | 8.6 / +3.9 | 14.6 / +18.7 | 49.6 / +8.6 | 14.02 | 0.737 | 10.324 |
| 53 | Kings Hwy -> Canarsie-Rockaway Pkwy | B82-SBS (sbs) | 134/133 | 34.8 | - | 7.7 / +21.5 | 12.1 / +10.8 | 8.3 / +19 | 12.3 / +26.8 | - | 13.47 | 0.765 | 10.305 |
| 54 | Fordham Rd -> Pelham Pkwy | Bx12-SBS (sbs) | 59/229 | 16.75 | - | 4.3 / +16.7 | 5.8 / +18.9 | 5 / +11.6 | 7.6 / +23.7 | - | 12.6 | 0.801 | 10.092 |
| 55 | 207 St -> Pelham Pkwy | Bx12-SBS (sbs) | 49/59 | 19.75 | - | 4.3 / +27.7 | 5.8 / +27.5 | 5 / +21.4 | 21.2 / +21.6 | - | 17.51 | 0.572 | 10.022 |
| 56 | Pelham Bay Park -> 207 St | Bx12-SBS (sbs) | 75/23 | 36.2 | 6.7 / +36.1 | 4.2 / +22.4 | 5.4 / +21.6 | 5.4 / +20.8 | 26.7 / +13.7 | - | 16.99 | 0.586 | 9.957 |
| 57 | Pelham Bay Park -> Inwood-207 St | Bx12-SBS (sbs) | 75/62 | 38 | 6.7 / +35.2 | 4.2 / +22.6 | 5.4 / +22.8 | 5.4 / +19.9 | 26.7 / +14 | - | 17.1 | 0.578 | 9.877 |
| 58 | Woodhaven Blvd -> Forest Av | Q14 (local) | 158/76 | 24 | 14.7 / +31.6 | 11 / +17.1 | 14.1 / +14.3 | 10.6 / +15.4 | 16.1 / +24.4 | 61.5 / +13.5 | 17.91 | 0.55 | 9.843 |
| 59 | Pelham Bay Park -> Fordham Rd | Bx12 (local) | 75/23 | 29.8 | 14.2 / +24.9 | 10.3 / +11.7 | 10.6 / +14.2 | 9.8 / +10.2 | 14.3 / +16.8 | 30.2 / +23.2 | 16.32 | 0.602 | 9.83 |
| 60 | 207 St -> Pelham Pkwy | Bx12-SBS (sbs) | 49/229 | 23.65 | - | 4.3 / +28.6 | 5.8 / +25 | 5 / +17.1 | 21.2 / +25.8 | - | 17.12 | 0.567 | 9.716 |

300 links are in links.json (best route per directed station pair; each has its trips with trip ids, so the planner needs no bus feed). Rows beyond 60 are in the JSON only.
