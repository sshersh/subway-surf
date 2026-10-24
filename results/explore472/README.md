# Explore run: night starts, faster runner, ride-level search (2026-10-24T05:19Z, feed 20260826-X-long-term-supplement-trip-ids, run 40045579370)

Reference: saved best on main is 23:33. The fast arm uses a faster-runner model (--transfer-scale 0.6 --run-speed 3.0 --walk-overhead 60), not MTA transfer times, so it is not verified.

### Arm: night

## local: 240 starts

Objective (h): best 24:45, 10th pct 26:20, median 29:12, worst 305419896:36.
(express = robust objective: plan time + expected miss cost; local = plan time)

| Rank | Stage | Objective | Seed | Kick | Window | Start t0 |
|---|---|---|---|---|---|---|
| 1 | search | 24:45 | t0.8_gseed.npy | 3 | 0.0-2.5 h | 2.50 |
| 2 | search | 24:53 | t0.8_gseed.npy | 0 | 0.0-2.5 h | 1.70 |
| 3 | search | 24:59 | g0.5_gseed.npy | 0 | 0.0-2.5 h | 1.36 |
| 4 | search | 25:15 | t0.8_gseed.npy | 0 | 0.0-2.5 h | 1.40 |
| 5 | search | 25:18 | g0.3_gseed.npy | 0 | 0.0-2.5 h | 2.05 |
| 6 | search | 25:24 | g0.5_gseed.npy | 0 | 0.5-3.0 h | 3.00 |
| 7 | search | 25:29 | best_route.json | 1 | 0.0-2.5 h | 0.43 |
| 8 | search | 25:30 | g0.3_gseed.npy | 0 | 0.0-2.5 h | 2.10 |
| 9 | search | 25:31 | g0.5_gseed.npy | 3 | 0.0-2.5 h | 1.45 |
| 10 | search | 25:36 | g0.8_gseed.npy | 0 | 0.0-2.5 h | 2.39 |

Best by seed: t0.8_gseed.npy 24:45 (n=21); g0.5_gseed.npy 24:59 (n=23); g0.3_gseed.npy 25:18 (n=22); best_route.json 25:29 (n=23); g0.8_gseed.npy 25:36 (n=24); t0.3_gseed.npy 25:39 (n=20); t0.5_gseed.npy 26:39 (n=20); best_solution.npy 27:15 (n=24); ms472_best_local.json 28:03 (n=21); run3_mta_free.json 28:16 (n=22); ms472_best_local.npy 28:47 (n=20)

Best by start window: [0.0, 2.5] 24:45 (n=117); [0.5, 3.0] 25:24 (n=123)

Convergence: median start was within 3 min of its final result after 16 min (90th pct 24 min).

**night best: 24:45, 02:42:00 Beach 25 St -> 27:27:00 Canal St**

### Arm: fast

## local: 240 starts

Objective (h): best 23:43, 10th pct 25:18, median 27:46, worst 305419896:36.
(express = robust objective: plan time + expected miss cost; local = plan time)

| Rank | Stage | Objective | Seed | Kick | Window | Start t0 |
|---|---|---|---|---|---|---|
| 1 | search | 23:43 | g0.5_gseed.npy | 0 | 0-3 h | 3.00 |
| 2 | search | 23:56 | best_route.json | 5 | 5-8 h | 7.42 |
| 3 | search | 24:02 | best_route.json | 6 | 5-8 h | 6.85 |
| 4 | search | 24:15 | t0.8_gseed.npy | 0 | 1-4 h | 4.00 |
| 5 | search | 24:31 | t0.8_gseed.npy | 0 | 0-3 h | 3.00 |
| 6 | search | 24:32 | best_solution.npy | 4 | 5-8 h | 5.82 |
| 7 | search | 24:39 | t0.8_gseed.npy | 0 | 6-10 h | 7.56 |
| 8 | search | 24:42 | t0.8_gseed.npy | 1 | 0-8 h | 6.71 |
| 9 | search | 24:48 | g0.5_gseed.npy | 2 | 1-4 h | 3.01 |
| 10 | search | 24:52 | t0.8_gseed.npy | 2 | 4-7 h | 7.00 |

Best by seed: g0.5_gseed.npy 23:43 (n=21); best_route.json 23:56 (n=20); t0.8_gseed.npy 24:15 (n=23); best_solution.npy 24:32 (n=20); g0.3_gseed.npy 24:56 (n=22); t0.3_gseed.npy 24:59 (n=24); t0.5_gseed.npy 25:06 (n=24); g0.8_gseed.npy 25:19 (n=20); ms472_best_local.npy 26:05 (n=23); ms472_best_local.json 26:05 (n=22); run3_mta_free.json 26:18 (n=21)

Best by start window: [0, 3] 23:43 (n=35); [5, 8] 23:56 (n=37); [1, 4] 24:15 (n=26); [6, 10] 24:39 (n=29); [0, 8] 24:42 (n=30); [4, 7] 24:52 (n=27); [2, 5] 24:59 (n=29); [3, 6] 25:20 (n=27)

Convergence: median start was within 3 min of its final result after 17 min (90th pct 24 min).

**fast best: 23:43, 03:02:00 Far Rockaway-Mott Av -> 26:45:00 Astoria-Ditmars Blvd**

### Arm: ride

