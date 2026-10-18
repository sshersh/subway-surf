# Multi-start search (2026-10-18T12:26Z, feed 20260826-X-long-term-supplement-trip-ids, run 39105317886)

## express: 560 starts

Objective (h): best 26:57, 10th pct 27:17, median 30:25, worst 305419896:36.
(express = robust objective: plan time + expected miss cost; local = plan time)

| Rank | Stage | Objective | Seed | Kick | Window | Start t0 |
|---|---|---|---|---|---|---|
| 1 | refine | 26:57 | elite0.npy | 3 | 4-7 h | 6.67 |
| 2 | refine | 26:57 | elite0.npy | 6 | 0-8 h | 6.77 |
| 3 | search | 26:57 | hand_express.json | 1 | 4-7 h | 6.73 |
| 4 | refine | 26:58 | elite3.npy | 3 | 0-8 h | 4.92 |
| 5 | refine | 26:58 | elite7.npy | 1 | 3-6 h | 4.92 |
| 6 | refine | 26:58 | elite5.npy | 1 | 3-6 h | 4.92 |
| 7 | refine | 26:58 | elite7.npy | 4 | 4-7 h | 4.97 |
| 8 | refine | 26:58 | elite5.npy | 1 | 2-5 h | 4.92 |
| 9 | refine | 26:58 | elite6.npy | 3 | 0-8 h | 5.16 |
| 10 | refine | 26:58 | elite5.npy | 2 | 0-8 h | 4.92 |

Best by seed: elite0.npy 26:57 (n=15); hand_express.json 26:57 (n=57); elite3.npy 26:58 (n=16); elite7.npy 26:58 (n=26); elite5.npy 26:58 (n=27); elite6.npy 26:58 (n=15); elite4.npy 26:58 (n=24); elite2.npy 26:58 (n=21); final_express.json 26:58 (n=58); elite1.npy 27:17 (n=16); robust_express.json 27:18 (n=58); t0.3_gseed.npy 27:22 (n=56); d_best.json 28:10 (n=56); t0.5_gseed.npy 28:19 (n=57); t0.8_gseed.npy 28:33 (n=58)

Best by start window: [4, 7] 26:57 (n=80); [0, 8] 26:57 (n=85); [3, 6] 26:58 (n=59); [2, 5] 26:58 (n=66); [5, 8] 26:58 (n=75); [1, 4] 27:44 (n=64); [6, 10] 27:45 (n=59); [0, 3] 28:49 (n=72)

Convergence: median start was within 3 min of its final result after 16 min (90th pct 24 min).

**express plan: 25:40**, 06:48:30 Rockaway Park-Beach 116 St -> 32:28:30 Pelham Bay Park, stations 475

## local: 560 starts

Objective (h): best 24:33, 10th pct 25:29, median 28:28, worst 305419896:36.
(express = robust objective: plan time + expected miss cost; local = plan time)

| Rank | Stage | Objective | Seed | Kick | Window | Start t0 |
|---|---|---|---|---|---|---|
| 1 | refine | 24:33 | elite1.npy | 1 | 5-8 h | 7.55 |
| 2 | refine | 24:36 | elite5.npy | 5 | 4-7 h | 7.00 |
| 3 | refine | 24:36 | elite5.npy | 1 | 4-7 h | 7.00 |
| 4 | search | 24:36 | g0.3_gseed.npy | 0 | 5-8 h | 7.58 |
| 5 | refine | 24:38 | elite1.npy | 1 | 6-10 h | 7.42 |
| 6 | refine | 24:38 | elite1.npy | 3 | 6-10 h | 7.48 |
| 7 | search | 24:38 | g0.3_gseed.npy | 0 | 5-8 h | 7.43 |
| 8 | refine | 24:42 | elite3.npy | 1 | 0-8 h | 7.05 |
| 9 | refine | 24:42 | elite2.npy | 2 | 5-8 h | 7.00 |
| 10 | refine | 24:42 | elite3.npy | 2 | 4-7 h | 7.00 |

Best by seed: elite1.npy 24:33 (n=23); elite5.npy 24:36 (n=22); g0.3_gseed.npy 24:36 (n=80); elite3.npy 24:42 (n=19); elite2.npy 24:42 (n=21); elite6.npy 24:54 (n=15); elite4.npy 24:59 (n=24); run3_mta_free.npy 24:59 (n=80); elite7.npy 25:12 (n=24); g0.5_gseed.npy 25:12 (n=80); g0.8_gseed.npy 25:29 (n=80); run1_mta_fixed_ends.npy 25:57 (n=80); elite0.npy 27:12 (n=12)

Best by start window: [5, 8] 24:33 (n=75); [4, 7] 24:36 (n=64); [6, 10] 24:38 (n=78); [0, 8] 24:42 (n=52); [3, 6] 24:59 (n=81); [2, 5] 24:59 (n=65); [0, 3] 25:57 (n=80); [1, 4] 26:06 (n=65)

Convergence: median start was within 3 min of its final result after 14 min (90th pct 23 min).

**local plan: 24:32**, 07:35:00 Far Rockaway-Mott Av -> 32:07:30 South Ferry, stations 475

